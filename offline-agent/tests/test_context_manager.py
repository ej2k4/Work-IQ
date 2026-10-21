"""
test_context_manager.py – Unit tests for context budget management and summarization.
"""
from agent.context_manager import ContextManager, estimate_tokens, summarize_step_pair


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") >= 1
    long_str = "a" * 350
    assert estimate_tokens(long_str) == 100


def test_summarize_step_pair():
    asst = '{"thought": "read file", "tool": "read_file", "args": {"path": "main.py"}}'
    obs = "OBSERVATION from read_file:\ndef foo(): pass\nprint('done')"
    summary = summarize_step_pair(asst, obs)
    assert "read_file(main.py)" in summary
    assert "def foo(): pass" in summary


def test_context_manager_under_budget():
    mgr = ContextManager(max_context_tokens=1000)
    messages = [
        {"role": "system", "content": "You are an agent."},
        {"role": "user", "content": "Task: fix bug"},
        {"role": "assistant", "content": '{"tool": "list_dir", "args": {}}'},
        {"role": "user", "content": "OBSERVATION from list_dir:\nfoo.py"},
    ]
    pruned = mgr.prune_or_summarize(messages)
    assert len(pruned) == len(messages)
    assert pruned == messages


def test_context_manager_over_budget_compresses_middle():
    mgr = ContextManager(max_context_tokens=300, keep_recent_pairs=1)
    
    # Create a message history that exceeds 300 tokens
    messages = [
        {"role": "system", "content": "System prompt."},
        {"role": "user", "content": "Task: complex refactoring."},
    ]
    # Add 5 earlier steps (each with large text)
    for i in range(1, 6):
        messages.append({
            "role": "assistant",
            "content": f'{{"thought": "step {i}", "tool": "write_file", "args": {{"path": "file_{i}.py"}}}}'
        })
        messages.append({
            "role": "user",
            "content": f"OBSERVATION from write_file:\n{'content ' * 30}"
        })

    # Add 1 recent step (keep_recent_pairs=1 -> 2 messages)
    messages.append({
        "role": "assistant",
        "content": '{"thought": "final", "tool": "run_tests", "args": {"path": "test.py"}}'
    })
    messages.append({
        "role": "user",
        "content": "OBSERVATION from run_tests:\nTESTS PASSED"
    })

    initial_tokens = mgr.total_tokens(messages)
    assert initial_tokens > 300

    pruned = mgr.prune_or_summarize(messages)
    assert len(pruned) < len(messages)
    # Check that system prompt and task are preserved
    assert pruned[0]["content"] == "System prompt."
    assert pruned[1]["content"] == "Task: complex refactoring."
    # Check that middle was replaced by a summary note
    assert "[Previous Steps Summary" in pruned[2]["content"]
    # Check that recent step is preserved
    assert "run_tests" in pruned[-2]["content"]
    assert "TESTS PASSED" in pruned[-1]["content"]
