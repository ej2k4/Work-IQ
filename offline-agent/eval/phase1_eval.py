"""
phase1_eval.py – Phase 1 evaluation harness.

Runs the agent on each of the 5 seeded-bug tasks and grades by pytest,
not by the model's own claim.

Anti-cheat checks:
  - The harness re-runs pytest itself; the model's 'finish' claim is irrelevant.
  - Every test file's content is compared against the canonical version.
    If ANY test file was modified, the task is marked FAIL + [edited tests!].

Usage:
    python -m eval.phase1_eval --model qwen2.5-coder:3b
    python -m eval.phase1_eval --model qwen2.5-coder:7b --max-steps 16
    python -m eval.phase1_eval --runs 3   # run each task 3 times
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from agent.loop import run_agent
from eval.toy_repo import FILES, TEST_FILES, build
from memory.db import DB

# Resolve the venv Python so the harness works whether or not the venv is
# activated in the shell.  We look for .venv/Scripts/python.exe relative to
# the project root (two directories up from this file: eval/ -> project root).
# If that doesn't exist we fall back to sys.executable (already-activated venv).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"  # Windows
if not _VENV_PYTHON.exists():
    _VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"       # Unix
_PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable


def _pytest_passes(workspace: Path, test_file: str) -> bool:
    """Return True if pytest exits 0 for the given test file inside workspace."""
    r = subprocess.run(
        [_PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", test_file],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return r.returncode == 0


def _any_test_tampered(workspace: Path) -> list[str]:
    """
    Compare every test file in workspace against its canonical content.
    Returns a list of tampered file names (empty if none were altered).
    """
    tampered = []
    for name in TEST_FILES:
        current = (workspace / name).read_text(encoding="utf-8")
        if current != FILES[name]:
            tampered.append(name)
    return tampered


def run_one(test_file: str, workspace: Path, model, max_steps: int,
            db: DB, run_index: int) -> dict:
    """Run the agent on a single task and return a result dict."""
    if workspace.exists():
        shutil.rmtree(workspace)
    build(workspace)

    task = (
        f"The tests in {test_file} are failing. "
        f"Fix the source code so they pass. Do not edit any test file. "
        f"Only run '{test_file}' when testing — ignore failures in other test files."
    )
    t0 = time.time()
    res = run_agent(task, str(workspace), model=model,
                    max_steps=max_steps, db=db, verbose=True)
    elapsed = time.time() - t0

    passed = _pytest_passes(workspace, test_file)
    tampered = _any_test_tampered(workspace)

    return {
        "test_file": test_file,
        "run": run_index,
        "passed": passed and not tampered,
        "status": res["status"],
        "tampered": tampered,
        "elapsed": elapsed,
        "task_id": res.get("task_id"),
    }


def main():
    p = argparse.ArgumentParser(description="Phase 1 evaluation harness")
    p.add_argument("--model", default=None,
                   help="Ollama model name (default: AGENT_MODEL or qwen2.5-coder:3b)")
    p.add_argument("--max-steps", type=int, default=12,
                   help="Max steps per task (default: 12)")
    p.add_argument("--runs", type=int, default=1,
                   help="How many times to run each task (default: 1; use 3 for the gate)")
    p.add_argument("--db", default="data/memory.db",
                   help="SQLite database path (default: data/memory.db)")
    a = p.parse_args()

    db = DB(a.db)
    base = Path("data/workspaces")
    all_results: list[dict] = []

    for run_idx in range(1, a.runs + 1):
        if a.runs > 1:
            print(f"\n{'='*60}")
            print(f"  RUN {run_idx} of {a.runs}")
            print(f"{'='*60}")

        for test_file in TEST_FILES:
            ws = base / f"eval_{test_file[:-3]}_r{run_idx}"
            print(f"\n--- {test_file} (run {run_idx}) ---")
            result = run_one(test_file, ws, a.model, a.max_steps, db, run_idx)
            all_results.append(result)

            outcome = "PASS" if result["passed"] else "FAIL"
            tamper_note = (
                f"  [edited tests: {', '.join(result['tampered'])}]"
                if result["tampered"] else ""
            )
            print(
                f"==> {test_file}: {outcome} "
                f"({result['status']}, {result['elapsed']:.0f}s)"
                f"{tamper_note}\n"
            )

    # ── Summary table ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    # Group by test_file for multi-run reporting
    by_file: dict[str, list[dict]] = {}
    for r in all_results:
        by_file.setdefault(r["test_file"], []).append(r)

    total_pass = 0
    total_runs = 0
    for fname, runs in by_file.items():
        passes = sum(1 for r in runs if r["passed"])
        total_pass += passes
        total_runs += len(runs)
        run_str = f"{passes}/{len(runs)}"
        tamper_any = any(r["tampered"] for r in runs)
        flag = "  [test edits detected!]" if tamper_any else ""
        print(f"{run_str:>5}  {fname:<22} {flag}")

    print("-" * 60)
    print(f"{total_pass}/{total_runs} runs passed")
    gate = total_pass / total_runs >= 0.8  # Phase 1 gate: ≥ 4/5 pass rate
    print(f"\nPhase 1 gate (≥80% pass rate): {'PASS ✓' if gate else 'FAIL ✗'}")

    if total_pass < total_runs:
        print(
            "\nTip: to inspect failures, run:\n"
            "  python -c \""
            "import sqlite3; c=sqlite3.connect('data/memory.db'); "
            "[print(r) for r in c.execute("
            "'SELECT task_id,n,tool,substr(observation,1,120) "
            "FROM steps ORDER BY id DESC LIMIT 50')]\""
        )

    sys.exit(0 if gate else 1)


if __name__ == "__main__":
    main()
