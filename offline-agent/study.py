"""
study.py – Interactive Educational Concept Graph Builder & Offline Tutor.

Allows users to command the agent to generate full, interconnected educational
concept graphs in their Obsidian vault, and query them offline.

Usage:
    # 1. Generate a new study graph on any topic:
    python study.py "Operating Systems"
    python study.py "Neural Networks"
    python study.py "Git Internals"

    # 2. Interactive prompt (asks you what you want to study):
    python study.py

    # 3. List existing study topics in your vault:
    python study.py --list

    # 4. Ask a question answered by your personal study graph:
    python study.py --ask "What is the difference between a process and a thread?"
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.llm import chat, DEFAULT_MODEL
from memory.db import DB
from memory.obsidian import index_vault

DEFAULT_VAULT = os.environ.get("OBSIDIAN_VAULT", r"C:\Users\admin\Documents\ObsidianVault")


def generate_curriculum_plan(topic: str, model: str = DEFAULT_MODEL) -> dict:
    """Use the local LLM to plan an interconnected concept graph for a topic."""
    prompt = f"""You are an expert educator and curriculum architect.
Create an interconnected curriculum concept graph for studying: '{topic}'.

Decompose this topic into 6 to 8 essential concept cards.
Each concept must link to other concepts in this curriculum using exact titles.

Respond with ONLY a single valid JSON object in this exact schema:
{{
  "topic": "{topic}",
  "overview": "2-sentence overview of the topic",
  "concepts": [
    {{
      "title": "Concept_Name_With_Underscores",
      "display_title": "Human Readable Title",
      "difficulty": "beginner|intermediate|advanced",
      "summary": "Clear 2-3 sentence definition and core explanation",
      "key_takeaway": "The one critical insight",
      "code_or_example": "Brief code snippet, math formula, or concrete example",
      "prerequisites": ["Other_Concept_Title"],
      "related": ["Other_Concept_Title"]
    }}
  ]
}}
Do NOT include markdown formatting or backticks around the JSON.
"""
    raw = chat([{"role": "user", "content": prompt}], model=model, json_mode=True)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
        if "concepts" in data and len(data["concepts"]) > 0:
            return data
    except Exception:
        pass

    # Safe fallback curriculum if model JSON was malformed
    clean_topic = re.sub(r"[^\w\s]", "", topic).strip().replace(" ", "_")
    return {
        "topic": topic,
        "overview": f"Foundational curriculum for studying {topic}.",
        "concepts": [
            {
                "title": f"{clean_topic}_Foundations",
                "display_title": f"{topic} Foundations",
                "difficulty": "beginner",
                "summary": f"Core principles, motivation, and underlying architecture of {topic}.",
                "key_takeaway": f"{topic} organizes complex systems into modular abstractions.",
                "code_or_example": "# Core setup\nprint('Initializing " + topic + "')",
                "prerequisites": [],
                "related": [f"{clean_topic}_Core_Mechanisms"],
            },
            {
                "title": f"{clean_topic}_Core_Mechanisms",
                "display_title": f"{topic} Core Mechanisms",
                "difficulty": "intermediate",
                "summary": f"The primary operational algorithms and data flows powering {topic}.",
                "key_takeaway": "Mastering the data flow reveals edge-case failure modes.",
                "code_or_example": "# Operational logic",
                "prerequisites": [f"{clean_topic}_Foundations"],
                "related": [f"{clean_topic}_Advanced_Applications"],
            },
            {
                "title": f"{clean_topic}_Advanced_Applications",
                "display_title": f"{topic} Advanced Applications",
                "difficulty": "advanced",
                "summary": f"Production optimizations, scaling patterns, and trade-offs in {topic}.",
                "key_takeaway": "Performance tuning requires balancing latency against memory.",
                "code_or_example": "# Optimization pass",
                "prerequisites": [f"{clean_topic}_Core_Mechanisms"],
                "related": [],
            },
        ],
    }


def write_curriculum_notes(plan: dict, vault_path: Path | str) -> list[Path]:
    """Write individual concept notes and an MOC index into the Obsidian vault."""
    root = Path(vault_path).resolve()
    topic_slug = re.sub(r"[^\w\-]", "_", plan["topic"]).strip("_")
    edu_dir = root / "Education" / topic_slug
    edu_dir.mkdir(parents=True, exist_ok=True)

    created_paths: list[Path] = []
    concepts = plan["concepts"]
    all_titles = {c["title"] for c in concepts}

    # 1. Write individual concept notes
    for c in concepts:
        title = c["title"]
        fname = f"{title}.md"
        fpath = edu_dir / fname

        prereq_links = "\n".join(f"- [[{p}]]" for p in c.get("prerequisites", []) if p in all_titles)
        if not prereq_links:
            prereq_links = "_None (Foundational)_"

        related_links = "\n".join(f"- [[{r}]]" for r in c.get("related", []) if r in all_titles)
        if not related_links:
            related_links = f"- [[{topic_slug}_Curriculum]]"

        code_block = ""
        if c.get("code_or_example"):
            code_block = f"\n## Example / Implementation\n```python\n{c['code_or_example']}\n```\n"

        content = f"""---
