from buglens.config import load_config
from buglens.demo.app import take_llm_quota


def test_daily_llm_quota_caps_answers(tmp_path):
    cfg = load_config()
    cfg["paths"] = {**cfg["paths"], "cache": str(tmp_path)}
    cfg["demo"] = {"ask_daily_limit": 2}
    assert [take_llm_quota(cfg) for _ in range(4)] == [True, True, False, False]
