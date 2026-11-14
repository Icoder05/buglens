"""Gemini client with caching, backoff, rate limiting, request cap and leakage guard — FR-M1.

Concept: LLM calls are the only non-deterministic, rate-limited and (beyond
the free tier) paid step, so they are wrapped once:
- disk cache: the response to an identical (model, schema, prompt) is stored
  under `data/cache/llm/<sha1>.json`; reruns make 0 API calls;
- exponential backoff with jitter on 429/503 (transient overload), but a
  *daily* quota error stops immediately — waiting will not help;
- an RPM throttle and a hard `max_requests` cap per command ($0 budget);
- token accounting from `usage_metadata` (accuracy vs. tokens, RQ3);
- a guard that refuses any prompt containing gold `patch`, `test_patch`,
  `FAIL_TO_PASS` or `PASS_TO_PASS` text (or an added line of the instance's
  own gold patch): the evaluation would be meaningless otherwise.
"""

from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from buglens.config import PROJECT_ROOT, Config
from buglens.utils import console, sha1


class LeakageError(AssertionError):
    pass


class RequestCapReached(RuntimeError):
    pass


class QuotaExhausted(RuntimeError):
    pass


def load_api_key() -> str | None:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    env = PROJECT_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                return value or None
    return None


@dataclass
class GoldGuard:
    """Holds every gold text that must never appear in a prompt."""

    full_texts: list[str] = field(default_factory=list)
    added_lines: dict[str, list[str]] = field(default_factory=dict)  # instance -> lines

    @classmethod
    def from_cfg(cls, cfg: Config) -> GoldGuard:
        from buglens.data.swebench import load_gold_texts, load_split

        guard = cls()
        for split in ("test", "dev"):
            public = {i.instance_id: i.problem_statement + "\n" + i.hints_text
                      for i in load_split(cfg, split)}
            for iid, texts in load_gold_texts(cfg, split).items():
                lines = []
                for key, text in texts.items():
                    if len(text.strip()) >= 20:
                        guard.full_texts.append(text.strip())
                    if key in ("patch", "test_patch"):
                        old_side = {ln[1:].strip() for ln in text.splitlines()
                                    if ln[:1] in ("-", " ") and not ln.startswith("---")}
                        lines += [ln[1:].strip() for ln in text.splitlines()
                                  if ln.startswith("+") and not ln.startswith("+++")
                                  and len(ln[1:].strip()) >= 30
                                  and ln[1:].strip() not in old_side
                                  and ln[1:].strip() not in public.get(iid, "")]
                guard.added_lines[iid] = lines
        return guard

    def check(self, prompt: str, instance_id: str | None = None,
              base_code: str = "") -> None:
        """`base_code` = code from `base_commit` shown in the prompt. A gold added line that
        already exists verbatim in that code (e.g. a repeated `if hasattr(...)`) is not leakage."""
        for text in self.full_texts:
            if text in prompt:
                raise LeakageError("prompt contains gold patch/test text")
        for line in self.added_lines.get(instance_id or "", []):
            if line in prompt and line not in base_code:
                raise LeakageError(f"prompt contains a gold-patch line of {instance_id}")


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cached: bool = False
    seconds: float = 0.0


Backend = Callable[[str, str, dict], tuple[str, int, int]]