topic: {plan['topic']}
difficulty: {c.get('difficulty', 'intermediate')}
tags:
  - education/{topic_slug.lower()}
  - difficulty/{c.get('difficulty', 'intermediate')}
---

# {c.get('display_title', title)}

{c['summary']}

> [!TIP] Key Takeaway
> {c.get('key_takeaway', '')}
{code_block}
## Prerequisites
{prereq_links}

## Related Concepts
{related_links}

---
Part of the [[{topic_slug}_Curriculum|{plan['topic']} Curriculum]].
"""
        fpath.write_text(content.strip(), encoding="utf-8")
        created_paths.append(fpath)

    # 2. Write Mermaid Roadmap and MOC Index
    mermaid_edges = []
    for c in concepts:
        for p in c.get("prerequisites", []):
            if p in all_titles:
                mermaid_edges.append(f"    {p}[\"[[{p}]]\"] --> {c['title']}[\"[[{c['title']}]]\"]")
        for r in c.get("related", []):
            if r in all_titles and r not in c.get("prerequisites", []):
                mermaid_edges.append(f"    {c['title']}[\"[[{c['title']}]]\"] -.-> {r}[\"[[{r}]]\"]")

    mermaid_block = "graph TD\n" + "\n".join(mermaid_edges) if mermaid_edges else "graph TD\n    A[Foundations] --> B[Core Mechanisms]"

    moc_path = edu_dir / f"{topic_slug}_Curriculum.md"
    concept_list_md = "\n".join(
        f"- **[[{c['title']}]]** (`{c.get('difficulty', 'intermediate')}`): {c['summary']}"
        for c in concepts
    )

    moc_content = f"""---
tags:
  - education/curriculum
  - moc
---

# {plan['topic']} Study Roadmap

{plan.get('overview', '')}

```mermaid
{mermaid_block}
```

## Concept Cards
{concept_list_md}

---
_Generated by Offline Agent Study Engine._
"""
    moc_path.write_text(moc_content.strip(), encoding="utf-8")
    created_paths.append(moc_path)

    return created_paths


def query_study_graph(query: str, db: DB, top_k: int = 3) -> str:
    """Answer a study question by searching vector memory and traversing concept links."""
    from memory.graph import hybrid_search

    res = hybrid_search(query, db, top_k=top_k)
    seeds = res.get("seed_chunks", [])
    connected = res.get("connected_graph", [])

    if not seeds and not connected:
        return "No matching study notes found in your vault. Try generating notes for this topic first!"

    sources = []
    for s in seeds:
        sources.append(f"### From Note: {s.get('source', 'Note')}\n{s.get('text', '')}")

    graph_links = []
    for c in connected[:5]:
        graph_links.append(f"- **{c.get('name')}** ({c.get('relation')} {c.get('related_symbol')})")

    context_str = "\n\n".join(sources)
    graph_str = "\n".join(graph_links)

    answer_prompt = f"""You are a patient, encouraging computer science tutor.
Answer the student's question based strictly on their personal study graph notes below.

Student Question: {query}

Vault Study Notes:
{context_str}

Connected Knowledge Graph Concepts:
{graph_str}

