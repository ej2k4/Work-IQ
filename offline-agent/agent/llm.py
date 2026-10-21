"""
llm.py – Thin wrapper around the Ollama /api/chat endpoint.

Uses plain requests (no extra SDK) so the dependency footprint stays minimal.
The model is selected by argument or by the AGENT_MODEL environment variable.

Phase 0 speed test:
    python -m agent.llm                        # default model (qwen2.5-coder:3b)
    python -m agent.llm qwen2.5-coder:7b       # slower, higher quality
"""
import os
import sys

import requests

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "qwen2.5-coder:3b")

# Recommended Ollama environment settings for 16 GB RAM / 4 GB VRAM:
#   OLLAMA_MAX_LOADED_MODELS=1
#   OLLAMA_NUM_PARALLEL=1


def chat_raw(
    messages: list[dict],
    model: str | None = None,
    json_mode: bool = False,
    temperature: float = 0.2,
    num_ctx: int = 4096,
    num_predict: int = 1024,
    timeout: int = 180,
) -> dict:
    """
    Call Ollama /api/chat and return the full JSON response dict.

    The response includes 'eval_count' (tokens generated) and 'eval_duration'
    (nanoseconds), which you can use to compute tokens per second.

    Args:
        messages:    List of {"role": ..., "content": ...} dicts.
        model:       Ollama model name; falls back to DEFAULT_MODEL.
        json_mode:   If True, sets format="json" to constrain output to JSON.
        temperature: Sampling temperature (lower = more deterministic).
        num_ctx:     KV-cache context length; raising this uses more VRAM.
        num_predict: Maximum tokens to generate (prevents runaway loops).
        timeout:     HTTP request timeout in seconds.

    Raises:
        requests.HTTPError: on non-2xx response.
        requests.ConnectionError: if Ollama is not running.
    """
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    }
    if json_mode:
        payload["format"] = "json"

    try:
        r = requests.post(f"{OLLAMA}/api/chat", json=payload, timeout=timeout)
    except requests.ConnectionError:
        raise requests.ConnectionError(
            f"Cannot reach Ollama at {OLLAMA}. "
            "Make sure the Ollama app is running and try again."
        )
    r.raise_for_status()
    return r.json()


def chat(
    messages: list[dict],
    model: str | None = None,
    json_mode: bool = False,
    temperature: float = 0.2,
    num_ctx: int = 4096,
    num_predict: int = 1024,
    timeout: int = 180,
) -> str:
    """
    Call Ollama /api/chat and return only the assistant message content string.

    This is the convenience wrapper used by the agent loop.
    """
    data = chat_raw(messages, model, json_mode, temperature, num_ctx, num_predict, timeout)
    return data["message"]["content"]


if __name__ == "__main__":
    # ── Phase 0 gate ──────────────────────────────────────────────────────────
    # Run this with Wi-Fi OFF to confirm the model works fully offline.
    # Record the tok/s numbers — they are your Phase 0 baseline.
    #
    #   python -m agent.llm                    → qwen2.5-coder:3b
    #   python -m agent.llm qwen2.5-coder:7b   → qwen2.5-coder:7b
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    print(f"Testing model: {model}")
    print(f"Ollama host  : {OLLAMA}")
    print()

    try:
        data = chat_raw(
            [{"role": "user",
              "content": "Write a Python function that reverses a linked list. Code only."}],
            model=model,
        )
    except requests.ConnectionError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except requests.HTTPError as e:
        print(f"ERROR: HTTP {e.response.status_code}: {e.response.text[:200]}")
        sys.exit(1)

    print(data["message"]["content"])

    tokens = data.get("eval_count", 0)
    prompt_tokens = data.get("prompt_eval_count", 0)
    secs = data.get("eval_duration", 1) / 1e9
    total_secs = data.get("total_duration", 1) / 1e9

    print(f"\n{'-'*50}")
    print(f"Model          : {model}")
    print(f"Prompt tokens  : {prompt_tokens}")
    print(f"Generated tokens: {tokens}")
    print(f"Generation time : {secs:.1f}s")
    print(f"Total time      : {total_secs:.1f}s")
    print(f"Speed           : {tokens / secs:.1f} tok/s  <- record this for Phase 0 gate")
