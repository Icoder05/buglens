"""Teaching file: contrastive (InfoNCE) fine-tuning in plain PyTorch — FR-T4.

Concept: InfoNCE treats retrieval as classification. For a batch of B
(issue, code) pairs we embed all issues Q (B x d) and all code D (B x d),
compute the B x B similarity matrix S = Q @ D.T / tau, and apply cross-entropy
with the "correct class" of row i being column i. Every other code snippet in
the batch is a negative ("in-batch negatives"). tau (temperature) sharpens the
softmax. loss.backward() computes gradients for every encoder weight, and
optimizer.step() nudges the weights to raise S[i, i] relative to S[i, j].
`finetune.py` does the same thing at scale via sentence-transformers.
Run: uv run python -m buglens.training.minimal_loop
"""

import pandas as pd
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

from buglens.config import load_config, set_seed

MODEL = "BAAI/bge-small-en-v1.5"  # small (33M params) so the loop runs in a minute


def embed(model, tok, texts, device):
    batch = tok(texts, padding=True, truncation=True, max_length=256, return_tensors="pt")
    out = model(**batch.to(device)).last_hidden_state[:, 0]  # [CLS] pooling
    return F.normalize(out, dim=-1)                           # unit vectors -> cosine


def main(n_pairs: int = 200, batch_size: int = 16, epochs: int = 3, tau: float = 0.05):
    cfg = load_config()
    set_seed(cfg.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pairs = pd.read_parquet(cfg.path("pairs") / "train.parquet").head(n_pairs)
    prefix = cfg.retrieval.query_prefix
    anchors = [a.removeprefix(prefix) for a in pairs.anchor]
    positives = list(pairs.positive)

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)
    model.train()
    history = []
    for epoch in range(epochs):
        epoch_losses = []
        for i in range(0, len(anchors), batch_size):
            q = embed(model, tok, anchors[i:i + batch_size], device)     # (B, d)
            d = embed(model, tok, positives[i:i + batch_size], device)   # (B, d)
            logits = q @ d.T / tau                                       # (B, B)
            labels = torch.arange(len(q), device=device)                 # diagonal = positive
            loss = F.cross_entropy(logits, labels)
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            epoch_losses.append(loss.item())
        mean = sum(epoch_losses) / len(epoch_losses)
        history.append(mean)
        print(f"epoch {epoch + 1}: mean InfoNCE loss {mean:.4f}")
    assert history[-1] < history[0], "loss should decrease on the training pairs"
    print("loss decreased:", " -> ".join(f"{h:.4f}" for h in history))
    return history


if __name__ == "__main__":
    main()
