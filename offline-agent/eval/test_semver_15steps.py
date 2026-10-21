"""
test_semver_15steps.py – Evaluates parse_semver with max_steps=15 across 3 runs.

Tests whether 10 steps was the bottleneck for the 3B model or if
parse_semver is a legitimate hard task for the learning loop.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import time

from agent.llm import DEFAULT_MODEL
from agent.loop import run_agent
from eval.benchmark_suite import BENCHMARK_TASKS, setup_benchmark_task, grade_benchmark_task
from memory.db import DB

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_single(task_def: dict, ws_dir: Path, db: DB, model: str = DEFAULT_MODEL, max_steps: int = 15) -> dict:
    if ws_dir.exists():
        shutil.rmtree(ws_dir)
    ws_dir.mkdir(parents=True, exist_ok=True)

    orig_tests = setup_benchmark_task(task_def, ws_dir)

    t0 = time.time()
    agent_outcome = run_agent(
        task=task_def["prompt"],
        workspace=ws_dir,
        model=model,
        db=db,
        max_steps=max_steps,
        verbose=True,
        require_green=True,
    )
    duration = round(time.time() - t0, 2)

    grade = grade_benchmark_task(task_def, ws_dir, orig_tests)

    task_id = agent_outcome.get("task_id")
    steps = db.get_steps(task_id) if task_id else []

    guard_no_change_count = sum(1 for s in steps if "NO CHANGE:" in s.get("observation", ""))
    guard_hint_count = sum(1 for s in steps if "HINT: find the assertion" in s.get("observation", ""))
    guard_fired = (guard_no_change_count > 0) or (guard_hint_count > 0)

    return {
        "task_id": task_id,
        "name": task_def["name"],
        "id": task_def["id"],
        "status": agent_outcome.get("status"),
        "passed": grade["passed"],
        "score": grade["score"],
        "reason": grade.get("reason", ""),
        "duration": duration,
        "step_count": len(steps),
        "guard_fired": guard_fired,
        "guard_no_change": guard_no_change_count,
        "guard_hint": guard_hint_count,
        "steps": steps,
    }


def main():
    db_path = _PROJECT_ROOT / "data" / "memory.db"
    db = DB(str(db_path))
    model = DEFAULT_MODEL

    base_dir = _PROJECT_ROOT / "data" / "workspaces" / "semver_15steps"
    base_dir.mkdir(parents=True, exist_ok=True)

    task_map = {t["id"]: t for t in BENCHMARK_TASKS}
    semver_task = task_map["parse_semver"]

    print("=" * 65)
    print("TESTING parse_semver AT 15 STEPS (3 RUNS)")
    print("=" * 65)

    results = []
    for run_i in range(1, 4):
        ws = base_dir / f"run{run_i}"
        print(f"\n--- [parse_semver Run {run_i}/3] Workspace: {ws.name} | max_steps=15 ---")
        res = run_single(semver_task, ws, db, model=model, max_steps=15)
        results.append(res)
        status_mark = "PASS [OK]" if res["passed"] else "FAIL [X]"
        print(f"\nResult: {status_mark} | Status: {res['status']} | Steps: {res['step_count']} | Time: {res['duration']}s | Guard Fired: {res['guard_fired']}")

    out_file = _PROJECT_ROOT / "eval" / "semver_15steps_results.json"
    out_file.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nStructured results saved to: {out_file}")


if __name__ == "__main__":
    main()
