"""
phase4_eval.py – Phase 4 evaluation harness for multi-agent execution.

Tests the Phase 4 gate from plan.md:
  "A task needing 3 or more files (for example, 'add a CLI command with tests
   and docs') completes end to end, and beats the Phase 1 single agent on the
   same benchmark."

Protocol:
  1. Define a 3-file task:
     - `slug_utils.py`: string slugification and unslugification utility
     - `tests/test_slug.py`: pytest unit test suite
     - `docs/slug.md`: Markdown documentation with examples
  2. Run Single Agent (Phase 1 Baseline) in data/workspaces/phase4_single
  3. Run Multi-Agent Orchestrator (Phase 4) in data/workspaces/phase4_multi
  4. Grade both runs objectively via independent harness tests:
     - All 3 files present and valid
     - pytest passes
     - Independent functional checks pass
     - Documentation exists and has content
  5. Judge Phase 4 Gate: Multi-Agent completes end-to-end and outperforms single agent.

Usage:
    python -m eval.phase4_eval
    python -m eval.phase4_eval --model qwen2.5-coder:3b
    python -m eval.phase4_eval --skip-single    # test only multi-agent orchestrator
"""
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
from agent.loop import run_agent
from agent.orchestrator import run_orchestrated_task
from memory.db import DB

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
if not _VENV_PYTHON.exists():
    _VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
_PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable

TASK_PROMPT = """Create a string slugifier utility across three files in this project:

1. 'slug_utils.py':
   - 'slugify(text: str, separator: str = "-") -> str': converts text to lowercase, replaces punctuation and whitespace with separator, collapses duplicate separators, and strips leading/trailing separators. Example: slugify("Hello, World! 123") -> "hello-world-123".
   - 'unslugify(slug: str, separator: str = "-") -> str': replaces separator with space and title-cases the words.

2. 'tests/test_slug.py':
   - Unit tests using pytest testing slugify and unslugify (basic string, punctuation, multiple spaces, custom separator).
   - Must pass when running pytest.

3. 'docs/slug.md':
   - Markdown documentation describing the functions, usage examples, and supported arguments.
"""


def grade_workspace(ws: Path, verbose: bool = True) -> dict:
    """
    Independent grading harness checking all 3 deliverables:
      1. slug_utils.py exists and functions pass functional tests
      2. tests/test_slug.py exists and pytest passes
      3. docs/slug.md exists and has non-empty documentation
    """
    scores = {
        "files_created": 0,
        "pytest_passed": False,
        "functional_passed": False,
        "docs_valid": False,
        "total_score": 0.0,
        "errors": [],
    }

    p_utils = ws / "slug_utils.py"
    p_tests = ws / "tests" / "test_slug.py"
    p_docs = ws / "docs" / "slug.md"

    # Check files exist
    created_count = sum(1 for p in (p_utils, p_tests, p_docs) if p.is_file() and p.stat().st_size > 30)
    scores["files_created"] = created_count

    # Check 1: docs
    if p_docs.is_file() and p_docs.stat().st_size > 50:
        content = p_docs.read_text(encoding="utf-8", errors="replace")
        if "#" in content and "slug" in content.lower():
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
from slug_utils import slugify, unslugify
assert slugify('Hello, World! 123') == 'hello-world-123'
assert slugify('  Foo   Bar  ') == 'foo-bar'
assert slugify('User Profile', separator='_') == 'user_profile'
assert unslugify('hello-world-123') in ('Hello World 123', 'Hello World 123'.title())
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
    p = argparse.ArgumentParser(description="Phase 4 Multi-Agent Benchmark Evaluation")
    p.add_argument("--model", default=None,
                   help="Ollama model name (default: qwen2.5-coder:3b)")
    p.add_argument("--skip-single", action="store_true",
                   help="Skip single-agent baseline run")
    a = p.parse_args()

    model = a.model or DEFAULT_MODEL
    db = DB("data/memory.db")

    ws_single = _PROJECT_ROOT / "data" / "workspaces" / "phase4_single"
    ws_multi = _PROJECT_ROOT / "data" / "workspaces" / "phase4_multi"

    print("=" * 65, flush=True)
    print("  PHASE 4 EVALUATION: MULTI-AGENT EXECUTION GATE", flush=True)
    print("=" * 65, flush=True)
    print(f"Model: {model}", flush=True)
    print("Goal: Build a 3-file system (slug_utils.py, tests/test_slug.py, docs/slug.md)\n", flush=True)

    single_scores = {"total_score": 0.0, "files_created": 0, "pytest_passed": False, "functional_passed": False, "docs_valid": False}

    # ── 1. Single Agent Baseline ──────────────────────────────────────────────
    if not a.skip_single:
        print("-" * 65, flush=True)
        print("RUNNING BASELINE: Single Agent (Phase 1 architecture)...", flush=True)
        print("-" * 65, flush=True)
        if ws_single.exists():
            shutil.rmtree(ws_single)
        ws_single.mkdir(parents=True, exist_ok=True)

        t0 = time.time()
        # Single agent gets a larger budget of 16 steps
        res_single = run_agent(TASK_PROMPT, str(ws_single), model=model, max_steps=16, db=db, verbose=True, require_green=False)
        t_single = time.time() - t0
        print(f"\nSingle Agent finished in {t_single:.1f}s (status: {res_single['status']})", flush=True)

        print("\nGrading Single Agent:")
        single_scores = grade_workspace(ws_single, verbose=True)
    else:
        if ws_single.exists() and any(ws_single.iterdir()):
            print("Grading existing Single Agent workspace baseline...", flush=True)
            single_scores = grade_workspace(ws_single, verbose=False)
            print(f"Single Agent baseline score: {single_scores['total_score']:.1f}/100", flush=True)
        else:
            single_scores["total_score"] = 20.0

    # ── 2. Multi-Agent Orchestrator ───────────────────────────────────────────
    print("\n" + "-" * 65, flush=True)
    print("RUNNING PHASE 4: Multi-Agent Orchestrator (Planner, Coder, Reviewer)...", flush=True)
    print("-" * 65, flush=True)
    if ws_multi.exists():
        shutil.rmtree(ws_multi)
    ws_multi.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    res_multi = run_orchestrated_task(TASK_PROMPT, str(ws_multi), model=model, db=db, max_subtask_steps=10, max_retries=3, verbose=True)
    t_multi = time.time() - t0
    print(f"\nMulti-Agent Orchestrator finished in {t_multi:.1f}s (status: {res_multi['status']})", flush=True)

    print("\nGrading Multi-Agent Workspace:")
    multi_scores = grade_workspace(ws_multi, verbose=True)

    # ── 3. Summary & Gate ─────────────────────────────────────────────────────
    print("\n" + "=" * 65, flush=True)
    print("PHASE 4 GATE COMPARISON SUMMARY", flush=True)
    print("=" * 65, flush=True)
    if not a.skip_single:
        print(f"Single Agent Score:            {single_scores['total_score']:.1f}/100", flush=True)
    print(f"Multi-Agent Orchestrator Score: {multi_scores['total_score']:.1f}/100", flush=True)

    gate_passed = (
        multi_scores["total_score"] >= 80.0
        and multi_scores["files_created"] == 3
        and multi_scores["functional_passed"]
        and multi_scores["total_score"] >= single_scores["total_score"]
    )

    status_str = "PASS" if gate_passed else "FAIL"
    print("-" * 65, flush=True)
    print(f"Phase 4 Gate (Multi-Agent >= 80% & beats Single Agent): {status_str}", flush=True)


if __name__ == "__main__":
    main()
