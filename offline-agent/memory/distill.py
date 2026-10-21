"""
distill.py – Dataset exporter for offline experience distillation and LoRA fine-tuning.

Extracts verified successful execution traces from SQLite memory.db and converts
them into standardized training datasets (ShareGPT, ChatML, Alpaca format)
for fine-tuning smaller models or distilling agent behaviors offline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent.loop import SYSTEM
from memory.db import DB

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def export_traces(
    db: DB,
    format_type: str = "chatml",
    only_finished: bool = True,
    min_steps: int = 2,
) -> list[dict[str, Any]]:
    """
    Export execution traces from DB into standard dataset format.
    """
    status_filter = "WHERE status = 'finished'" if only_finished else ""
    query = f"SELECT id, task, model, status, summary FROM tasks {status_filter} ORDER BY id ASC"
    tasks = db.con.execute(query).fetchall()

    dataset: list[dict[str, Any]] = []

    for row in tasks:
        tid, task_text, model, status, summary = row
        steps = db.get_steps(tid)
        if len(steps) < min_steps:
            continue

        # Build conversation sequence
        turns: list[dict[str, str]] = []
        turns.append({"role": "system", "content": SYSTEM})
        turns.append({"role": "user", "content": f"Task: {task_text}"})

        for s in steps:
            tool = s["tool"]
            args_str = s["args"]
            obs = s["observation"]

            try:
                args_obj = json.loads(args_str) if isinstance(args_str, str) else args_str
            except Exception:
                args_obj = {}

            action_json = json.dumps({"tool": tool, "args": args_obj})
            turns.append({"role": "assistant", "content": action_json})
            turns.append({"role": "user", "content": f"OBSERVATION from {tool}:\n{obs}"})

        if format_type == "chatml":
            dataset.append({
                "id": f"task_{tid}",
                "model": model,
                "status": status,
                "messages": turns,
            })
        elif format_type == "sharegpt":
            role_map = {"system": "system", "user": "human", "assistant": "gpt"}
            conversations = [
                {"from": role_map[t["role"]], "value": t["content"]}
                for t in turns
            ]
            dataset.append({
                "id": f"task_{tid}",
                "model": model,
                "conversations": conversations,
            })
        elif format_type == "alpaca":
            # Flatten multi-turn into single completion or pair
            history_str = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in turns[:-1])
            dataset.append({
                "instruction": f"Solve this programming task using tool calls: {task_text}",
                "input": history_str,
                "output": turns[-1]["content"] if turns else "",
            })

    return dataset


def save_dataset_jsonl(dataset: list[dict[str, Any]], out_path: Path | str) -> int:
    """Save dataset list to a JSON Lines file."""
    p = Path(out_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(dataset)


def main():
    p = argparse.ArgumentParser(description="Export agent execution traces from memory.db for LoRA fine-tuning.")
    p.add_argument("--db", default=str(_PROJECT_ROOT / "data" / "memory.db"), help="Path to SQLite memory database")
    p.add_argument("--format", choices=["chatml", "sharegpt", "alpaca"], default="chatml", help="Dataset format")
    p.add_argument("--out", default=str(_PROJECT_ROOT / "data" / "distill_dataset.jsonl"), help="Output JSONL filepath")
    p.add_argument("--include-failed", action="store_true", help="Include failed / stuck traces (default: finished only)")
    p.add_argument("--min-steps", type=int, default=2, help="Minimum step count to include")
    p.add_argument("--stats", action="store_true", help="Display dataset stats without writing")
    args = p.parse_args()

    db = DB(args.db)
    dataset = export_traces(
        db,
        format_type=args.format,
        only_finished=not args.include_failed,
        min_steps=args.min_steps,
    )

    total_turns = sum(len(d.get("messages", d.get("conversations", []))) for d in dataset)
    print("=" * 60)
    print("EXPERIENCE DISTILLATION DATASET EXPORTER")
    print("=" * 60)
    print(f"Total verified traces : {len(dataset)}")
    print(f"Total dialogue turns  : {total_turns}")
    print(f"Format                : {args.format}")

    if not args.stats:
        count = save_dataset_jsonl(dataset, args.out)
        print(f"Saved {count} training traces to: {args.out}")


if __name__ == "__main__":
    main()