Provide a clear, engaging explanation, and mention which [[Notes]] they can explore next.
"""
    return chat([{"role": "user", "content": answer_prompt}], model=DEFAULT_MODEL, json_mode=False)


def list_study_topics(vault_path: Path | str) -> list[str]:
    """List all study curricula generated in the vault."""
    edu_root = Path(vault_path).resolve() / "Education"
    if not edu_root.is_dir():
        return []
    topics = [d.name for d in edu_root.iterdir() if d.is_dir()]
    return sorted(topics)


def main():
    p = argparse.ArgumentParser(
        description="Offline AI Study Engine: Build and query interactive concept graphs in Obsidian.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python study.py "Operating Systems"
  python study.py "Neural Networks and Deep Learning"
  python study.py "Git Internals"
  python study.py --list
  python study.py --ask "What is the difference between a process and a thread?"
        """,
    )
    p.add_argument("topic", nargs="?", default=None, help="The topic you want to study (e.g., 'Operating Systems')")
    p.add_argument("--vault", default=DEFAULT_VAULT, help=f"Path to Obsidian vault (default: {DEFAULT_VAULT})")
    p.add_argument("--list", action="store_true", help="List all study curricula currently in your vault")
    p.add_argument("--ask", default=None, help="Ask a question answered by your study graph")
    p.add_argument("--db", default=str(_PROJECT_ROOT / "data" / "memory.db"), help="Path to SQLite memory.db")
    args = p.parse_args()

    vpath = Path(args.vault).resolve()
    vpath.mkdir(parents=True, exist_ok=True)
    db = DB(args.db)

    # 1. List topics
    if args.list:
        topics = list_study_topics(vpath)
        print("=" * 60)
        print("STUDY TOPICS IN YOUR OBSIDIAN VAULT")
        print("=" * 60)
        if topics:
            for t in topics:
                print(f"  • {t.replace('_', ' ')}  (folder: Education/{t})")
            print(f"\nVault location: {vpath}")
        else:
            print("  No study topics found yet. Run `python study.py <topic>` to create one!")
        return

    # 2. Ask question
    if args.ask:
        print("=" * 60)
        print(f"TUTOR: Answering: '{args.ask}'")
        print("=" * 60)
        answer = query_study_graph(args.ask, db=db)
        print("\n" + answer + "\n")
        return

    # 3. Build study graph
    target_topic = args.topic
    if not target_topic:
        print("=" * 60)
        print("  OFFLINE AI STUDY ENGINE: CONCEPT GRAPH BUILDER")
        print("=" * 60)
        try:
            target_topic = input("\nEnter the topic you want to study: ").strip()
        except EOFError:
            target_topic = "Operating Systems"

    if not target_topic:
        print("No topic specified. Exiting.")
        return

    print(f"\n[1/3] Planning curriculum for '{target_topic}' with local AI...")
    plan = generate_curriculum_plan(target_topic)
    print(f"  Planned {len(plan['concepts'])} concept cards: {', '.join(c['title'] for c in plan['concepts'][:4])}...")

    print(f"\n[2/3] Writing linked Markdown notes to Obsidian vault...")
    created = write_curriculum_notes(plan, vpath)
    print(f"  Created {len(created)} notes in {vpath / 'Education' / re.sub(r'[^\\w\\-]', '_', plan['topic']).strip('_')}")

    print(f"\n[3/3] Indexing new concept nodes and wikilinks into SQLite knowledge graph...")
    stats = index_vault(vpath, db=db, verbose=False)
    print(f"  Vault graph updated: {stats['notes']} notes, {stats['edges']} relationship edges.")

    print("\n" + "=" * 60)
    print("SUCCESS: Study Graph Created!")
    print("=" * 60)
    print(f"Topic:         {target_topic}")
    print(f"Obsidian Path: {vpath / 'Education'}")
    print("\nHow to view in Obsidian:")
    print("  1. Open Obsidian -> Open folder as vault -> " + str(vpath))
    print("  2. Press Ctrl + G to open Graph View to see the visual interactive map!")
    print(f"  3. Open [[{re.sub(r'[^\\w\\-]', '_', plan['topic']).strip('_')}_Curriculum]] to start reading.")


if __name__ == "__main__":
    main()
