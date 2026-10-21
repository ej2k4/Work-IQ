"""
learning.py – Phase 5 Learning Loop for Offline Coding Agent.

Implements the three tiers from plan.md:
  1. Verified-experience memory:
     - reflect_on_success: stores verified lessons in facts (kind='lesson')
     - reflect_on_failure: stores anti-patterns in facts (kind='pitfall')
     - retrieve_learning_context: semantic cosine search over embedded facts
  2. Offline knowledge packs:
     - index_knowledge_pack: index curated documentation as documents (kind='doc')
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from agent.llm import chat, DEFAULT_MODEL
from memory.db import DB


def reflect_on_success(
    task: str,
    subtasks_summary: str,
    model: str = DEFAULT_MODEL,
    db: DB | None = None,
    task_id: int | None = None,
    verbose: bool = True,
) -> str:
    """
    Extract a generalizable, high-signal coding lesson from a successful task.
    Saves it to the DB facts table as kind='lesson' with vector embedding.
    """
    prompt = (
        f"A multi-agent coding team just successfully completed this task:\n"
        f"Goal: {task}\n"
        f"Subtasks:\n{subtasks_summary}\n\n"
        "In 1 to 2 short sentences, state the key coding rule, architectural pattern, "
        "or string/file handling practice that made this successful. "
        "Start with 'Lesson: '."
    )
    try:
        raw = chat([{"role": "user", "content": prompt}], model=model, json_mode=False).strip()
        lesson = raw.replace("\n", " ").strip()
        if not lesson.lower().startswith("lesson:"):
            lesson = f"Lesson: {lesson}"
    except Exception as e:
        lesson = f"Lesson: Modular separation of subtasks with test verification ensures end-to-end correctness ({e})."

    if db:
        try:
            tid = task_id or 1
            fact_id = db.save_fact(tid, "lesson", lesson, embed_now=True)
            if verbose:
                print(f"[Learning] Saved verified lesson #{fact_id}: {lesson[:90]}...")
        except Exception as e:
            if verbose:
                print(f"[Learning] Note: could not save fact: {e}")

    return lesson


def reflect_on_failure(
    task: str,
    subtask: dict,
    error_output: str,
    model: str = DEFAULT_MODEL,
    db: DB | None = None,
    task_id: int | None = None,
    verbose: bool = True,
) -> str:
    """
    Extract a concrete anti-pattern or trap from a failed subtask or test failure.
    Saves it to the DB facts table as kind='pitfall' with vector embedding.
    """
    title = subtask.get("title", "Subtask")
    spec = subtask.get("spec", "")
    prompt = (
        f"A coding agent failed to complete this subtask:\n"
        f"Subtask: {title}\n"
        f"Spec: {spec}\n"
        f"Failure output:\n{error_output[-1200:]}\n\n"
        "In 1 to 2 short sentences, identify the exact bug, regex trap, or mistake "
        "that caused the failure, and state how to avoid it in future tasks. "
        "Start with 'Pitfall: '."
    )
    try:
        raw = chat([{"role": "user", "content": prompt}], model=model, json_mode=False).strip()
        pitfall = raw.replace("\n", " ").strip()
        if not pitfall.lower().startswith("pitfall:"):
            pitfall = f"Pitfall: {pitfall}"
    except Exception as e:
        pitfall = f"Pitfall: Avoid overwriting working source modules during test subtasks ({e})."

    if db:
        try:
            tid = task_id or 1
            fact_id = db.save_fact(tid, "pitfall", pitfall, embed_now=True)
            if verbose:
                print(f"[Learning] Saved verified pitfall #{fact_id}: {pitfall[:90]}...")
        except Exception as e:
            if verbose:
                print(f"[Learning] Note: could not save pitfall: {e}")

    return pitfall


def retrieve_learning_context(
    query: str,
    db: DB | None = None,
    top_k: int = 2,
    min_score: float = 0.45,
) -> dict:
    """
    Retrieve semantically relevant lessons and pitfalls for a task or subtask.
    Returns:
        {
            'lessons': list[dict],
            'pitfalls': list[dict],
            'formatted_text': str
        }
    """
    if db is None:
        return {"lessons": [], "pitfalls": [], "formatted_text": ""}

    lessons = db.search_facts(query, kind="lesson", top_k=top_k, min_score=min_score)
    pitfalls = db.search_facts(query, kind="pitfall", top_k=top_k, min_score=min_score)

    lines = []
    if lessons:
        lines.append("Verified Experience & Patterns:")
        for l in lessons:
            lines.append(f"  • {l['text'].strip()}")

    if pitfalls:
        lines.append("Known Pitfalls to Avoid:")
        for p in pitfalls:
            lines.append(f"  • {p['text'].strip()}")

    return {
        "lessons": lessons,
        "pitfalls": pitfalls,
        "formatted_text": "\n".join(lines) if lines else "",
    }


def index_knowledge_pack(
    pack_name: str,
    docs_dir: Path | str,
    db: DB,
    verbose: bool = True,
) -> dict:
    """
    Index a directory of offline documentation as documents with kind='doc'.
    Chunks and embeds each file for memory retrieval.
    """
    from memory.vectors import index_directory

    p = Path(docs_dir).resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"Documentation directory not found: {p}")

    if verbose:
        print(f"[KnowledgePack] Indexing offline pack '{pack_name}' from {p}...")

    stats = index_directory(p, db, source=pack_name, verbose=verbose)
    # Mark indexed documents with kind='doc'
    db.con.execute("UPDATE documents SET kind='doc' WHERE source=?", (pack_name,))
    db.con.commit()

    if verbose:
        print(f"[KnowledgePack] Successfully indexed '{pack_name}': {stats}")

    return stats


def main():
    p = argparse.ArgumentParser(description="Phase 5 Learning Loop CLI")
    sub = p.add_subparsers(dest="cmd")

    # list
    p_list = sub.add_parser("list", help="List stored facts (lessons and pitfalls)")
    p_list.add_argument("--kind", choices=["lesson", "pitfall"], default=None)
    p_list.add_argument("--db", default="data/memory.db")

    # search
    p_search = sub.add_parser("search", help="Semantic search over facts")
    p_search.add_argument("query")
    p_search.add_argument("--kind", choices=["lesson", "pitfall"], default=None)
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.add_argument("--db", default="data/memory.db")

    # index-pack
    p_pack = sub.add_parser("index-pack", help="Index an offline documentation pack")
    p_pack.add_argument("dir", help="Path to documentation folder")
    p_pack.add_argument("--name", default="stdlib_docs", help="Knowledge pack source name")
    p_pack.add_argument("--db", default="data/memory.db")

    a = p.parse_args()
    if not a.cmd:
        p.print_help()
        return

    db = DB(a.db)

    if a.cmd == "list":
        rows = db.all_fact_embeddings(kind=a.kind) if hasattr(db, "all_fact_embeddings") else []
        if not rows:
            # Fallback to direct table query
            q = "SELECT id, kind, text, verified FROM facts"
            if a.kind:
                q += f" WHERE kind = '{a.kind}'"
            raw = db.con.execute(q).fetchall()
            print(f"Total facts: {len(raw)}")
            for r in raw:
                print(f"[{r[1].upper()}] #{r[0]}: {r[2]}")
        else:
            print(f"Total embedded facts: {len(rows)}")
            for r in rows:
                print(f"[{r[3].upper()}] #{r[0]}: {r[2]}")

    elif a.cmd == "search":
        print(f"Searching facts for: '{a.query}'...\n")
        res = retrieve_learning_context(a.query, db=db, top_k=a.top_k)
        if res["formatted_text"]:
            print(res["formatted_text"])
        else:
            print("No matching lessons or pitfalls found.")

    elif a.cmd == "index-pack":
        index_knowledge_pack(a.name, a.dir, db=db, verbose=True)


if __name__ == "__main__":
    main()
