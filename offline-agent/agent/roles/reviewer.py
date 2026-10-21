"""
reviewer.py – Reviewer / Tester role for Phase 4 multi-agent orchestration.

Executes the subtask's check_cmd in the jailed workspace. If the check fails,
analyzes the error trace and generates concise, actionable feedback for the Coder's retry.
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from agent.llm import chat, DEFAULT_MODEL

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
if not _VENV_PYTHON.exists():
    _VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
_PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable


def run_check(
    subtask: dict,
    workspace: Path | str,
    model: str = DEFAULT_MODEL,
    timeout: int = 60,
    verbose: bool = True,
) -> dict:
    """
    Execute subtask['check_cmd'] inside workspace.
    Returns: {"passed": bool, "output": str, "feedback": str}
    """
    ws = Path(workspace).resolve()
    cmd_str = (subtask.get("check_cmd") or "").strip()

    if not cmd_str:
        # If no check command was specified, default to pass if workspace exists
        return {"passed": True, "output": "No check_cmd specified.", "feedback": ""}

    try:
        from agent.security import validate_command, SecurityViolation
        args = validate_command(cmd_str, ws)
    except SecurityViolation as e:
        if verbose:
            print(f"[Reviewer] Security violation: {e}")
        return {
            "passed": False,
            "output": f"SECURITY ERROR: {e}",
            "feedback": f"Security violation: {e}. Check commands must stay inside the sandbox and use allowed tools only.",
        }
    except Exception as e:
        return {"passed": False, "output": f"ERROR: {e}", "feedback": str(e)}

    if verbose:
        print(f"[Reviewer] Running check: {' '.join(args[:6])} in {ws.name}")

    try:
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ws) + os.pathsep + env.get("PYTHONPATH", "")
        r = subprocess.run(
            args,
            cwd=ws,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        passed = (r.returncode == 0)
        output = (r.stdout + "\n" + r.stderr).strip()
    except subprocess.TimeoutExpired:
        passed = False
        output = f"ERROR: check command timed out after {timeout}s."
    except Exception as e:
        passed = False
        output = f"ERROR running check command: {e}"

    feedback = ""
    if not passed:
        # Generate targeted 1-2 sentence feedback for the coder
        prompt = (
            f"Subtask: {subtask.get('title')}\n"
            f"Spec: {subtask.get('spec')}\n"
            f"Check command: {cmd_str}\n"
            f"Failure output:\n{output[-1500:]}\n\n"
            "In 1 to 2 short sentences, explain exactly what failed and what the Coder "
            "must change to make this check pass on the next attempt."
        )
        try:
            feedback = chat([{"role": "user", "content": prompt}], model=model, json_mode=False).strip()
        except Exception:
            feedback = f"Check command failed: {output[-300:]}"

        if verbose:
            print(f"[Reviewer] Check FAIL (exit {getattr(r, 'returncode', -1)})")
            print(f"[Reviewer] Feedback: {feedback[:120]}")
    else:
        if verbose:
            print("[Reviewer] Check PASS [OK]")

    return {
        "passed": passed,
        "output": output,
        "feedback": feedback,
    }
