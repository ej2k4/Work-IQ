"""
obsidian.py – Obsidian vault integration for Phase 3.

Read path:
  - Indexes vault markdown notes into documents ('kind=note').
  - Extracts [[wikilinks]] and #tags into nodes and edges graph.
  - Embeds note sections for semantic retrieval.

Write path:
  - Agent write-back is strictly jailed to <vault>/Agent/.
  - Writes task notes with YAML frontmatter, summary, lessons, and [[links]].
"""
from __future__ import annotations

import datetime
import hashlib
import os
import re
from pathlib import Path
from typing import Optional

from memory.db import DB
from memory.graph import index_markdown_concept_graph
from memory.vectors import chunk_text, embed_to_bytes, EMBED_MODEL


def get_vault_path() -> Path | None:
    """Return Path to OBSIDIAN_VAULT environment variable if configured and exists."""
    v = os.environ.get("OBSIDIAN_VAULT")
    if not v:
        return None
    p = Path(v).resolve()
    return p if p.is_dir() else None


def index_vault(
    vault_dir: Path | str,
    db: DB,
    embed_model: str = EMBED_MODEL,
    verbose: bool = False,
) -> dict:
    """
    Index all markdown notes in an Obsidian vault:
      - Store documents (kind='note')
      - Chunk sections & store vector embeddings
      - Parse [[wikilinks]] and #tags into graph nodes & edges
    """
    root = Path(vault_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"Vault directory does not exist: {vault_dir}")

    stats = {"notes": 0, "chunks": 0, "nodes": 0, "edges": 0}

    for fpath in sorted(root.rglob("*.md")):
        if not fpath.is_file():
            continue
        rel_parts = fpath.relative_to(root).parts
        # Skip hidden folders (.obsidian, .trash)
        if any(p.startswith(".") for p in rel_parts):
            continue

        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            if verbose:
                print(f"Error reading note {fpath}: {e}")
            continue

        rel_path = str(fpath.relative_to(root)).replace("\\", "/")
        content_hash = hashlib.sha1(content.encode("utf-8")).hexdigest()

        # 1. Store document
        doc_id, changed = db.upsert_document(
            path=rel_path,
            source=f"vault:{root.name}",
            kind="note",
            content_hash=content_hash,
        )
        stats["notes"] += 1

        # 2. Chunk & embed if changed
        if changed:
            chunks = chunk_text(content)
            chunk_ids = db.insert_chunks(doc_id, chunks)
            for cid, c in zip(chunk_ids, chunks):
                try:
                    vec_bytes = embed_to_bytes(c["text"], model=embed_model)
                    db.insert_embedding(cid, embed_model, vec_bytes)
                    stats["chunks"] += 1
                except Exception as e:
                    if verbose:
                        print(f"Embedding failed for note chunk: {e}")

        # 3. Graph index (wikilinks & tags)
        gres = index_markdown_concept_graph(fpath, content, db, root_path=root)
        stats["nodes"] += gres["nodes"]
        stats["edges"] += gres["edges"]

    if verbose:
        print(f"Obsidian vault indexed: {stats}")
    return stats


def write_agent_note(
    vault_dir: Path | str,
    task_id: int,
    task: str,
    status: str,
    summary: str = "",
    lesson: str = "",
    touched_files: list[str] | None = None,
    db: DB | None = None,
) -> Path:
    """
    Write a structured task report note into <vault>/Agent/Task-{task_id}.md.

    Enforces strict jail: cannot write outside <vault>/Agent/.
    """
    root = Path(vault_dir).resolve()
    agent_dir = (root / "Agent").resolve()
    agent_dir.mkdir(parents=True, exist_ok=True)

    filename = f"Task-{task_id}.md"
    target_path = (agent_dir / filename).resolve()

    # Safety check: target MUST be directly inside agent_dir
    if agent_dir not in target_path.parents and target_path.parent != agent_dir:
        raise ValueError(f"Security violation: attempt to write note outside Agent directory: {target_path}")

    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    files_list = touched_files or []

    # Format YAML frontmatter and Markdown body
    files_yaml = "\n".join(f"  - \"[[{f}]]\"" for f in files_list) if files_list else "  []"
    frontmatter = f"""---
task_id: {task_id}
date: {now_iso}
status: {status}
files:
{files_yaml}
tags:
  - agent/task
  - status/{status}
---
"""

    links_section = ""
    if files_list:
        links_section = "\n## Touched Files\n" + "\n".join(f"- [[{f}]]" for f in files_list) + "\n"

    lesson_section = ""
    if lesson:
        lesson_section = f"\n## Key Lesson\n> {lesson}\n"

    body = f"""# Task {task_id}: {task}

**Status:** `{status}`  
**Recorded:** {now_iso}

## Summary
{summary or "No summary provided."}
{lesson_section}{links_section}
"""

    full_text = frontmatter + "\n" + body
    target_path.write_text(full_text, encoding="utf-8")

    # Update DB graph if db provided
    if db:
        note_name = f"Task-{task_id}"
        note_ref = f"Agent/{filename}"
        note_node = db.upsert_node("note", note_name, note_ref)
        tag_node = db.upsert_node("tag", f"#status/{status}", f"tag:status/{status}")
        db.add_edge(note_node, tag_node, "tagged")
        for f in files_list:
            f_node = db.upsert_node("file", Path(f).name, f)
            db.add_edge(note_node, f_node, "links_to")
    # Update Agent/INDEX.md dashboard
    try:
        update_vault_index(root)
    except Exception as e:
        pass

    return target_path


