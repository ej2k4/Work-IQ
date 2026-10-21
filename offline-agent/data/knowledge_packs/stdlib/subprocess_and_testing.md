# Subprocess and Pytest Testing Patterns Guide

## Executing Python Code with -c
- When running `python -c` from subprocess or shlex commands on Windows:
  - If argument strings have outer enclosing double quotes (`"-c", "\"code\""`), Python treats the code as a string literal and exits with status 0 without actually running assertions!
  - Always strip enclosing quotes from command arguments before calling `subprocess.run(args)`.

## Writing Resilient Pytest Tests
- Keep test assertions focused on external interfaces and specifications:
  ```python
  import pytest
  from my_module import my_func

  def test_basic_operation():
      assert my_func("input") == "expected"
  ```
- Do not assert undocumented internal implementation details.
