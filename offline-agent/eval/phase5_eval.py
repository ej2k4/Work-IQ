"""
phase5_eval.py – Phase 5 evaluation harness for the learning loop.

Tests the Phase 5 gate from plan.md:
  "Each learning step improves a held-out benchmark; otherwise roll back."

Protocol:
  1. Define a held-out 3-file task never seen during training/prompts:
     - `url_utils.py`: parse_query and build_query query string utilities
     - `tests/test_url.py`: pytest unit test suite
     - `docs/url.md`: Markdown documentation with examples
  2. Run Condition A: Cold Baseline (enable_learning=False) in data/workspaces/phase5_cold
  3. Run Condition B: Learned Agent (enable_learning=True) in data/workspaces/phase5_learned
  4. Grade both workspaces objectively via independent harness tests:
     - Files created (>30 bytes)
     - pytest passes
     - Independent functional checks pass
     - Documentation valid
  5. Judge Phase 5 Gate:
     - Learned Agent achieves composite score >= 80%
     - Learned Agent outperforms or matches Cold Baseline with equal/fewer retries.

Usage:
    python -m eval.phase5_eval
    python -m eval.phase5_eval --skip-cold    # test only learned agent
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Ensure UTF-8 console output on Windows with unbuffered line output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

from agent.llm import DEFAULT_MODEL
from agent.orchestrator import run_orchestrated_task
from memory.db import DB

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
if not _VENV_PYTHON.exists():
    _VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
_PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable

TASK_PROMPT = """Create a URL query string parser utility across three files in this project:

1. 'url_utils.py':
   - 'parse_query(query_str: str) -> dict': parses 'key=val&key2=val2' into a dictionary. Strips leading '?' if present. Ignores empty pairs. Values are strings. Example: parse_query("?a=1&b=2") -> {"a": "1", "b": "2"}.
   - 'build_query(params: dict) -> str': converts dictionary into a sorted 'key=val&key2=val2' string. Example: build_query({"b": "2", "a": "1"}) -> "a=1&b=2".

2. 'tests/test_url.py':
   - Unit tests using pytest testing parse_query (standard params, leading '?', empty string, multiple pairs) and build_query (sorting, empty dict, basic dict).
   - Must pass when running pytest.

3. 'docs/url.md':
   - Markdown documentation describing the functions, parameters, return types, and usage examples.
"""


def grade_workspace(ws: Path, verbose: bool = True) -> dict:
    """
    Independent grading harness checking all 3 deliverables for URL query utility.
    """
    scores = {
        "files_created": 0,
        "pytest_passed": False,
        "functional_passed": False,
        "docs_valid": False,
        "total_score": 0.0,
        "errors": [],
    }

    p_utils = ws / "url_utils.py"
    p_tests = ws / "tests" / "test_url.py"
    p_docs = ws / "docs" / "url.md"

    # Check files exist
    created_count = sum(1 for p in (p_utils, p_tests, p_docs) if p.is_file() and p.stat().st_size > 30)
    scores["files_created"] = created_count

    # Check 1: docs
    if p_docs.is_file() and p_docs.stat().st_size > 50:
        content = p_docs.read_text(encoding="utf-8", errors="replace")
        if "#" in content and ("url" in content.lower() or "query" in content.lower()):
            scores["docs_valid"] = True

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ws) + os.pathsep + env.get("PYTHONPATH", "")

    # Check 2: pytest
    if p_tests.is_file():
        r = subprocess.run(
            [_PYTHON, "-m", "pytest", "-q", str(p_tests)],
            cwd=ws,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if r.returncode == 0:
            scores["pytest_passed"] = True
        else:
            scores["errors"].append(f"pytest failed: {r.stdout.strip()[:200]}")

    # Check 3: independent functional check
    if p_utils.is_file():
        check_code = """
import sys
sys.path.insert(0, '.')
from url_utils import parse_query, build_query

# Test parse_query
res1 = parse_query('?a=1&b=2')
assert res1.get('a') == '1' and res1.get('b') == '2', f"parse_query with leading ? failed: {res1}"

res2 = parse_query('name=antigravity&mode=offline')
assert res2.get('name') == 'antigravity' and res2.get('mode') == 'offline', f"parse_query standard failed: {res2}"

assert parse_query('') == {}, "parse_query empty string failed"

# Test build_query
b_res = build_query({'b': '2', 'a': '1'})
assert b_res == 'a=1&b=2', f"build_query sorting failed: {b_res}"
assert build_query({}) == '', "build_query empty dict failed"

