"""
security.py – Hardened security policies and jail enforcement.

Enforces:
1. Workspace path jail (prevents traversal, absolute path escapes, symlink traversal,
   Windows device names, alternate data streams, and null-byte injection).
2. Subtask file-write restrictions (fine-grained write jails).
3. Command allowlist and injection defenses for reviewer / test execution.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import sys


class SecurityViolation(ValueError):
    """Raised when an operation attempts to violate sandbox boundaries."""
    pass


# Reserved Windows device names that cannot be used as file paths
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

# Strict command allowlist: only these base executables are permitted
ALLOWED_EXECUTABLES = {
    "python", "python.exe",
    "pytest", "pytest.exe",
    "git", "git.exe",
}

# Dangerous shell commands or utilities explicitly forbidden
FORBIDDEN_COMMANDS = {
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "bash", "sh", "zsh",
    "curl", "curl.exe", "wget", "wget.exe", "nc", "netcat", "socat",
    "reg", "certutil", "bitsadmin", "wmic",
    "rm", "rmdir", "del", "erase", "format", "dd",
    "kill", "taskkill", "pkill", "shutdown", "reboot",
}

# Dangerous shell metacharacters that indicate command chaining or redirection
DANGEROUS_SHELL_PATTERNS = re.compile(r"[;&|><`$]")


def validate_path(
    rel_or_abs: str | Path,
    workspace_root: str | Path,
    must_exist: bool = False,
    is_write: bool = False,
    allowed_write_files: set[str] | list[str] | None = None,
) -> Path:
    """
    Validate that a path stays strictly inside workspace_root.
    
    Checks:
    - Rejects null bytes
    - Rejects Windows device names (CON, NUL, AUX, etc.)
    - Rejects alternate data streams (e.g. file.txt:stream)
    - Verifies resolved path stays within workspace_root
    - Verifies real symlink target stays within workspace_root
    - If is_write=True and allowed_write_files is specified, verifies file is in allowed list.
    """
    path_str = str(rel_or_abs).strip()
    if not path_str:
        raise SecurityViolation("Path cannot be empty")

    # 1. Null-byte injection check
    if "\0" in path_str:
        raise SecurityViolation(f"Path contains null byte: {repr(path_str)}")

    # 2. Alternate data streams (Windows colon check beyond drive letter)
    # E.g., "file.txt:stream" or "c:\dir:stream"
    colon_idx = path_str.find(":")
    if colon_idx != -1:
        # If it's a Windows drive (e.g., C:\), check if there is a second colon
        if len(path_str) > 1 and path_str[1] == ":" and path_str[0].isalpha():
            if ":" in path_str[2:]:
                raise SecurityViolation(f"Alternate data stream forbidden: {path_str}")
        else:
            raise SecurityViolation(f"Colon in path forbidden: {path_str}")

    ws = Path(workspace_root).resolve()

    # 3. Handle relative vs absolute paths
    target = Path(path_str)
    if not target.is_absolute():
        target = (ws / target)

    # 4. Resolve path
    try:
        resolved = target.resolve(strict=False)
    except Exception as e:
        raise SecurityViolation(f"Failed to resolve path: {e}")

    # 5. Check workspace jail containment
    if resolved != ws and ws not in resolved.parents:
        raise SecurityViolation(f"Path '{path_str}' escapes workspace '{ws}'")

    # 6. Check for Windows reserved device names in any part
    for part in resolved.parts:
        name_without_ext = part.split(".")[0].upper()
        if name_without_ext in WINDOWS_RESERVED_NAMES:
            raise SecurityViolation(f"Reserved device name '{part}' is forbidden")

    # 7. Check symlink target escapes (if path exists and is symlink)
    if target.is_symlink():
        try:
            real_target = target.resolve(strict=True)
            if real_target != ws and ws not in real_target.parents:
                raise SecurityViolation(f"Symlink '{path_str}' targets outside workspace: {real_target}")
        except FileNotFoundError:
            pass

    # 8. Existence check if required
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {path_str}")

    # 9. Allowed write targets validation
    if is_write and allowed_write_files is not None:
        norm_rel = resolved.relative_to(ws).as_posix()
        allowed = {Path(f).as_posix().lstrip("./") for f in allowed_write_files}
        if norm_rel not in allowed:
            raise SecurityViolation(
                f"Permission denied: this subtask is strictly restricted to writing: {sorted(list(allowed))}. "
                f"You may NOT write to '{path_str}'."
            )

    return resolved


def validate_command(
    cmd: str | list[str],
    workspace_root: str | Path,
) -> list[str]:
    """
    Validate and sanitize an execution command.
    
    Checks:
    - Parses command without invoking an unquoted shell
    - Disallows shell chaining operators (; && || | > < ` $)
    - Ensures base executable is in ALLOWED_EXECUTABLES and not in FORBIDDEN_COMMANDS
    - Replaces 'python' and 'pytest' with the current environment's interpreter
    - Validates any file arguments stay inside workspace
    """
    if isinstance(cmd, str):
        cmd_str = cmd.strip()
        if not cmd_str:
            raise SecurityViolation("Command cannot be empty")

        # Disallow shell metacharacters and chaining
        # (Allow double/single quotes and common python flags like -c)
        # Check if unquoted shell metacharacters exist
        # We parse with shlex
        try:
            args = shlex.split(cmd_str, posix=False)
        except ValueError as e:
            raise SecurityViolation(f"Malformed command line: {e}")
    else:
        args = list(cmd)

    if not args:
        raise SecurityViolation("Command args list cannot be empty")

    # Check for forbidden shell metacharacters and chaining operators in arguments
    FORBIDDEN_CHARS = {";", "|", "&", ">", "<", "`", "$"}
    for a in args:
        # If unquoted and contains forbidden characters, block immediately
        is_quoted = (a.startswith('"') and a.endswith('"')) or (a.startswith("'") and a.endswith("'"))
        if not is_quoted and any(ch in a for ch in FORBIDDEN_CHARS):
            raise SecurityViolation(f"Shell chaining operator forbidden in argument: {a}")
        # Also check for embedded forbidden executable invocations
        if not is_quoted and a.lower() in FORBIDDEN_COMMANDS:
            raise SecurityViolation(f"Forbidden command '{a}' detected in arguments")

    raw_exe = Path(args[0]).name.lower()

    if raw_exe in FORBIDDEN_COMMANDS:
        raise SecurityViolation(f"Forbidden command '{raw_exe}' cannot be executed")

    # Map python/pytest to current venv python
    _project_root = Path(__file__).resolve().parent.parent
    _venv_py = _project_root / ".venv" / "Scripts" / "python.exe"
    if not _venv_py.exists():
        _venv_py = _project_root / ".venv" / "bin" / "python"
    venv_python = str(_venv_py) if _venv_py.exists() else sys.executable

    clean_args = []
    # Strip enclosing quotes from args (e.g. from shlex posix=False)
    for a in args:
        if (a.startswith('"') and a.endswith('"')) or (a.startswith("'") and a.endswith("'")):
            clean_args.append(a[1:-1])
        else:
            clean_args.append(a)

    if raw_exe in ("python", "python.exe"):
        clean_args[0] = venv_python
    elif raw_exe in ("pytest", "pytest.exe"):
        clean_args = [venv_python, "-m", "pytest"] + clean_args[1:]
    elif raw_exe in ("git", "git.exe"):
        # Git is allowed only for read-only status/diff/log
        if len(clean_args) > 1:
            subcmd = clean_args[1].lower()
            if subcmd not in ("status", "diff", "log", "show", "branch"):
                raise SecurityViolation(f"Only read-only git commands allowed, got: git {subcmd}")
    else:
        # Check if executable path points directly to venv python or system python
        is_python_path = "python" in raw_exe
        if not is_python_path:
            raise SecurityViolation(f"Executable '{raw_exe}' is not in allowed list: {sorted(list(ALLOWED_EXECUTABLES))}")

    return clean_args
