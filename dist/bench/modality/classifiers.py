"""Deterministic, non-LLM modality classifiers over sentence embeddings.

Two mechanisms, both trained ONLY on the templated dataset (the "easy" surface
forms), then tested on real varied text (the "hard" forms). This measures
GENERALIZATION beyond seen surface markers — the thing the frozen lexicon failed.

  RBFPrototype  — Granville/RBF-style, no DNN, no gradient training. For each
                  modality, store the embeddings of training examples as prototypes
                  (nodes β_k). Classify x by a Gaussian-kernel weighted vote:
                  score(c) = Σ_{k in c} exp(-τ · ||x - β_k||²). Pick argmax. This is
                  exactly the kernel machinery of the Alt-DNN paper: locations +
                  scale, deterministic, replicable, explainable (you can point at
                  the nearest prototype).
  SmallLogistic — logistic regression on the same embeddings. A tiny trained model
                  (sklearn), still deterministic and replicable, as a reference for
                  what a minimal learned classifier achieves.

Both expose .predict(text) -> modality, and RBFPrototype also returns a margin so
an abstention threshold can make it SAFE-but-incomplete (gate-style).
"""
from __future__ import annotations

import numpy as np

_MODEL = None


def _embedder():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        # small, multilingual, runs on CPU
        _MODEL = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    return _MODEL


def embed(texts):
    return _embedder().encode(list(texts), normalize_embeddings=True, show_progress_bar=False)


class RBFPrototype:
    """Gaussian-kernel prototype classifier (RBF, no DNN, no training step)."""

    def __init__(self, tau: float = 8.0):
        self.tau = tau
        self.protos: dict[str, np.ndarray] = {}

    def fit(self, texts, labels):
        X = embed(texts)
        for lab in set(labels):
            self.protos[lab] = X[[i for i, l in enumerate(labels) if l == lab]]
        return self

    def _scores(self, xvec):
        out = {}
        for lab, P in self.protos.items():
            d2 = np.sum((P - xvec) ** 2, axis=1)        # squared euclid to each node
            out[lab] = float(np.sum(np.exp(-self.tau * d2)))
        return out

    def predict(self, text, min_margin: float = 0.0):
        x = embed([text])[0]
        s = self._scores(x)
        ranked = sorted(s.items(), key=lambda kv: -kv[1])
        top, second = ranked[0], (ranked[1] if len(ranked) > 1 else (None, 0.0))
        margin = top[1] - second[1]
        if margin < min_margin:
            return None, margin            # abstain (safe-but-incomplete)
        return top[0], margin


class SmallLogistic:
    def __init__(self):
        self.clf = None

    def fit(self, texts, labels):
        from sklearn.linear_model import LogisticRegression
        X = embed(texts)
        self.clf = LogisticRegression(max_iter=1000, C=2.0).fit(X, labels)
        return self

    def predict(self, text):
        x = embed([text])
        return self.clf.predict(x)[0]
