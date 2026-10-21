"""
stall_guard.py – Detects repetitive edits / failures and breaks agent loops.
"""
import hashlib


def _hash(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _failure_signature(obs):
    """Short fingerprint of a failing pytest run (FAILED lines and E lines)."""
    keep = [ln.strip() for ln in obs.splitlines()
            if ln.strip().startswith(("FAILED", "E "))]
    return "|".join(keep[:6])


class StallGuard:
    """Detects an agent repeating itself and changes what happens next.

    Usage inside the agent loop:
        guard = StallGuard()
        raw = chat(messages, model=model, json_mode=True,
                   temperature=guard.temperature)
        ...
        obs = tools.call(tool, args)
        res = guard.after_step(tool, args, obs)
        obs = res["obs"]
        if res["abort"]:
            return end("stuck", res["reason"])
    """

    def __init__(self, base_temp=0.2, hot_temp=0.8, max_strikes=4):
        self.base_temp = base_temp
        self.hot_temp = hot_temp
        self.max_strikes = max_strikes
        self.strikes = 0
        self.last_write = {}        # path -> hash of the last content written
        self.last_failure = None    # signature of the last failing test run
        self.last_fail_text = ""

    @property
    def temperature(self):
        # Same context at low temperature gives the same answer, so a stuck
        # model needs more randomness to try something different.
        return self.hot_temp if self.strikes >= 1 else self.base_temp

    def after_step(self, tool, args, obs):
        abort, reason = False, ""

        if tool == "write_file":
            path = args.get("path", "")
            h = _hash(str(args.get("content", "")))
            same = self.last_write.get(path) == h or "identical content" in obs
            self.last_write[path] = h
            if same:
                self.strikes += 1
                obs = ("NO CHANGE: you sent the same file content again, so the "
                       "test result will be the same. Last failing output:\n"
                       f"{self.last_fail_text}\n"
                       "Change the code to fix that specific failure.")

        elif tool == "run_tests":
            if "TESTS PASSED" in obs:
                self.strikes = 0
                self.last_failure = None
            elif "TESTS FAILED" in obs:
                sig = _failure_signature(obs)
                if sig and sig == self.last_failure:
                    self.strikes += 1
                else:
                    self.strikes = 0      # a different failure means progress
                self.last_failure = sig
                self.last_fail_text = obs[:800]
                obs += ("\nHINT: find the assertion that failed, say in 'thought' "
                        "which input gave which wrong output and why, then change "
                        "the code for that case. Do not resend the same file.")

        if self.strikes >= self.max_strikes:
            abort, reason = True, "no progress: repeated the same edit and failure"
        return {"obs": obs, "abort": abort, "reason": reason}
