"""
planner.py – Planner role for Phase 4 multi-agent orchestration.

Decomposes a complex multi-file task into 2-4 ordered, verifiable subtasks,
each with a concrete check_cmd (e.g. pytest or python check) and dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path

from agent.llm import chat, DEFAULT_MODEL
from memory.db import DB

PLANNER_SYSTEM = """You are a software architect and task planner.
Your job is to break a programming task down into 2 to 4 small, focused, sequential subtasks.
Each subtask must touch 1 file at most and have a clear, automated check command (check_cmd) appropriate for that file.

Return ONLY a JSON object with this exact structure:
{
  "subtasks": [
    {
      "title": "Create slug_utils.py",
      "spec": "Implement slugify(text: str, separator: str = '-') -> str and unslugify(slug: str, separator: str = '-') -> str in slug_utils.py. In slugify: cleaned = ''.join(c.lower() if c.isalnum() or c in ' _-' else '' for c in text); words = [w for w in cleaned.replace('_', ' ').replace('-', ' ').split() if w]; return separator.join(words). In unslugify: words = [w.capitalize() for w in slug.split(separator) if w]; return ' '.join(words).",
      "check_cmd": "python -c \\"from slug_utils import slugify, unslugify; assert slugify('Hello, World! 123') == 'hello-world-123' and unslugify('hello-world') == 'Hello World'\\"",
      "depends_on": []
    },
    {
      "title": "Create tests/test_slug.py",
      "spec": "Write unit tests for slugify and unslugify using pytest in tests/test_slug.py. Include test_slugify (testing basic string 'hello world' -> 'hello-world', punctuation 'hello, world!' -> 'hello-world', multiple whitespace 'foo   bar' -> 'foo-bar', custom separator separator='_') and test_unslugify (testing 'hello-world' -> 'Hello World', custom separator 'hello_world' -> 'Hello World'). All tests must pass with pytest.",
      "check_cmd": "python -m pytest tests/test_slug.py -q",
      "depends_on": [0]
    },
    {
      "title": "Create docs/slug.md",
      "spec": "Create markdown documentation in docs/slug.md with header '# Slug Utils Documentation', detailing slugify and unslugify parameters, default separator '-', return types, and usage examples.",
      "check_cmd": "python -c \\"import os; assert os.path.isfile('docs/slug.md') and os.path.getsize('docs/slug.md') > 30\\"",
      "depends_on": [0]
    }
  ]
}