def update_vault_index(vault_dir: Path | str) -> Path:
    """
    Generate or update <vault>/Agent/INDEX.md listing all recorded agent tasks.
    """
    root = Path(vault_dir).resolve()
    agent_dir = root / "Agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    index_file = agent_dir / "INDEX.md"

    task_files = sorted(agent_dir.glob("Task-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    records = []
    lessons = []
    status_counts: dict[str, int] = {}

    for tf in task_files:
        try:
            content = tf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Extract frontmatter fields
        fm_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
        tid_match = re.search(r"task_id:\s*(\d+)", fm_match.group(1)) if fm_match else None
        date_match = re.search(r"date:\s*(.+)", fm_match.group(1)) if fm_match else None
        status_match = re.search(r"status:\s*(\w+)", fm_match.group(1)) if fm_match else None

        # Extract title from first markdown header
        h_match = re.search(r"^# Task \d+:\s*(.+)$", content, re.MULTILINE)
        task_title = h_match.group(1).strip() if h_match else tf.stem

        # Extract lesson
        lesson_match = re.search(r"## Key Lesson\n>\s*(.+)", content)
        lesson_text = lesson_match.group(1).strip() if lesson_match else ""

        tid = tid_match.group(1) if tid_match else tf.stem.replace("Task-", "")
        dt = date_match.group(1).strip() if date_match else ""
        st = status_match.group(1).strip() if status_match else "unknown"

        status_counts[st] = status_counts.get(st, 0) + 1
        records.append({
            "id": tid,
            "date": dt,
            "title": task_title,
            "status": st,
            "stem": tf.stem,
            "lesson": lesson_text,
        })
        if lesson_text:
            lessons.append((tid, lesson_text))

    # Format Markdown dashboard
    stats_lines = [f"- **Total Tasks**: {len(records)}"]
    for s, c in sorted(status_counts.items()):
        stats_lines.append(f"- **{s.capitalize()}**: {c}")
    stats_md = "\n".join(stats_lines)

    rows = []
    for r in records:
        status_tag = f"#status/{r['status']}"
        link = f"[[{r['stem']}]]"
        short_lesson = r['lesson'][:60] + "..." if len(r['lesson']) > 60 else r['lesson']
        rows.append(f"| {r['id']} | {r['date']} | {r['title']} | `{r['status']}` | {link} | {short_lesson} |")

    table_md = "| ID | Date | Task | Status | Note | Key Lesson |\n| :---: | :---: | :--- | :---: | :---: | :--- |\n" + "\n".join(rows) if rows else "_No tasks recorded yet._"

    lessons_md = ""
    if lessons:
        lesson_items = [f"- **[[Task-{tid}]]**: {les}" for tid, les in lessons[:10]]
        lessons_md = "\n## Recent Verified Lessons\n" + "\n".join(lesson_items) + "\n"

    body = f"""---
tags:
  - agent/dashboard
  - agent/index
---

# Agent Task Dashboard

Auto-generated overview and Map of Content (MOC) of all offline agent tasks.

## Statistics
{stats_md}

## Task Log
{table_md}
{lessons_md}
"""
    index_file.write_text(body, encoding="utf-8")
    return index_file


def main():
    import argparse
    p = argparse.ArgumentParser(description="Obsidian vault manager for offline coding agent.")
    p.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT"), help="Path to Obsidian vault")
    p.add_argument("--index", action="store_true", help="Index all markdown notes in vault into vector memory & concept graph")
    p.add_argument("--db", default="data/memory.db", help="Path to SQLite memory database")
    p.add_argument("--update-index", action="store_true", help="Rebuild Agent/INDEX.md task dashboard")
    args = p.parse_args()

    if not args.vault:
        p.error("Vault path must be provided via --vault or OBSIDIAN_VAULT environment variable.")

    vpath = Path(args.vault).resolve()
    if not vpath.is_dir():
        p.error(f"Vault directory not found: {vpath}")

    if args.index:
        db = DB(args.db)
        print(f"Indexing Obsidian vault: {vpath} ...")
        stats = index_vault(vpath, db=db, verbose=True)
        print(f"Indexing complete: {stats}")

    if args.update_index:
        idx_p = update_vault_index(vpath)
        print(f"Updated Agent task dashboard: {idx_p}")


if __name__ == "__main__":
    main()

