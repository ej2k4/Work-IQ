import json
import pytest
from pathlib import Path

from memory.db import DB
from memory.distill import export_traces, save_dataset_jsonl


@pytest.fixture
def mock_db_with_traces(tmp_path):
    db_path = tmp_path / "mock_memory.db"
    db = DB(str(db_path))

    # Add a finished task with 3 steps
    tid = db.start_task("Fix broken test", "qwen2.5-coder:3b")
    db.log_step(tid, 1, "list_dir", "{}", "main.py\ntest_main.py")
    db.log_step(tid, 2, "read_file", '{"path": "test_main.py"}', "assert 1 == 1")
    db.log_step(tid, 3, "finish", '{"summary": "Fixed bug"}', "accepted")
    db.finish_task(tid, "finished", "Fixed bug")

    # Add a failed task
    fid = db.start_task("Failed task", "qwen2.5-coder:3b")
    db.log_step(fid, 1, "list_dir", "{}", "main.py")
    db.finish_task(fid, "stuck", "repeat detected")

    return db


def test_export_traces_sharegpt(mock_db_with_traces, tmp_path):
    dataset = export_traces(mock_db_with_traces, format_type="sharegpt", only_finished=True)
    assert len(dataset) == 1
    assert dataset[0]["id"] == "task_1"
    assert "conversations" in dataset[0]
    convs = dataset[0]["conversations"]
    assert convs[0]["from"] == "system"
    assert convs[1]["from"] == "human"
    assert convs[2]["from"] == "gpt"
    assert "list_dir" in convs[2]["value"]

    # Test saving to JSONL
    out_file = tmp_path / "dataset.jsonl"
    count = save_dataset_jsonl(dataset, out_file)
    assert count == 1
    assert out_file.exists()
    lines = out_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["id"] == "task_1"


def test_export_traces_chatml_and_alpaca(mock_db_with_traces):
    chatml = export_traces(mock_db_with_traces, format_type="chatml", only_finished=True)
    assert len(chatml) == 1
    assert "messages" in chatml[0]
    assert chatml[0]["messages"][0]["role"] == "system"

    alpaca = export_traces(mock_db_with_traces, format_type="alpaca", only_finished=True)
    assert len(alpaca) == 1
    assert "instruction" in alpaca[0]
    assert "input" in alpaca[0]
    assert "output" in alpaca[0]
