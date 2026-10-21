"""
coder.py – Coder role for Phase 4 multi-agent orchestration.

Executes the tool-use loop on a single subtask, armed with Researcher context
and Reviewer feedback (on retries).
"""
from __future__ import annotations

from pathlib import Path

from agent.llm import DEFAULT_MODEL
from agent.loop import run_agent
from memory.db import DB


import re

CODER_SYSTEM = """You are an expert software developer working on a specific subtask.
You use file and testing tools to inspect the workspace, create or update files, and verify your implementation.

Available tools:
  list_dir(path=".")
  read_file(path)
  write_file(path, content)
  run_tests(path="")
  search_memory(query, top_k)
  query_graph(symbol, hops)
  finish(summary)

Rules:
1. Focus strictly on completing your assigned subtask and writing your assigned target file.
2. write_file replaces the WHOLE file — write the complete, working implementation directly.
3. If your subtask is to write a module, implement the required functions cleanly.
4. If your subtask is to write tests, write clean pytest test functions covering the specified behaviors.
5. If your subtask is documentation, write clean, complete Markdown documentation into the target file.
6. When done, call finish with a concise summary.
7. Output ONLY the JSON tool-call object, with no markdown code fences or explanatory text.
"""


def run_coder_subtask(
    subtask: dict,
    workspace: Path | str,
    research_context: str = "",
    reviewer_feedback: str = "",
    db: DB | None = None,
    model: str = DEFAULT_MODEL,
    max_steps: int = 10,
    verbose: bool = True,
) -> dict:
    """
    Run the tool loop on a specific subtask with injected research and reviewer feedback.
    """
    ws = Path(workspace).resolve()

    # Extract target file to enforce isolation
    title = subtask.get("title", "")
    spec = subtask.get("spec", "")
    files_mentioned = re.findall(r'[\w\./\\]+\.(?:py|md|txt|rst)', f"{title} {spec}")
    target_file = files_mentioned[0] if files_mentioned else None
    allowed_writes = [target_file] if target_file else None

    prompt_parts = [
        f"Subtask: {title}",
        f"Requirements:\n{spec}",
    ]

    if target_file:
        prompt_parts.append(
            f"Target Deliverable File: {target_file}\n"
            f"- Write your implementation directly to '{target_file}' using write_file.\n"
            "- Do NOT modify or overwrite existing files from previous subtasks."
        )

    if research_context:
        prompt_parts.append(f"Research Context & Dependencies:\n{research_context}")

    if reviewer_feedback:
        prompt_parts.append(
            f"IMPORTANT: The previous attempt failed. Reviewer feedback:\n{reviewer_feedback}\n"
            "Address this feedback directly."
        )

    prompt_parts.append(
        "Instruction: Focus ONLY on completing this specific subtask. "
        "Do not write placeholder stubs; write the complete, working implementation directly using write_file. "
        "Run tests if this subtask involves testing, and call finish when done."
    )

    task_prompt = "\n\n".join(prompt_parts)

    if verbose:
        print(f"\n[Coder] Starting subtask: {title} (target: {target_file or 'any'})")

    # Run tool loop on the subtask; test subtasks require green tests before finish
    has_test_check = "pytest" in (subtask.get("check_cmd") or "")
    res = run_agent(
        task=task_prompt,
        workspace=str(ws),
        model=model,
        max_steps=max_steps,
        db=db,
        verbose=verbose,
        require_green=has_test_check,
        system_prompt=CODER_SYSTEM,
        allowed_write_files=allowed_writes,
    )

    return res
