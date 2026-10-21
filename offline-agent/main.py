"""
main.py – CLI entry point for the offline coding agent.

Usage:
    python main.py "Fix the bug in utils.py" --workspace C:\\path\\to\\project
    python main.py "Add a slugify function with tests" --workspace ./myproject --model qwen2.5-coder:7b
"""
import argparse
import sys

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from agent.loop import run_agent
from memory.db import DB


def main():
    p = argparse.ArgumentParser(
        description="Run the offline coding agent on a task.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "Fix failing tests in mathutils.py"
  python main.py "Add a slugify function with tests" --workspace ./myproject
  python main.py "Refactor stack.py" --model qwen2.5-coder:7b --max-steps 20
        """,
    )
    p.add_argument("task", help="Natural language description of the task")
    p.add_argument(
        "--workspace",
        default="data/workspaces/default",
        help="Path to the project folder the agent will work in (default: data/workspaces/default)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Ollama model name (default: AGENT_MODEL env var or qwen2.5-coder:3b)",
    )
    p.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Maximum tool-call steps before giving up (default: 12)",
    )
    p.add_argument(
        "--db",
        default="data/memory.db",
        help="Path to the SQLite memory database (default: data/memory.db)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-step output",
    )
    p.add_argument(
        "--multi-agent",
        action="store_true",
        help="Use Phase 4 multi-agent orchestrator (Planner, Researcher, Coder, Reviewer)",
    )
    p.add_argument(
        "--vault",
        default=None,
        help="Path to Obsidian vault (enables live task logging to Agent/ and concept graph)",
    )
    a = p.parse_args()

    if a.vault:
        import os
        from pathlib import Path
        os.environ["OBSIDIAN_VAULT"] = str(Path(a.vault).resolve())

    db = DB(a.db)
    if a.multi_agent:
        from agent.orchestrator import run_orchestrated_task
        result = run_orchestrated_task(
            a.task,
            a.workspace,
            model=a.model,
            db=db,
            max_subtask_steps=a.max_steps,
            verbose=not a.quiet,
        )
    else:
        result = run_agent(
            a.task,
            a.workspace,
            model=a.model,
            max_steps=a.max_steps,
            db=db,
            verbose=not a.quiet,
        )

    print("\n--- RESULT ---")
    print(f"Status  : {result['status']}")
    print(f"Summary : {result['summary']}")
    if result.get("task_id"):
        print(f"Task ID : {result['task_id']}  (query steps: SELECT * FROM steps WHERE task_id={result['task_id']})")
    sys.exit(0 if result["status"] == "finished" else 1)


if __name__ == "__main__":
    main()
