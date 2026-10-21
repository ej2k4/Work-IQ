"""
tools.py – Jailed file and test tools for the coding agent.

All file operations are restricted to the workspace root.  Any path that
resolves outside the workspace raises a ValueError and returns an error
observation — the agent cannot escape via '../' traversal.

Tool signatures (as seen by the model):
    list_dir(path=".")
    read_file(path)
    write_file(path, content)
    run_tests(path="")          # empty path = run all tests
    search_memory(query, top_k) # vector search over indexed code/docs
    finish(summary)             # handled in loop.py, not here
"""
import subprocess
import sys
from pathlib import Path

from agent.security import validate_path, SecurityViolation

MAX_OBS = 3000  # characters; keeps context from ballooning


def _clip(text: str) -> str:
    """Truncate long tool output with a clear marker."""
    if len(text) <= MAX_OBS:
        return text
    return text[:MAX_OBS] + f"\n...[truncated {len(text) - MAX_OBS} chars]"


class Tools:
    """File and test tools, jailed to one workspace folder."""

    def __init__(self, workspace, db=None, allowed_write_files=None):
        self.root = Path(workspace).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # Set to True only after run_tests passes; reset on every write_file.
        self.tests_green = False
        # Optional DB for search_memory and graph queries (Phase 2 & 3).
        self._db = db
        # Optional set of allowed write targets for subtask isolation.
        self.allowed_write_files = allowed_write_files
        # Set of file paths modified during this task.
        self.touched_files: set[str] = set()

    # ── Path safety ─────────────────────────────────────────────────────────

    def _safe(self, rel: str, is_write: bool = False) -> Path:
        """
        Validate *rel* relative to workspace root using hardened security policies.
        Raises SecurityViolation / ValueError if path escapes or violates policy.
        """
        return validate_path(
            rel,
            self.root,
            is_write=is_write,
            allowed_write_files=self.allowed_write_files if is_write else None,
        )

    # ── Tools ────────────────────────────────────────────────────────────────

    def list_dir(self, path: str = ".") -> str:
        """Return a sorted listing of files and subdirectories at *path*."""
        try:
            p = self._safe(path)
        except ValueError as e:
            return f"ERROR: {e}"
        if not p.exists():
            return f"ERROR: '{path}' does not exist"
        if not p.is_dir():
            return f"ERROR: '{path}' is not a directory"
        entries = sorted(
            (c.name + ("/" if c.is_dir() else ""))
            for c in p.iterdir()
            if c.name not in {"__pycache__", ".pytest_cache", ".git"}
        )
        return "\n".join(entries) if entries else "(empty directory)"

    def read_file(self, path: str) -> str:
        """Return the contents of *path* (clipped to MAX_OBS chars)."""
        try:
            p = self._safe(path)
        except ValueError as e:
            return f"ERROR: {e}"
        if not p.exists():
            return f"ERROR: file '{path}' does not exist"
        if not p.is_file():
            return f"ERROR: '{path}' is a directory, not a file"
        return _clip(p.read_text(encoding="utf-8", errors="replace"))

    def write_file(self, path: str, content: str) -> str:
        """
        Overwrite *path* with *content* (creating parent dirs as needed).
        Resets tests_green to False — the agent must re-run tests after writing.
        """
        try:
            p = self._safe(path, is_write=True)
        except (ValueError, SecurityViolation) as e:
            return f"ERROR: {e}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        self.tests_green = False
        self.touched_files.add(path)
        return f"OK: wrote {len(content)} chars to {path}"

    def run_tests(self, path: str = "") -> str:
        """
        Run pytest inside the workspace.

        Args:
            path: Optional relative path to a specific test file.
                  If empty, run all tests in the workspace.

        Returns a string starting with 'TESTS PASSED' or 'TESTS FAILED',
        followed by pytest's stdout/stderr (clipped).
        """
        cmd = [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"]
        if path:
            try:
                cmd.append(str(self._safe(path)))
            except ValueError as e:
                return f"ERROR: {e}"
        try:
            r = subprocess.run(
                cmd,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: tests timed out after 60s"
        except FileNotFoundError:
            return "ERROR: pytest not found — is it installed in this environment?"

        self.tests_green = r.returncode == 0
        status = "PASSED" if self.tests_green else "FAILED"
        output = _clip((r.stdout + r.stderr).strip())
        return f"TESTS {status}\n{output}"

    # ── Memory search (Phase 2) ──────────────────────────────────────────────

    def search_memory(self, query: str, top_k: int = 5, min_score: float = 0.55) -> str:
        """
        Embed *query* and return the top-k most relevant code/doc chunks
        from the vector index. Results below *min_score* are excluded.

        Returns a formatted string listing file path, line range, and a
        short text snippet for each result.
        """
        if self._db is None:
            return "ERROR: memory index not available (no DB attached)"
        try:
            from memory.vectors import embed, cosine_search
        except ImportError as e:
            return f"ERROR: memory module not available: {e}"

        try:
            qvec = embed(query)
        except Exception as e:
            return f"ERROR: embedding failed: {e}"

        rows = self._db.all_embeddings()
        if not rows:
            return "No documents indexed yet. Run: python -m memory.vectors index <dir>"

        results = cosine_search(qvec, rows, top_k=int(top_k), min_score=float(min_score))
        if not results:
            return (
                f"No relevant documents found (similarity below threshold {min_score}). "
                "Try reading files directly or refining your query."
            )

        lines = []
        for i, r in enumerate(results, 1):
            path = self._db.chunk_path(r["chunk_id"]) or "unknown"
            snippet = r["text"][:300].replace("\n", " ").strip()
            lines.append(
                f"[{i}] score={r['score']:.3f}  {path}  "
                f"lines {r['start_line']}-{r['end_line']}\n"
                f"    {snippet}"
            )
        return "\n".join(lines)

    # ── Graph context (Phase 3) ──────────────────────────────────────────────

    def query_graph(self, symbol: str, hops: int = 2) -> str:
        """
        Query the code and concept graph for symbol relationships.
        Shows callers, dependencies, definitions, and linked notes.
        """
        if self._db is None:
            return "ERROR: graph index not available (no DB attached)"
        try:
            from memory.graph import load_graph, find_impact, find_dependencies
        except ImportError as e:
            return f"ERROR: graph module not available: {e}"

        G = load_graph(self._db)
        if len(G) == 0:
            return "No graph indexed yet. Run: python -m memory.graph index <dir>"

        impacted = find_impact(G, symbol, max_hops=int(hops))
        deps = find_dependencies(G, symbol, max_hops=int(hops))

        if not impacted and not deps:
            return f"No callers or dependencies found for '{symbol}' in the graph."

        lines = [f"Graph relationships for '{symbol}':"]
        if impacted:
            lines.append("  Dependents / Callers (what might break if modified):")
            for item in impacted[:6]:
                lines.append(f"    - [{item['kind']}] {item['name']} ({item['ref']}) [depth {item['depth']}]")
        if deps:
            lines.append("  Dependencies / Called symbols:")
            for item in deps[:6]:
                lines.append(f"    - [{item['kind']}] {item['name']} ({item['ref']}) [depth {item['depth']}]")

        return "\n".join(lines)

    # ── Dispatcher ───────────────────────────────────────────────────────────

    def call(self, tool: str, args: dict) -> str:
        """
        Dispatch a tool call by name.  Returns an observation string.
        'finish' is NOT handled here — loop.py owns that logic.
        """
        dispatch = {
            "list_dir": self.list_dir,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "run_tests": self.run_tests,
            "search_memory": self.search_memory,
            "query_graph": self.query_graph,
        }
        if tool not in dispatch:
            valid = ", ".join(dispatch) + ", finish"
            return f"ERROR: unknown tool '{tool}'. Valid tools: {valid}"
        try:
            return dispatch[tool](**args)
        except TypeError as e:
            return f"ERROR: wrong arguments for '{tool}': {e}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {e}"