Rules:
1. Break multi-file tasks into 1 file per subtask.
2. In 'spec', ALWAYS preserve full function signatures, parameters, default arguments, and behavior requirements from the goal.
3. For implementation/module files: verify key functions with a python assertion testing both a standard case and an empty/default case (e.g. python -c "from module import func; assert func(...) == expected and func('') == default").
4. For test files: use pytest (e.g. python -m pytest tests/test_file.py -q).
5. For markdown/doc files: check file existence and size (e.g. python -c "import os; assert os.path.isfile('path') and os.path.getsize('path') > 30"). Never use echo, cat, or shell redirects.
6. 'depends_on' uses 0-based indices pointing to earlier items in the array.
7. Return ONLY the JSON object, with no other text."""


def plan_task(
    task: str,
    workspace: Path | str,
    db: DB,
    task_id: int,
    model: str = DEFAULT_MODEL,
    verbose: bool = True,
) -> list[dict]:
    """
    Generate subtasks for task, record them in SQLite task graph, and return them.
    """
    ws = Path(workspace).resolve()
    model = model or DEFAULT_MODEL
    # Collect existing files in workspace to guide the planner
    existing_files = [
        str(p.relative_to(ws)).replace("\\", "/")
        for p in ws.rglob("*")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(ws).parts)
    ]
    file_list_str = "\n".join(f"- {f}" for f in existing_files) if existing_files else "(empty folder)"

    prompt = (
        f"Goal: {task}\n\n"
        f"Existing workspace files:\n{file_list_str}\n\n"
        "Plan the subtasks to accomplish this goal end-to-end. Return JSON object with 'subtasks' key."
    )

    if verbose:
        print("[Planner] Generating task decomposition...")

    subtasks_data: list[dict] = []

    for attempt in range(2):
        try:
            raw = chat(
                [
                    {"role": "system", "content": PLANNER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                json_mode=True,
            )
            data = json.loads(raw)
            if isinstance(data, list):
                subtasks_data = data
                break
            elif isinstance(data, dict):
                for key in ("subtasks", "tasks", "plan", "steps"):
                    if key in data and isinstance(data[key], list) and data[key]:
                        subtasks_data = data[key]
                        break
                if not subtasks_data and "title" in data:
                    subtasks_data = [data]
                if subtasks_data:
                    break
        except Exception as e:
            if verbose:
                print(f"[Planner] Attempt {attempt+1} parse error: {e}")

    # Fallback if model failed to return a valid list
    if not subtasks_data:
        subtasks_data = [{
            "title": "Complete task end-to-end",
            "spec": task,
            "check_cmd": "python -m pytest -q",
            "depends_on": [],
        }]

    # Insert subtasks into SQLite task graph
    db_subtask_ids: list[int] = []
    for s in subtasks_data:
        title = s.get("title", "Subtask")
        spec = s.get("spec", task)
        check_cmd = s.get("check_cmd", "")

        # Clean check_cmd for cross-platform robustness
        import re
        files_mentioned = re.findall(r'[\w\./\\]+\.(?:py|md|txt|rst)', f"{title} {spec}")
        target_file = files_mentioned[0] if files_mentioned else ""

        if any(bad in check_cmd for bad in ("echo", ">", "cat ", "type ")):
            if target_file.endswith(".md") or target_file.endswith(".txt"):
                check_cmd = f"python -c \"import os; assert os.path.isfile('{target_file}') and os.path.getsize('{target_file}') > 20\""
            elif target_file.endswith(".py"):
                mod_name = Path(target_file).stem
                check_cmd = f"python -c \"import {mod_name}\""
            else:
                check_cmd = ""
        elif "pytest" in check_cmd:
            if not check_cmd.startswith("python"):
                check_cmd = f"python -m {check_cmd}"
            # If subtask is not creating a test file, don't run pytest before the tests exist
            if target_file and not target_file.startswith("test") and "test" not in target_file:
                mod_name = Path(target_file).stem
                check_cmd = f"python -c \"import {mod_name}\""

        role = s.get("assigned_role", "coder")
        sid = db.create_subtask(task_id, title, spec, check_cmd, assigned_role=role)
        db_subtask_ids.append(sid)
        if verbose:
            print(f"  [subtask {sid}] {title} (check: {check_cmd})")

    # Insert dependency edges
    for idx, s in enumerate(subtasks_data):
        curr_id = db_subtask_ids[idx]
        raw_deps = s.get("depends_on", [])
        if not isinstance(raw_deps, list):
            raw_deps = [raw_deps]

        for dep in raw_deps:
            parent_id = None
            if isinstance(dep, int) and 0 <= dep < len(db_subtask_ids) and dep != idx:
                parent_id = db_subtask_ids[dep]
            elif isinstance(dep, str):
                # Match string against earlier subtask titles
                for p_idx, prev_s in enumerate(subtasks_data[:idx]):
                    p_title = prev_s.get("title", "").lower()
                    p_spec = prev_s.get("spec", "").lower()
                    if dep.lower() in p_title or dep.lower() in p_spec:
                        parent_id = db_subtask_ids[p_idx]
                        break

            if parent_id and parent_id != curr_id:
                db.add_subtask_dep(curr_id, parent_id)
                if verbose:
                    print(f"    dep: subtask {curr_id} -> depends on subtask {parent_id}")

    return db.get_subtasks(task_id)
