"""Fine-tune the dense encoder on SWE-bench-train triples — FR-T3 (system S4).

Concept: same InfoNCE objective as `minimal_loop.py`, with two scale tricks.
(1) MultipleNegativesRankingLoss uses every other positive *and* every hard
negative in the batch as negatives, so a batch of 64 gives each issue 127
negatives. (2) The "Cached" variant (GradCache) makes batch 64 fit in a small
GPU: it first embeds the whole batch without gradients in mini-batches of 16,
computes the loss and the gradient w.r.t. the embeddings, then replays each
mini-batch with gradients enabled. Large effective batches matter for
contrastive learning because more negatives make the task harder.
An InformationRetrievalEvaluator on repository-disjoint validation pairs
measures retrieval before and after training.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from buglens.config import PROJECT_ROOT, Config, set_seed, write_meta  # noqa: E402
from buglens.utils import console, summary  # noqa: E402


def _imports():
    try:
        from sentence_transformers.sentence_transformer.evaluation import (
            InformationRetrievalEvaluator,
        )
        from sentence_transformers.sentence_transformer.losses import (
            CachedMultipleNegativesRankingLoss,
        )
        from sentence_transformers.sentence_transformer.training_args import BatchSamplers
    except ImportError:  # older sentence-transformers (e.g. on Kaggle)
        from sentence_transformers.evaluation import InformationRetrievalEvaluator
        from sentence_transformers.losses import CachedMultipleNegativesRankingLoss
        from sentence_transformers.training_args import BatchSamplers
    return InformationRetrievalEvaluator, CachedMultipleNegativesRankingLoss, BatchSamplers


def build_evaluator(val: pd.DataFrame, evaluator_cls):
    queries, corpus, relevant = {}, {}, {}
    doc_ids: dict[str, str] = {}

    def doc_id(text: str) -> str:
        if text not in doc_ids:
            doc_ids[text] = f"d{len(doc_ids)}"
            corpus[doc_ids[text]] = text
        return doc_ids[text]

    for i, row in enumerate(val.itertuples()):
        qid = f"q{i}"
        queries[qid] = row.anchor  # already carries the query prefix
        relevant[qid] = {doc_id(row.positive)}
        doc_id(row.negative)
    return evaluator_cls(queries=queries, corpus=corpus, relevant_docs=relevant,
                         name="val", accuracy_at_k=[1, 5, 10], mrr_at_k=[10],
                         ndcg_at_k=[10], show_progress_bar=False, write_csv=False)


def finetune(cfg: Config) -> Path:
    import torch
    from datasets import Dataset
    from sentence_transformers import (
        SentenceTransformer,
        SentenceTransformerTrainer,
        SentenceTransformerTrainingArguments,
    )

    from buglens.retrieval.dense import _patch_transformers

    _patch_transformers()
    set_seed(cfg.seed)
    t = cfg.training
    r = cfg.retrieval
    evaluator_cls, loss_cls, batch_samplers = _imports()
    pairs_dir = cfg.path("pairs")
    train_df = pd.read_parquet(pairs_dir / "train.parquet")
    val_df = pd.read_parquet(pairs_dir / "val.parquet")
    console.print(f"train pairs={len(train_df)} val pairs={len(val_df)}")

    model_id = r.dense_model_fallback if r.use_fallback_model else r.dense_model
    model = SentenceTransformer(model_id, trust_remote_code=True)
    model.max_seq_length = r.max_seq_length

    evaluator = build_evaluator(val_df, evaluator_cls)
    before = evaluator(model)
    console.print(f"before: {_short(before)}")

    train_ds = Dataset.from_pandas(train_df[["anchor", "positive", "negative"]],
                                   preserve_index=False)
    loss = loss_cls(model, mini_batch_size=t.mini_batch_size)
    out_dir = PROJECT_ROOT / r.finetuned_model
    ckpt_dir = cfg.path("models") / "checkpoints"
    args = SentenceTransformerTrainingArguments(
        output_dir=str(ckpt_dir),
        num_train_epochs=t.epochs,
        per_device_train_batch_size=t.batch_size,
        learning_rate=t.lr,
        warmup_ratio=t.warmup_ratio,
        fp16=bool(t.fp16) and torch.cuda.is_available(),
        seed=cfg.seed,
        batch_sampler=batch_samplers.NO_DUPLICATES,
        logging_steps=1,
        save_strategy="no",
        eval_strategy="no",
        report_to="none",
        dataloader_num_workers=0,
    )
    trainer = SentenceTransformerTrainer(model=model, args=args, train_dataset=train_ds,
                                         loss=loss)
    trainer.train()

    after = evaluator(model)
    console.print(f"after:  {_short(after)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save(str(out_dir))

    figures = cfg.path("reports") / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    logs = [x for x in trainer.state.log_history if "loss" in x]
    plt.figure(figsize=(6, 3.5))
    plt.plot([x["step"] for x in logs], [x["loss"] for x in logs], marker=".")
    plt.xlabel("step")
    plt.ylabel("training loss (CachedMNRL)")
    plt.title(f"Fine-tuning {model_id.split('/')[-1]} on SWE-bench-train")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(figures / "finetune_loss.png", dpi=150)
    plt.close()

    result = {"model": model_id, "train_pairs": len(train_df), "val_pairs": len(val_df),
              "before": before, "after": after,
              "loss_history": [(x["step"], x["loss"]) for x in logs]}
    (cfg.path("reports") / "finetune_eval.json").write_text(json.dumps(result, indent=2))
    write_meta(out_dir, cfg, filename="buglens_meta.json", base_model=model_id)
    console.print("\nShare the model (optional):")
    console.print(f"  kaggle datasets init -p {out_dir}")
    console.print(f"  kaggle datasets create -p {out_dir}")
    console.print(f"  huggingface-cli upload <user>/coderankembed-buglens-ft {out_dir}")
    console.print(f"  download into {r.finetuned_model}/ to use it as system S4.")
    summary("finetune", out=str(out_dir), **{k: f"{v:.3f}" for k, v in _short(after).items()})
    return out_dir


def _short(metrics: dict) -> dict:
    keep = {}
    for k, v in metrics.items():
        if any(s in k for s in ("accuracy@1", "accuracy@5", "accuracy@10", "mrr@10")):
            keep[k.replace("val_cosine_", "")] = v
    return keep
