"""Repeated-run experiment for the LLM reranker (report section: iterations / uncertainty).

The S7 prompt for 50 randomly sampled test issues (seed 42) is sent 3 times: repeat 0 is the
cached main run, repeats 1-2 are new, independent calls with identical prompts (temperature 0).
Output: reports/research/data/llm_repeats.csv, one row per (instance, repeat).
"""

import csv
import random
import time

from buglens.chunking.corpus import load_corpus
from buglens.config import PROJECT_ROOT, load_config
from buglens.data.prepare import load_labels
from buglens.data.swebench import load_split
from buglens.eval.evaluate import load_run
from buglens.llm.client import LLMClient
from buglens.llm.rerank import SCHEMA, build_prompt, parse_ranking

OUT = PROJECT_ROOT / "reports" / "research" / "data" / "llm_repeats.csv"


def main(n: int = 50, repeats: int = 3) -> None:
    cfg = load_config()
    insts = load_split(cfg, "test")
    sample = sorted(random.Random(42).sample(insts, n), key=lambda i: (i.repo, i.base_commit))
    base = {r.instance_id: r for r in load_run(cfg, "S5", "test")}
    labels = load_labels(cfg, "test")
    client = LLMClient(cfg)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["instance_id", "repo", "repeat", "top1_chunk", "top1_file", "ranking",
                    "gold_file_top1", "gold_func_in_top5", "tokens_in", "tokens_out",
                    "seconds", "cached", "valid_json", "timestamp"])
        for inst in sample:
            corpus = load_corpus(cfg, inst.repo, inst.base_commit)
            by_id = {c.chunk_id: c for c in corpus.chunks}
            head = sorted(base[inst.instance_id].functions, key=lambda c: c.rank)[:cfg.llm.rerank_top]
            shown = [by_id[c.chunk_id] for c in head]
            prompt = build_prompt(inst, shown, cfg)
            gold = labels[inst.instance_id]
            for r in range(repeats):
                t0 = time.perf_counter()
                data, usage = client.generate_json(prompt, SCHEMA, inst.instance_id,
                                                   "\n".join(c.text for c in shown), repeat=r)
                ranking = parse_ranking(data, [c.chunk_id for c in head])
                order = (ranking or []) + [c.chunk_id for c in head if c.chunk_id not in (ranking or [])]
                top1 = order[0]
                w.writerow([inst.instance_id, inst.repo, r, top1, top1.split("::")[0],
                            "|".join(order), int(top1.split("::")[0] in gold.files),
                            int(bool(set(order[:5]) & set(gold.functions))),
                            usage.tokens_in, usage.tokens_out,
                            round(usage.seconds if usage.cached else time.perf_counter() - t0, 3),
                            int(usage.cached), int(ranking is not None),
                            time.strftime("%Y-%m-%dT%H:%M:%S")])
                f.flush()
    print(client.report())


if __name__ == "__main__":
    main()
