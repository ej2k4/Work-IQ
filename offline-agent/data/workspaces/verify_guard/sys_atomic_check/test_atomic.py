import pytest
from pathlib import Path
from atomic import atomic_write

def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "test.txt"
    atomic_write(target, "hello atomic")
    assert target.read_text(encoding="utf-8") == "hello atomic"

def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "sub" / "output.txt"
    atomic_write(target, "deep content")
    assert target.read_text(encoding="utf-8") == "deep content"

def test_atomic_write_overwrites_existing(tmp_path):
    target = tmp_path / "existing.txt"
    target.write_text("initial", encoding="utf-8")
    atomic_write(target, "updated")
    assert target.read_text(encoding="utf-8") == "updated"
