import os
from pathlib import Path
import pytest

from memory.db import DB
from memory.obsidian import index_vault, write_agent_note, update_vault_index


@pytest.fixture
def temp_vault(tmp_path):
    vault = tmp_path / "test_vault"
    vault.mkdir()
    # Create sample user notes
    (vault / "Architecture.md").write_text(
        "# Architecture\n\nSee [[Design]] and [[Database]] for core patterns. #tag/core",
        encoding="utf-8",
    )
    (vault / "Design.md").write_text(
        "# Design\n\nFollows offline-first principles. Tagged with #tag/offline.",
        encoding="utf-8",
    )
    return vault


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_mem.db"
    return DB(str(db_path))


def test_index_vault_creates_documents_and_graph(temp_vault, temp_db):
    stats = index_vault(temp_vault, db=temp_db)
    assert stats["notes"] >= 2
    assert stats["nodes"] > 0
    assert stats["edges"] > 0

    # Verify documents in DB
    docs = temp_db.con.execute("SELECT path, kind FROM documents WHERE kind='note'").fetchall()
    doc_paths = [d[0] for d in docs]
    assert "Architecture.md" in doc_paths
    assert "Design.md" in doc_paths


def test_write_agent_note_and_dashboard(temp_vault, temp_db):
    # Write note for task 42
    note_p = write_agent_note(
        vault_dir=temp_vault,
        task_id=42,
        task="Implement semver comparison",
        status="finished",
        summary="Added numeric tuple comparison and zero-padding.",
        lesson="Always pad shorter version tuples with zeros.",
        touched_files=["semver.py", "test_semver.py"],
        db=temp_db,
    )

    assert note_p.exists()
    assert note_p.name == "Task-42.md"
    assert note_p.parent.name == "Agent"

    content = note_p.read_text(encoding="utf-8")
    assert "task_id: 42" in content
    assert "status: finished" in content
    assert "status/finished" in content
    assert "[[semver.py]]" in content
    assert "Always pad shorter version tuples with zeros." in content

    # Verify INDEX.md dashboard was generated
    index_file = temp_vault / "Agent" / "INDEX.md"
    assert index_file.exists()
    index_content = index_file.read_text(encoding="utf-8")
    assert "Agent Task Dashboard" in index_content
    assert "[[Task-42]]" in index_content
    assert "Always pad shorter version tuples with zeros." in index_content


def test_write_agent_note_jail_enforcement(temp_vault, temp_db):
    # Attempting to write outside Agent directory must be blocked or throw
    agent_dir = temp_vault / "Agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    
    # Passing a path that attempts path traversal in filename/task_id is jailed by design
    # write_agent_note hardcodes filename as f"Task-{task_id}.md" inside agent_dir
    p = write_agent_note(
        vault_dir=temp_vault,
        task_id=99,
        task="Testing safety",
        status="stuck",
        summary="Stuck repeat",
        db=temp_db,
    )
    assert p.resolve().parent == (temp_vault / "Agent").resolve()
