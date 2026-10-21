"""
loop.py – The core agent tool-use loop.

Protocol: the model returns exactly ONE JSON object per turn:
    {"thought": "<one short sentence>", "tool": "<name>", "args": {...}}

Safety mechanisms:
- max_steps cap
- repeat detection (same call 4 times in a row → stuck)
- finish guard (finish rejected unless run_tests passed after last write_file)
- invalid-JSON recovery (fed back as an error observation)
"""
import json
import os
from pathlib import Path

import requests

from agent.llm import chat, DEFAULT_MODEL
from agent.tools import Tools

SYSTEM = """You are a coding agent working inside a project folder.
Each turn you reply with exactly ONE JSON object and nothing else:
{"thought": "<one short sentence>", "tool": "<tool name>", "args": {...}}

Available tools:
- list_dir      {"path": "."}
- read_file     {"path": "file.py"}
- write_file    {"path": "file.py", "content": "<the ENTIRE new file content>"}
- run_tests     {"path": "test_file.py"}   (ALWAYS pass the specific test file name)
- search_memory {"query": "<natural language>", "top_k": 5}  (find relevant code/docs)
- query_graph   {"symbol": "<func or class name>", "hops": 2} (find callers & dependencies)
- finish        {"summary": "<what you changed>"}

Rules:
1. Start by listing the directory, then read the failing test and the source it imports.
   Use search_memory when you need to locate code, definitions, or documentation across the project.
2. write_file replaces the WHOLE file — include every line, not just your change.
3. ALWAYS run_tests with the SPECIFIC test file from your task — never run all tests.
4. Only call finish after the target test file passes.
5. Never edit test files. Fix the source code only.
6. If a tool returns an error, read the message carefully and correct your approach.
7. Focus only on fixing the source file imported by the target test. Ignore failures in other test files."""