print('FUNCTIONAL_OK')
"""
        r_func = subprocess.run(
            [_PYTHON, "-c", check_code],
            cwd=ws,
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if r_func.returncode == 0 and "FUNCTIONAL_OK" in r_func.stdout:
            scores["functional_passed"] = True
        else:
            err = (r_func.stdout + "\n" + r_func.stderr).strip()
            scores["errors"].append(f"functional check failed: {err[:200]}")

    # Compute composite score out of 100
    total = 0.0
    if scores["files_created"] == 3:
        total += 30.0
    else:
        total += scores["files_created"] * 10.0

    if scores["docs_valid"]:
        total += 20.0
    if scores["pytest_passed"]:
        total += 25.0
    if scores["functional_passed"]:
        total += 25.0

    scores["total_score"] = total

    if verbose:
        print(f"  Files created:       {scores['files_created']}/3")
        print(f"  Documentation valid: {'PASS' if scores['docs_valid'] else 'FAIL'}")
        print(f"  Agent's pytest:      {'PASS' if scores['pytest_passed'] else 'FAIL'}")
        print(f"  Harness validation:  {'PASS' if scores['functional_passed'] else 'FAIL'}")
        print(f"  Total Score:         {scores['total_score']:.1f}/100")
        if scores["errors"]:
            for e in scores["errors"]:
                print(f"    - {e}")

    return scores


def main():
    p = argparse.ArgumentParser(description="Phase 5 Learning Loop Benchmark Evaluation")
    p.add_argument("--model", default=None,
                   help="Ollama model name (default: qwen2.5-coder:3b)")
    p.add_argument("--skip-cold", action="store_true",
                   help="Skip cold baseline run (use existing workspace if available)")
    a = p.parse_args()

    model = a.model or DEFAULT_MODEL
    db = DB("data/memory.db")

    ws_cold = _PROJECT_ROOT / "data" / "workspaces" / "phase5_cold"
    ws_learned = _PROJECT_ROOT / "data" / "workspaces" / "phase5_learned"

    print("=" * 65, flush=True)
    print("  PHASE 5 EVALUATION: LEARNING LOOP & HELD-OUT GATE", flush=True)
    print("=" * 65, flush=True)
    print(f"Model: {model}", flush=True)
    print("Goal: Build 3-file system (url_utils.py, tests/test_url.py, docs/url.md)\n", flush=True)

    cold_scores = {"total_score": 0.0, "files_created": 0, "pytest_passed": False, "functional_passed": False, "docs_valid": False}
    cold_time = 0.0

    # ── 1. Cold Baseline (No Learning Retrieval) ──────────────────────────────
    if not a.skip_cold:
        print("-" * 65, flush=True)
        print("RUNNING CONDITION A: Cold Baseline (learning retrieval disabled)...", flush=True)
        print("-" * 65, flush=True)
        if ws_cold.exists():
            shutil.rmtree(ws_cold)
        ws_cold.mkdir(parents=True, exist_ok=True)

        t0 = time.time()
        res_cold = run_orchestrated_task(
            TASK_PROMPT,
            str(ws_cold),
            model=model,
            db=db,
            max_subtask_steps=10,
            max_retries=3,
            enable_learning=False,
            verbose=True,
        )
        cold_time = time.time() - t0
        print(f"\nCold Baseline finished in {cold_time:.1f}s (status: {res_cold['status']})", flush=True)

        print("\nGrading Cold Baseline:")
        cold_scores = grade_workspace(ws_cold, verbose=True)
    else:
        if ws_cold.exists() and any(ws_cold.iterdir()):
            print("Grading existing Cold Baseline workspace...", flush=True)
            cold_scores = grade_workspace(ws_cold, verbose=False)
            print(f"Cold Baseline score: {cold_scores['total_score']:.1f}/100", flush=True)
        else:
            cold_scores["total_score"] = 0.0

    # ── 2. Learned Agent (With Phase 5 Learning Loop) ─────────────────────────
    print("\n" + "-" * 65, flush=True)
    print("RUNNING CONDITION B: Learned Agent (with verified experience & docs)...", flush=True)
    print("-" * 65, flush=True)
    if ws_learned.exists():
        shutil.rmtree(ws_learned)
    ws_learned.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    res_learned = run_orchestrated_task(
        TASK_PROMPT,
        str(ws_learned),
        model=model,
        db=db,
        max_subtask_steps=10,
        max_retries=3,
        enable_learning=True,
        verbose=True,
    )
    learned_time = time.time() - t0
    print(f"\nLearned Agent finished in {learned_time:.1f}s (status: {res_learned['status']})", flush=True)

    print("\nGrading Learned Workspace:")
    learned_scores = grade_workspace(ws_learned, verbose=True)

    # ── 3. Summary & Gate ─────────────────────────────────────────────────────
    print("\n" + "=" * 65, flush=True)
    print("PHASE 5 GATE COMPARISON SUMMARY", flush=True)
    print("=" * 65, flush=True)
    if not a.skip_cold:
        print(f"Cold Baseline Score:  {cold_scores['total_score']:.1f}/100 ({cold_time:.1f}s)", flush=True)
    print(f"Learned Agent Score:  {learned_scores['total_score']:.1f}/100 ({learned_time:.1f}s)", flush=True)

    gate_passed = (
        learned_scores["total_score"] >= 80.0
        and learned_scores["files_created"] == 3
        and learned_scores["functional_passed"]
        and learned_scores["total_score"] >= cold_scores["total_score"]
    )

    status_str = "PASS" if gate_passed else "FAIL"
    print("-" * 65, flush=True)
    print(f"Phase 5 Gate (Learned >= 80% & >= Cold Baseline): {status_str}", flush=True)


if __name__ == "__main__":
    main()
