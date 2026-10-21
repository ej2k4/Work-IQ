"""
orchestrator.py – Phase 4 Multi-agent task graph orchestrator.

Coordinates Planner, Researcher, Coder, and Reviewer sequentially through
a shared SQLite task graph (subtasks and subtask_deps tables).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from agent.llm import chat, DEFAULT_MODEL
from agent.roles.planner import plan_task
from agent.roles.researcher import build_research_context
from agent.roles.coder import run_coder_subtask
from agent.roles.reviewer import run_check
from memory.db import DB


def run_orchestrated_task(
    task: str,
    workspace: Path | str,
    model: str = DEFAULT_MODEL,
    db: DB | None = None,
    max_subtask_steps: int = 10,
    max_retries: int = 3,
    enable_learning: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Run multi-agent execution on a task using the SQLite task graph.

    Protocol:
      1. Planner decomposes task into subtasks + dependency graph.
      2. Loop:
         a. Pick ready subtask (pending + all dependencies done).
         b. Researcher gathers context from memory and graph.
         c. Coder attempts subtask within step budget.
         d. Reviewer executes check_cmd.
            - Pass: subtask -> done.
            - Fail: Reviewer produces feedback, Coder retries (max_retries).
      3. Save reflection lesson and Obsidian task note if configured.
    """
    ws = Path(workspace).resolve()
    ws.mkdir(parents=True, exist_ok=True)

    model = model or DEFAULT_MODEL

    if db is None:
        db = DB()

    task_id = db.start_task(task, model)
    if verbose:
        print("=" * 65)
        print(f"  ORCHESTRATOR: Starting Task #{task_id}")
        print(f"  Goal: {task}")
        print("=" * 65)

    # ── 1. Planning ──────────────────────────────────────────────────────────
    subtasks = plan_task(
        task=task,
        workspace=ws,
        db=db,
        task_id=task_id,
        model=model,
        verbose=verbose,
    )

    if not subtasks:
        db.finish_task(task_id, "failed", "Planner produced no subtasks")
        return {"status": "failed", "task_id": task_id, "subtasks": []}

    # ── 2. Execution Loop ────────────────────────────────────────────────────
    while True:
        ready = db.get_ready_subtasks(task_id)

        if not ready:
            all_s = db.get_subtasks(task_id)
            all_done = all(s["status"] == "done" for s in all_s)
            any_failed = any(s["status"] == "failed" for s in all_s)

            if all_done:
                break
            elif any_failed:
                if verbose:
                    print("\n[Orchestrator] One or more subtasks failed permanently.")
                break
            else:
                # Deadlock: pending subtasks remain but dependencies cannot be satisfied
                if verbose:
                    print("\n[Orchestrator] Deadlock detected in subtask dependency graph.")
                break

        curr_subtask = ready[0]
        sid = curr_subtask["id"]
        title = curr_subtask["title"]

        if verbose:
            print("\n" + "-" * 60)
            print(f"[Orchestrator] Dispatching Subtask #{sid}: {title}")
            print("-" * 60)

        # Retry loop for current subtask
        feedback = curr_subtask.get("feedback") or ""
        subtask_passed = False

        for attempt in range(1, max_retries + 1):
            db.update_subtask_status(sid, "running", feedback=feedback)

            # Researcher builds context
            research_context = build_research_context(curr_subtask, db, workspace=ws, enable_learning=enable_learning)

            # Coder implements subtask
            coder_res = run_coder_subtask(
                subtask=curr_subtask,
                workspace=ws,
                research_context=research_context,
                reviewer_feedback=feedback,
                db=db,
                model=model,
                max_steps=max_subtask_steps,
                verbose=verbose,
            )

            # Reviewer evaluates check_cmd
            review = run_check(
                subtask=curr_subtask,
                workspace=ws,
                model=model,
                verbose=verbose,
            )

            if review["passed"]:
                db.update_subtask_status(
                    sid,
                    "done",
                    result_summary=coder_res.get("summary", ""),
                    feedback="",
                    increment_attempt=True,
                )
                subtask_passed = True
                if verbose:
                    print(f"[Orchestrator] Subtask #{sid} marked DONE.")
                break
            else:
                feedback = review["feedback"]
                if attempt < max_retries:
                    db.update_subtask_status(
                        sid,
                        "pending",
                        feedback=feedback,
                        increment_attempt=True,
                    )
                    if verbose:
                        print(f"[Orchestrator] Subtask #{sid} failed check. Retrying (attempt {attempt+1}/{max_retries})...")
                else:
                    db.update_subtask_status(
                        sid,
                        "failed",
                        feedback=feedback,
                        increment_attempt=True,
                    )
                    if verbose:
                        print(f"[Orchestrator] Subtask #{sid} exceeded max retries. Marked FAILED.")

        if not subtask_passed:
            # Stop execution if an essential subtask failed
            break

    # ── 3. Finalization & Reflection ─────────────────────────────────────────
    final_subtasks = db.get_subtasks(task_id)
    overall_passed = all(s["status"] == "done" for s in final_subtasks)
    status_str = "finished" if overall_passed else "failed"

    summary_lines = [f"- [{s['status'].upper()}] {s['title']}: {s.get('result_summary') or 'done'}"
                     for s in final_subtasks]
    overall_summary = "\n".join(summary_lines)

    if overall_passed:
        # Save reflection lesson using learning module
        try:
            from agent.learning import reflect_on_success
            lesson = reflect_on_success(task, overall_summary, model=model, db=db, task_id=task_id, verbose=verbose)
        except Exception:
            lesson = ""
    else:
        # Save pitfall from failed subtask to prevent repeating the same mistake
        failed_s = next((s for s in final_subtasks if s["status"] == "failed"), None)
        if failed_s:
            try:
                from agent.learning import reflect_on_failure
                err = failed_s.get("feedback") or "Subtask exceeded max retries."
                reflect_on_failure(task, failed_s, err, model=model, db=db, task_id=task_id, verbose=verbose)
            except Exception:
                pass

    # Obsidian write-back if vault configured
    vault_dir = os.environ.get("OBSIDIAN_VAULT")
    if vault_dir and Path(vault_dir).is_dir():
        try:
            from memory.obsidian import write_agent_note
            p = write_agent_note(
                vault_dir=vault_dir,
                task_id=task_id,
                task=task,
                status=status_str,
                summary=overall_summary,
                lesson=lesson if 'lesson' in locals() else "",
                touched_files=[str(f.name) for f in ws.glob("*.py")],
                db=db,
            )
            if verbose:
                print(f"[Orchestrator] Obsidian note recorded: {p.name}")
        except Exception as e:
            if verbose:
                print(f"[Orchestrator] Obsidian note write failed: {e}")

    db.finish_task(task_id, status_str, overall_summary)

    if verbose:
        print("\n" + "=" * 65)
        print(f"  TASK #{task_id} OUTCOME: {status_str.upper()}")
        print(f"  Subtasks: {sum(1 for s in final_subtasks if s['status'] == 'done')}/{len(final_subtasks)} completed")
        print("=" * 65)

    return {
        "status": status_str,
        "task_id": task_id,
        "subtasks": final_subtasks,
        "passed": overall_passed,
        "summary": overall_summary,
    }