def run_agent(task, workspace, model=None, max_steps=12, db=None,
              verbose=True, require_green=True, system_prompt=None,
              allowed_write_files=None):
    """
    Run the agent loop on a task inside the given workspace directory.

    Args:
        task:                Natural-language task description.
        workspace:           Path to the project folder (will be created if absent).
        model:               Ollama model name; falls back to DEFAULT_MODEL.
        max_steps:           Maximum tool-call iterations before giving up.
        db:                  Optional DB instance for persistent logging.
        verbose:             Print each step to stdout if True.
        require_green:       Reject 'finish' unless tests passed after last write.
        system_prompt:       Optional custom system prompt (defaults to SYSTEM).
        allowed_write_files: Optional set/list of allowed write file targets.

    Returns:
        dict with keys: status ("finished"|"stuck"|"max_steps"),
                        summary (str), task_id (int|None).
    """
    model = model or DEFAULT_MODEL
    tools = Tools(workspace, db=db, allowed_write_files=allowed_write_files)
    task_id = db.start_task(task, model) if db else None

    sys_content = system_prompt or SYSTEM
    messages = [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": f"Task: {task}"},
    ]

    def end(status, summary="", lesson=""):
        vault_dir = os.environ.get("OBSIDIAN_VAULT")
        if vault_dir and Path(vault_dir).is_dir():
            try:
                from memory.obsidian import write_agent_note
                p = write_agent_note(
                    vault_dir=vault_dir,
                    task_id=task_id or 1,
                    task=task,
                    status=status,
                    summary=summary,
                    lesson=lesson,
                    touched_files=list(tools.touched_files),
                    db=db,
                )
                if verbose:
                    print(f"    [obsidian] note recorded: {p.name}")
            except Exception as e:
                if verbose:
                    print(f"    [obsidian] note write failed: {e}")
        if db:
            db.finish_task(task_id, status, summary)
        return {"status": status, "summary": summary, "task_id": task_id}

    # Repeat detection: track (tool, args) pairs
    last_key = None
    repeats = 0
    REPEAT_LIMIT = 3
    from agent.context_manager import ContextManager
    from agent.stall_guard import StallGuard
    ctx_mgr = ContextManager(max_context_tokens=5500, keep_recent_pairs=3)
    guard = StallGuard()

    for n in range(1, max_steps + 1):
        # ── Context budget management & summarization ───────────────────────
        messages = ctx_mgr.prune_or_summarize(messages)

        # ── Model call ──────────────────────────────────────────────────────
        try:
            raw = chat(messages, model=model, json_mode=True, temperature=guard.temperature)
        except requests.HTTPError as e:
            obs = (
                f"ERROR: model server returned {e.response.status_code}. "
                "The context may be too long. Summarise and retry."
            )
            messages.append({"role": "user", "content": obs})
            if db:
                db.log_step(task_id, n, "llm_error", {}, obs)
            if verbose:
                print(f"[{n}] <LLM HTTP error {e.response.status_code}>")
            continue
        except requests.ConnectionError as e:
            if db:
                db.finish_task(task_id, "error", str(e))
            raise
        # ── Parse action ────────────────────────────────────────────────────
        cleaned_raw = raw.strip()
        if cleaned_raw.startswith("```"):
            lines = cleaned_raw.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned_raw = "\n".join(lines).strip()

        try:
            action = json.loads(cleaned_raw, strict=False)
            tool = action["tool"]
            args = action.get("args") or {}
            if not isinstance(args, dict):
                raise ValueError("'args' must be a JSON object")
        except Exception as e:
            obs = (
                f"ERROR: invalid reply ({e}). "
                "Reply with exactly one JSON object containing 'tool' and 'args' keys."
            )
            messages.append({"role": "user", "content": obs})
            if db:
                db.log_step(task_id, n, "invalid_json", {}, obs)
            if verbose:
                print(f"[{n}] <invalid JSON>: {str(e)[:80]}")
            continue

        messages.append({"role": "assistant", "content": raw})

        if verbose:
            print(f"[{n}] {tool} {json.dumps(args)[:120]}")

        # ── Repeat detection ─────────────────────────────────────────────────
        key = (tool, json.dumps(args, sort_keys=True))
        if key == last_key:
            repeats += 1
        else:
            repeats = 0
        last_key = key

        if repeats >= REPEAT_LIMIT:
            if db:
                db.log_step(task_id, n, tool, args, "stuck: repeat detected")
            return end("stuck", f"same action repeated {repeats + 1} times in a row")

        # ── Dispatch ─────────────────────────────────────────────────────────
        if tool == "finish":
            if require_green and not tools.tests_green:
                obs = (
                    "REJECTED: tests have not passed since your last change. "
                    "Run the tests first, fix any failures, then call finish."
                )
                messages.append({"role": "user", "content": f"OBSERVATION from finish:\n{obs}"})
                if db:
                    db.log_step(task_id, n, tool, args, obs)
                if verbose:
                    print("    ->", obs)
                continue
            else:
                summary = str(args.get("summary", ""))
                if db:
                    db.log_step(task_id, n, tool, args, "accepted")
                # ── Record touched files in task graph (Phase 3) ────────────
                if db and task_id:
                    for f in tools.touched_files:
                        db.record_task_touched_file(task_id, f)
                # ── Reflection: save a verified lesson ──────────────────────
                lesson = ""
                if db and task_id and tools.tests_green:
                    try:
                        lesson_prompt = (
                            f"The agent just fixed a bug. Task: {task}\n"
                            f"Summary: {summary}\n"
                            "In one sentence, what is the key lesson or pattern "
                            "that will help fix similar bugs faster next time?"
                        )
                        lesson = chat(
                            [{"role": "user", "content": lesson_prompt}],
                            model=model,
                            json_mode=False,
                        ).strip()
                        if lesson:
                            db.save_fact(task_id, "lesson", lesson)
                            if verbose:
                                print(f"    [reflection] lesson saved: {lesson[:80]}")
                    except Exception:
                        pass  # reflection is best-effort; never block finish
                return end("finished", summary, lesson=lesson)
        else:
            obs = tools.call(tool, args)
            res = guard.after_step(tool, args, obs)
            obs = res["obs"]
            if res["abort"]:
                if db:
                    db.log_step(task_id, n, tool, args, f"stuck: {res['reason']}")
                return end("stuck", res["reason"])

        if db:
            db.log_step(task_id, n, tool, args, obs)
        if verbose:
            print("    ->", obs.replace("\n", " | ")[:160])
        messages.append({"role": "user", "content": f"OBSERVATION from {tool}:\n{obs}"})

    return end("max_steps", "ran out of steps")
