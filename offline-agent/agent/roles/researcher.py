"""
researcher.py – Researcher role for Phase 4 multi-agent orchestration.

Queries vector memory, code graph, and past lessons in SQLite to assemble
a concise, high-signal context packet for the Coder before attempting a subtask.
"""
from __future__ import annotations

from memory.db import DB
from memory.graph import load_graph, find_dependencies, find_impact
from memory.vectors import embed, cosine_search


from pathlib import Path

def build_research_context(
    subtask: dict,
    db: DB,
    workspace: Path | str | None = None,
    enable_learning: bool = True,
    top_k_chunks: int = 2,
    max_chars: int = 1200,
) -> str:
    """
    Search workspace files, vector memory, and past lessons to construct
    a compact context block for the Coder.
    """
    spec = subtask.get("spec", "")
    title = subtask.get("title", "")
    query = f"{title} {spec}"[:300]

    lines = []

    # 1. Existing workspace implementations (highest signal for writing tests or docs)
    if workspace:
        ws_p = Path(workspace).resolve()
        py_files = [p for p in ws_p.glob("*.py") if p.is_file() and not p.name.startswith("test_")]
        if py_files:
            lines.append("Workspace Implementations:")
            for pf in py_files[:2]:
                try:
                    content = pf.read_text(encoding="utf-8", errors="replace")
                    sig_lines = [l.strip() for l in content.splitlines() if l.strip().startswith(("def ", "class "))]
                    if sig_lines:
                        lines.append(f"  [{pf.name}]:")
                        for sig in sig_lines[:6]:
                            lines.append(f"    {sig}")
                except Exception:
                    pass

    # 2. Semantic learning loop: verified lessons and pitfalls (if enabled)
    if enable_learning:
        try:
            from agent.learning import retrieve_learning_context
            learn_ctx = retrieve_learning_context(query, db=db, top_k=2)
            if learn_ctx["formatted_text"]:
                lines.append(learn_ctx["formatted_text"])
        except Exception:
            recent_lessons = db.recent_facts(kind="lesson", limit=2)
            if recent_lessons:
                lines.append("Past Lessons & Verified Patterns:")
                for l in recent_lessons:
                    lines.append(f"  • {l.strip()[:180]}")

    # 3. Vector search over indexed documentation/code (high threshold)
    rows = db.all_embeddings()
    if rows:
        try:
            qvec = embed(query)
            chunks = cosine_search(qvec, rows, top_k=top_k_chunks, min_score=0.62)
            if chunks:
                lines.append("Relevant Context Chunks from Memory:")
                for c in chunks:
                    p = db.chunk_path(c["chunk_id"]) or "code"
                    snip = c["text"].strip().replace("\r\n", "\n")[:200].replace('"""', "'''")
                    lines.append(f"  [{Path(p).name} lines {c['start_line']}-{c['end_line']}]:\n  {snip}")
        except Exception:
            pass  # best-effort retrieval

    # 4. Code graph dependencies
    G = load_graph(db)
    if len(G) > 0:
        words = [w for w in spec.replace("`", " ").split() if len(w) > 3 and w.isidentifier()]
        found_deps = []
        for w in words[:4]:
            deps = find_dependencies(G, w, max_hops=1)
            for d in deps[:2]:
                found_deps.append(f"{w} -> {d['name']} ({d['ref']})")
        if found_deps:
            lines.append("Code Graph Dependencies:")
            for fd in found_deps[:4]:
                lines.append(f"  • {fd}")

    full_context = "\n".join(lines).strip()
    return full_context[:max_chars] if full_context else ""
