"""FinBERT headline sentiment scoring (ProsusAI/finbert, CPU only).

Loads the model lazily in a background thread so the server starts fast. Headlines are batched
and cached by title so the same headline is never scored twice in a session.
"""
import threading
from dataclasses import dataclass

_model = None
_tokenizer = None
_ready = threading.Event()
_lock = threading.Lock()
_cache: dict[str, "Sentiment"] = {}

MODEL_ID = "ProsusAI/finbert"


@dataclass
class Sentiment:
    label: str        # positive | negative | neutral
    pos: float
    neg: float
    neu: float
    score: float      # P(pos) - P(neg), in [-1, 1]


def warm():
    """Start loading the model in a background thread; call at server startup."""
    t = threading.Thread(target=_load, daemon=True)
    t.start()


def _load():
    global _model, _tokenizer
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    _model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID)
    _model.eval()
    _ready.set()


def is_ready() -> bool:
    return _ready.is_set()


def score_headlines(titles: list[str], timeout: float = 30.0) -> list[Sentiment | None]:
    """Score a batch of headline titles. Returns None for each that fails or times out."""
    if not titles:
        return []
    if not _ready.wait(timeout):
        return [None] * len(titles)

    # Check cache first
    results: list[Sentiment | None] = [None] * len(titles)
    to_run: list[tuple[int, str]] = []
    with _lock:
        for i, t in enumerate(titles):
            if t in _cache:
                results[i] = _cache[t]
            else:
                to_run.append((i, t))

    if not to_run:
        return results

    import torch
    indices, texts = zip(*to_run)
    try:
        inputs = _tokenizer(list(texts), padding=True, truncation=True, max_length=128,
                            return_tensors="pt")
        with torch.no_grad():
            logits = _model(**inputs).logits
        probs = torch.softmax(logits, dim=1).cpu().numpy()
        # FinBERT labels: 0=positive, 1=negative, 2=neutral
        labels = ["positive", "negative", "neutral"]
        with _lock:
            for j, idx in enumerate(indices):
                p = probs[j]
                s = Sentiment(
                    label=labels[int(p.argmax())],
                    pos=round(float(p[0]), 3),
                    neg=round(float(p[1]), 3),
                    neu=round(float(p[2]), 3),
                    score=round(float(p[0] - p[1]), 3),
                )
                _cache[texts[j]] = s
                results[idx] = s
    except Exception:
        pass
    return results


def score_one(title: str, timeout: float = 30.0) -> Sentiment | None:
    r = score_headlines([title], timeout)
    return r[0] if r else None