class LLMClient:
    def __init__(self, cfg: Config, guard: GoldGuard | None = None,
                 max_requests: int | None = None, backend: Backend | None = None):
        self.cfg = cfg
        self.model = cfg.llm.model
        self.guard = guard if guard is not None else GoldGuard.from_cfg(cfg)
        self.max_requests = max_requests if max_requests is not None else cfg.llm.max_requests
        self.requests = 0
        self.cache_hits = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self._last_call = 0.0
        self._backend = backend
        self.cache_dir = cfg.path("cache") / "llm"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- backend
    def _gemini(self, model: str, prompt: str, schema: dict) -> tuple[str, int, int]:
        from google import genai
        from google.genai import types

        if not hasattr(self, "_client"):
            key = load_api_key()
            if not key:
                raise RuntimeError("GEMINI_API_KEY not set (environment or .env)")
            timeout_ms = int(self.cfg.llm.get("timeout_s", 120) * 1000)
            self._client = genai.Client(api_key=key,
                                        http_options=types.HttpOptions(timeout=timeout_ms))
        config = {"response_mime_type": "application/json", "response_json_schema": schema,
                  "temperature": 0.0}
        budget = self.cfg.llm.get("thinking_budget")
        level = self.cfg.llm.get("thinking_level")  # Gemini 3.x: "minimal" | "low" | ...
        if level:
            config["thinking_config"] = types.ThinkingConfig(thinking_level=level)
        elif budget is not None:
            config["thinking_config"] = types.ThinkingConfig(thinking_budget=int(budget))
        resp = self._client.models.generate_content(
            model=model, contents=prompt, config=types.GenerateContentConfig(**config))
        um = resp.usage_metadata
        t_in = (um.prompt_token_count or 0) if um else 0
        t_out = ((um.candidates_token_count or 0) + (um.thoughts_token_count or 0)) if um else 0
        return resp.text or "", t_in, t_out

    def _throttle(self) -> None:
        interval = 60.0 / max(self.cfg.llm.rpm, 1)
        wait = self._last_call + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _call_with_backoff(self, prompt: str, schema: dict) -> tuple[str, int, int]:
        backend = self._backend or self._gemini
        delay = 4.0
        for attempt in range(self.cfg.llm.max_retries + 1):
            self._throttle()
            try:
                return backend(self.model, prompt, schema)
            except Exception as e:  # noqa: BLE001 - inspect API errors below
                code = getattr(e, "code", None)
                msg = str(e)
                if code == 429 and ("PerDay" in msg or "per day" in msg.lower()):
                    raise QuotaExhausted(f"daily free-tier quota exhausted: {msg[:300]}") from e
                if code in (429, 500, 503, 504) and attempt < self.cfg.llm.max_retries:
                    sleep = delay * (2 ** attempt) * (0.5 + random.random())
                    console.print(f"[yellow]LLM {code}; retry in {sleep:.0f}s[/yellow]")
                    time.sleep(min(sleep, 120))
                    continue
                raise
        raise RuntimeError("unreachable")

    # ------------------------------------------------------------- public
    def generate_json(self, prompt: str, schema: dict, instance_id: str | None = None,
                      base_code: str = "") -> tuple[dict | None, Usage]:
        """Return (parsed JSON or None if unparsable, usage). Cached on disk."""
        self.guard.check(prompt, instance_id, base_code)
        key = sha1(self.model + "\n" + json.dumps(schema, sort_keys=True) + "\n" + prompt)
        path = self.cache_dir / f"{key}.json"
        t0 = time.perf_counter()
        if path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            self.cache_hits += 1
            usage = Usage(rec["tokens_in"], rec["tokens_out"], True, rec.get("seconds", 0.0))
        else:
            if self.requests >= self.max_requests:
                raise RequestCapReached(f"max_requests={self.max_requests} reached")
            self.requests += 1
            text, t_in, t_out = self._call_with_backoff(prompt, schema)
            seconds = time.perf_counter() - t0
            rec = {"model": self.model, "response": text, "tokens_in": t_in,
                   "tokens_out": t_out, "seconds": seconds}
            path.write_text(json.dumps(rec), encoding="utf-8")
            usage = Usage(t_in, t_out, False, seconds)
        self.tokens_in += usage.tokens_in
        self.tokens_out += usage.tokens_out
        try:
            return json.loads(rec["response"]), usage
        except (json.JSONDecodeError, TypeError):
            return None, usage

    def report(self) -> str:
        return (f"llm model={self.model} api_calls={self.requests} cache_hits={self.cache_hits} "
                f"tokens_in={self.tokens_in} tokens_out={self.tokens_out}")
