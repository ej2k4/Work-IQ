"""
test_stall_guard.py – Unit tests for StallGuard.
"""
from agent.stall_guard import StallGuard


def test_stall_guard_initial_state():
    guard = StallGuard(base_temp=0.2, hot_temp=0.8, max_strikes=4)
    assert guard.strikes == 0
    assert guard.temperature == 0.2


def test_stall_guard_write_file_detection():
    guard = StallGuard()
    # First write
    res1 = guard.after_step("write_file", {"path": "app.py", "content": "x = 1"}, "OK: wrote 5 chars")
    assert guard.strikes == 0
    assert guard.temperature == 0.2
    assert res1["abort"] is False

    # Simulate a failing test to store last_fail_text
    guard.after_step("run_tests", {"path": "test.py"}, "TESTS FAILED\nFAILED test.py::test_x - assert x == 2\nE assert 1 == 2")

    # Identical write triggers strike and hot temperature
    res2 = guard.after_step("write_file", {"path": "app.py", "content": "x = 1"}, "OK: wrote 5 chars")
    assert guard.strikes == 1
    assert guard.temperature == 0.8
    assert "NO CHANGE" in res2["obs"]
    assert "assert 1 == 2" in res2["obs"]
    assert res2["abort"] is False


def test_stall_guard_aborts_at_max_strikes():
    guard = StallGuard(max_strikes=3)
    guard.last_fail_text = "FAILED assertion"
    for _ in range(4):
        res = guard.after_step("write_file", {"path": "app.py", "content": "same"}, "OK")
    assert guard.strikes == 3
    assert res["abort"] is True
    assert "no progress" in res["reason"]


def test_stall_guard_resets_on_test_pass():
    guard = StallGuard()
    guard.strikes = 2
    res = guard.after_step("run_tests", {"path": "test.py"}, "TESTS PASSED\nAll 5 passed")
    assert guard.strikes == 0
    assert guard.temperature == 0.2
