"""Chart CNN: "(Re-)Imag(in)ing Price Trends" (Jiang, Kelly & Xiu, 2023).

Renders 20-day candlestick images as 64x60 black-and-white bitmaps, runs them through a small CNN
trained on NSE stocks, and returns P(up over the next 5 trading days). The model is trained offline
by scripts/train_cnn.py and loaded lazily at first request.
"""
import json
import math
import os
import struct
import threading
import zlib

import numpy as np

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "models")
IMG_H, IMG_W = 64, 60  # height x width
WINDOW = 20  # trading days per image
PX_PER_DAY = 3  # pixels per trading day: left=open tick, middle=hl bar, right=close tick
VOL_HEIGHT = 10  # bottom pixels for volume bars

_model = None
_meta = None
_lock = threading.Lock()


def _load_model():
    global _model, _meta
    import torch
    meta_path = os.path.join(MODEL_DIR, "chart_cnn.json")
    pt_path = os.path.join(MODEL_DIR, "chart_cnn.pt")
    if not os.path.exists(pt_path) or not os.path.exists(meta_path):
        return
    with open(meta_path) as f:
        _meta = json.load(f)
    from .chart_cnn_model import ChartCNN
    model = ChartCNN()
    model.load_state_dict(torch.load(pt_path, map_location="cpu", weights_only=True))
    model.eval()
    _model = model


def get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _load_model()
    return _model, _meta


def render_image(closes: list[int], opens: list[int], highs: list[int],
                 lows: list[int], volumes: list[int]) -> np.ndarray:
    """Render a 64x60 uint8 image (0=black, 255=white) from 20 days of OHLCV.

    Layout: 20 days x 3px = 60px wide.  Top 54px for price (OHLC + 20-day MA line),
    bottom 10px for volume bars.
    """
    n = len(closes)
    assert n == WINDOW, f"Need {WINDOW} days, got {n}"
    img = np.zeros((IMG_H, IMG_W), dtype=np.uint8)

    price_h = IMG_H - VOL_HEIGHT  # 54 rows for price
    all_prices = highs + lows
    pmin, pmax = min(all_prices), max(all_prices)
    if pmax == pmin:
        pmax = pmin + 1

    def price_y(p: int) -> int:
        """Map price to row 0..price_h-1 (0=top=highest)."""
        return max(0, min(price_h - 1, int((pmax - p) / (pmax - pmin) * (price_h - 1))))

    # Draw candles
    for i in range(n):
        x_base = i * PX_PER_DAY
        oy = price_y(opens[i])
        cy = price_y(closes[i])
        hy = price_y(highs[i])
        ly = price_y(lows[i])

        # High-low bar in the middle column
        for y in range(hy, ly + 1):
            img[y, x_base + 1] = 255

        # Open tick on left column
        img[oy, x_base] = 255
        # Close tick on right column
        img[cy, x_base + 2] = 255

    # 20-day moving average line
    ma = [sum(closes[:i + 1]) / (i + 1) for i in range(n)]
    for i in range(n):
        y = price_y(int(ma[i]))
        x = i * PX_PER_DAY + 1
        img[y, x] = 255
        if i > 0:
            y_prev = price_y(int(ma[i - 1]))
            x_prev = (i - 1) * PX_PER_DAY + 1
            # Connect with a simple line
            steps = max(abs(y - y_prev), abs(x - x_prev), 1)
            for s in range(steps + 1):
                yy = int(y_prev + (y - y_prev) * s / steps)
                xx = int(x_prev + (x - x_prev) * s / steps)
                if 0 <= yy < price_h and 0 <= xx < IMG_W:
                    img[yy, xx] = 255

    # Volume bars at the bottom
    max_vol = max(volumes) if max(volumes) > 0 else 1
    for i in range(n):
        bar_h = max(1, int(volumes[i] / max_vol * VOL_HEIGHT))
        x_base = i * PX_PER_DAY
        for dy in range(bar_h):
            y = IMG_H - 1 - dy
            img[y, x_base] = 255
            img[y, x_base + 1] = 255
            img[y, x_base + 2] = 255

    return img


def predict(img: np.ndarray) -> float | None:
    """P(up over the next 5 trading days) from a 64x60 image. None if model not loaded."""
    model, meta = get_model()
    if model is None:
        return None
    import torch
    t = torch.from_numpy(img).float().unsqueeze(0).unsqueeze(0) / 255.0  # (1, 1, 64, 60)
    with torch.no_grad():
        logits = model(t)
        prob = torch.softmax(logits, dim=1)[0, 1].item()  # class 1 = up
    return round(prob, 3)


def image_to_png(img: np.ndarray) -> bytes:
    """Encode a 2D uint8 array as a minimal grayscale PNG (no Pillow needed)."""
    h, w = img.shape

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    # IHDR
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)  # 8-bit grayscale
    # IDAT: each row gets a filter byte (0 = none)
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))
    compressed = zlib.compress(raw)

    out = b"\x89PNG\r\n\x1a\n"
    out += chunk(b"IHDR", ihdr)
    out += chunk(b"IDAT", compressed)
    out += chunk(b"IEND", b"")
    return out


def chart_for_day(closes_by_date: dict, ohlcv_by_date: dict,
                  day, window: int = WINDOW) -> dict | None:
    """Build the chart image ending on `day` and return prediction + base64 PNG.

    ohlcv_by_date: {date: (open, high, low, close, volume)} in paise.
    Returns {"prob_up": float, "image_b64": str, "accuracy": float, "baseline": float} or None.
    """
    import base64

    sorted_dates = sorted(d for d in ohlcv_by_date if d <= day)
    if len(sorted_dates) < window:
        return None
    dates = sorted_dates[-window:]
    opens = [ohlcv_by_date[d][0] for d in dates]
    highs = [ohlcv_by_date[d][1] for d in dates]
    lows = [ohlcv_by_date[d][2] for d in dates]
    closes = [ohlcv_by_date[d][3] for d in dates]
    volumes = [ohlcv_by_date[d][4] for d in dates]

    img = render_image(closes, opens, highs, lows, volumes)
    prob = predict(img)
    png = image_to_png(img)
    b64 = base64.b64encode(png).decode()

    _, meta = get_model()
    return {
        "prob_up": prob,
        "image_b64": b64,
        "accuracy": meta.get("accuracy") if meta else None,
        "baseline": meta.get("baseline") if meta else None,
        "auc": meta.get("auc") if meta else None,
    }
