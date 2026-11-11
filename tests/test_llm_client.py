import pytest

from buglens.config import load_config
from buglens.llm.client import GoldGuard, LeakageError, LLMClient, RequestCapReached


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["paths"] = {**c["paths"], "cache": str(tmp_path / "cache")}
    c["llm"] = {**c["llm"], "rpm": 6000}
    return c


def _guard():
    patch = "diff --git a/x.py b/x.py\n+    return compute_the_secret_fix(value, other)\n"
    return GoldGuard(full_texts=[patch.strip()],
                     added_lines={"inst-1": ["return compute_the_secret_fix(value, other)"]})


def test_guard_blocks_gold_patch_and_added_lines():
    g = _guard()
    with pytest.raises(LeakageError):
        g.check("prompt ... diff --git a/x.py b/x.py\n+    return compute_the_secret_fix("
                "value, other) ...")
    with pytest.raises(LeakageError):
        g.check("code: return compute_the_secret_fix(value, other)", "inst-1")
    g.check("code: return compute_the_secret_fix(value, other)", "inst-2")  # other instance


def test_cache_and_request_cap(cfg):
    calls = []

    def backend(model, prompt, schema):
        calls.append(prompt)
        return '{"ranking": ["a"], "reason": "r"}', 10, 3

    client = LLMClient(cfg, guard=GoldGuard(), max_requests=1, backend=backend)
    data, usage = client.generate_json("hello", {"type": "object"})
    assert data["ranking"] == ["a"] and (usage.tokens_in, usage.tokens_out) == (10, 3)
    data2, usage2 = client.generate_json("hello", {"type": "object"})
    assert data2 == data and usage2.cached and len(calls) == 1   # rerun = 0 API calls
    with pytest.raises(RequestCapReached):
        client.generate_json("another prompt", {"type": "object"})


def test_invalid_json_returns_none(cfg):
    client = LLMClient(cfg, guard=GoldGuard(), backend=lambda m, p, s: ("not json", 1, 1))
    data, _ = client.generate_json("x", {"type": "object"})
    assert data is None
