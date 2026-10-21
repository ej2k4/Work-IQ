"""
context_manager.py – Context-budget management and step-log summarization.

Prevents context window overflow on small models (e.g. 3B/7B with 8192 num_ctx)
by dynamically monitoring token budgets and condensing early execution steps.
"""
from __future__ import annotations

import json
import re


def estimate_tokens(text: str) -> int:
    """Fast local approximation of token count (~3.5 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 3.5)


def summarize_step_pair(assistant_content: str, user_obs: str) -> str:
    """Summarize a single tool action and its observation into a 1-line note."""
    tool_name = "unknown"
    args_summary = ""
    try:
        data = json.loads(assistant_content.strip())
        tool_name = data.get("tool", "action")
        args = data.get("args", {})
        if "path" in args:
            args_summary = f"({args['path']})"
        elif "query" in args:
            args_summary = f"('{args['query'][:20]}')"
        elif "summary" in args:
            args_summary = f"('{args['summary'][:25]}')"
    except Exception:
        # Fallback regex extraction
        m = re.search(r'"tool":\s*"([^"]+)"', assistant_content)
        if m:
            tool_name = m.group(1)

    # Summarize observation, stripping the OBSERVATION from <tool>: header
    clean_obs = re.sub(r"^OBSERVATION from \w+:\s*", "", user_obs.strip())
    first_line = clean_obs.splitlines()[0] if clean_obs else ""
    first_line = first_line[:80].strip()

    return f"- {tool_name}{args_summary} -> {first_line}"


class ContextManager:
    """
    Manages message history to guarantee stays within local context limits.
    """

    def __init__(
        self,
        max_context_tokens: int = 5500,
        keep_recent_pairs: int = 3,
    ):
        self.max_context_tokens = max_context_tokens
        self.keep_recent_pairs = keep_recent_pairs

    def total_tokens(self, messages: list[dict]) -> int:
        return sum(estimate_tokens(m.get("content", "")) for m in messages)

    def prune_or_summarize(self, messages: list[dict]) -> list[dict]:
        """
        If total tokens exceed max_context_tokens, compress older steps
        into a concise summary while preserving system prompt, task, and recent steps.
        """
        current_tokens = self.total_tokens(messages)
        if current_tokens <= self.max_context_tokens:
            return messages

        # Must have at least system prompt (0) + initial task (1) + some history
        if len(messages) <= 3:
            return messages

        system_msg = messages[0]
        task_msg = messages[1]

        # Recent steps to keep intact (each step typically has assistant + user observation)
        recent_count = self.keep_recent_pairs * 2
        if len(messages) <= 2 + recent_count:
            # Not enough middle messages to compress, clip large individual observations
            clipped_messages = [system_msg, task_msg]
            for m in messages[2:]:
                content = m.get("content", "")
                if len(content) > 1000:
                    content = content[:1000] + "\n...[truncated for context budget]"
                clipped_messages.append({"role": m["role"], "content": content})
            return clipped_messages

        older_messages = messages[2:-recent_count]
        recent_messages = messages[-recent_count:]

        # Compress older_messages into high-density notes
        summary_lines = []
        i = 0
        while i < len(older_messages):
            msg = older_messages[i]
            if msg.get("role") == "assistant":
                asst_text = msg.get("content", "")
                user_text = ""
                if i + 1 < len(older_messages) and older_messages[i + 1].get("role") == "user":
                    user_text = older_messages[i + 1].get("content", "")
                    i += 1
                summary_lines.append(summarize_step_pair(asst_text, user_text))
            elif msg.get("role") == "user":
                clean = msg.get("content", "")[:60].replace("\n", " ")
                summary_lines.append(f"• User note: {clean}")
            i += 1

        summary_text = (
            "[Previous Steps Summary - older actions condensed to preserve context budget]:\n"
            + "\n".join(summary_lines)
            + "\n[End of previous summary. Recent steps continue below:]"
        )

        compressed_summary_msg = {
            "role": "user",
            "content": summary_text,
        }

        new_history = [system_msg, task_msg, compressed_summary_msg] + recent_messages
        return new_history
