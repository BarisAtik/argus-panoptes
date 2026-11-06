# Transformer on the proxy: plan written before any result

Every proxy result so far came from sparse linear models. This is the first real pretrained
encoder: RoBERTa from spaCy's `en_core_web_trf` wheel (`ntl.local_roberta`), on CPU.

**Fixed in advance**

- Fresh splits, seeds 100 and up. Seeds 0 to 9 were looked at in earlier experiments.
- Reference: the TF-IDF + masked blend, which is the kernel's current default.
- Candidates: frozen mean-pooled embeddings + logistic regression (C=0.01, not tuned), fine-tuned
  RoBERTa, and the equal geometric blend of fine-tuned + TF-IDF + masked.
- Settings: 3 epochs, batch 8, 192 tokens, lr 2e-5, label smoothing 0.05. No tuning on these
  holdouts. 192 tokens truncates the longest passages, a CPU budget choice.
- A candidate wins only if its paired prompt-bootstrap CI clears zero on every split run.

**Predictions**

1. Fine-tuned beats the sparse blend. Public reports put fine-tuned LLMs far ahead of classical
   models on the real data, though with bigger models, GPUs and far more data.
2. Frozen embeddings lose to the sparse blend: they were trained to capture meaning, not style.
3. Tuned + sparse beats tuned alone, because the errors should differ.
4. Under a genre change a tuned encoder falls as hard as TF-IDF, about half its score.
