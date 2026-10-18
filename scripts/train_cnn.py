#!/usr/bin/env python3
"""Train the chart CNN on ~200 liquid NSE stocks (2017–present).

Usage:  .venv/bin/python scripts/train_cnn.py

Downloads daily data via yfinance, renders 64x60 candlestick images, trains a small CNN,
and saves the model + metrics to data/models/.  RAM-conscious: images are uint8.
"""
import csv
import datetime as dt
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

# Add project root to path so we can import the shared model and renderer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.app.chart_cnn_model import ChartCNN
from backend.app.chart_cnn import render_image, IMG_H, IMG_W, WINDOW

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "models")
TRAIN_CUT = dt.date(2024, 7, 1)
VAL_CUT = dt.date(2025, 7, 1)
FORWARD_DAYS = 5
STEP = 5       # one sample every 5 trading days per stock (saves RAM)
TOP_N = 200    # top stocks by turnover
EPOCHS = 8
BATCH = 64
LR = 1e-3


def top_stocks(n: int = TOP_N) -> list[str]:
    """Top N EQ stocks by turnover from the latest bhavcopy."""
    nse_dir = os.path.join(os.path.dirname(__file__), "..", "data", "nse")
    bhavs = sorted(f for f in os.listdir(nse_dir) if f.startswith("sec_bhavdata_full"))
    if not bhavs:
        raise FileNotFoundError("No bhavcopy in data/nse/")
    path = os.path.join(nse_dir, bhavs[-1])
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            sym = row.get("SYMBOL", "").strip()
            series = row.get(" SERIES", row.get("SERIES", "")).strip()
            turnover = row.get(" TURNOVER_LACS", row.get("TURNOVER_LACS", "0")).strip()
            if series == "EQ" and sym:
                try:
                    rows.append((sym, float(turnover)))
                except ValueError:
                    pass
    # Exclude common ETFs
    etfs = {"NIFTYBEES", "BANKBEES", "JUNIORBEES", "GOLDBEES", "LIQUIDBEES", "SETFNIF50",
            "SETFNIFBK", "MON100", "ICICIB22", "LIQUIDETF"}
    rows = [(s, t) for s, t in rows if s not in etfs]
    rows.sort(key=lambda x: -x[1])
    return [s for s, _ in rows[:n]]


def download_data(symbols: list[str]) -> dict:
    """Download daily OHLCV from yfinance for each symbol. Returns {symbol: DataFrame}."""
    import yfinance as yf
    data = {}
    total = len(symbols)
    for i, sym in enumerate(symbols):
        ticker = f"{sym}.NS"
        print(f"  [{i+1}/{total}] {ticker}...", end=" ", flush=True)
        try:
            df = yf.download(ticker, start="2017-01-01", auto_adjust=True,
                             progress=False, threads=False)
            if len(df) > 100:
                data[sym] = df
                print(f"{len(df)} days")
            else:
                print("too few days, skipped")
        except Exception as e:
            print(f"error: {e}")
        time.sleep(0.1)  # be nice to Yahoo
    return data


def build_samples(data: dict) -> tuple:
    """Build (images, labels, dates, symbols) from the downloaded data."""
    images, labels, dates_list, syms_list = [], [], [], []
    for sym, df in data.items():
        df = df.sort_index()
        opens = df["Open"].values
        highs = df["High"].values
        lows = df["Low"].values
        closes = df["Close"].values
        volumes = df["Volume"].values
        idx_dates = df.index.date if hasattr(df.index, 'date') else [d.date() for d in df.index]

        n = len(df)
        for start in range(0, n - WINDOW - FORWARD_DAYS, STEP):
            end = start + WINDOW
            future = end + FORWARD_DAYS
            if future > n:
                break

            day = idx_dates[end - 1]
            # Label: 1 if price is up after FORWARD_DAYS
            label = 1 if closes[future - 1] > closes[end - 1] else 0

            # Convert to paise (int) for the renderer
            o = [int(float(opens[start + j]) * 100) for j in range(WINDOW)]
            h = [int(float(highs[start + j]) * 100) for j in range(WINDOW)]
            l = [int(float(lows[start + j]) * 100) for j in range(WINDOW)]
            c = [int(float(closes[start + j]) * 100) for j in range(WINDOW)]
            v = [int(float(volumes[start + j])) for j in range(WINDOW)]

            # Skip if any price is zero or negative
            if min(o + h + l + c) <= 0 or min(v) < 0:
                continue

            img = render_image(c, o, h, l, v)
            images.append(img)
            labels.append(label)
            dates_list.append(day)
            syms_list.append(sym)

    return np.array(images, dtype=np.uint8), np.array(labels), dates_list, syms_list


def train():
    print("=== Chart CNN Training ===\n")

    # 1. Get top stocks
    print("1. Finding top stocks by turnover...")
    symbols = top_stocks()
    print(f"   {len(symbols)} stocks selected\n")

    # 2. Download data
    print("2. Downloading daily data from Yahoo Finance...")
    data = download_data(symbols)
    print(f"   Got data for {len(data)} stocks\n")

    # 3. Build samples
    print("3. Building chart images...")
    images, labels, dates, syms = build_samples(data)
    print(f"   {len(images)} samples, {labels.mean():.1%} up, ~{images.nbytes / 1e6:.0f} MB\n")

    # 4. Time split
    train_mask = np.array([d < TRAIN_CUT for d in dates])
    val_mask = np.array([(d >= TRAIN_CUT) & (d < VAL_CUT) for d in dates])
    test_mask = np.array([d >= VAL_CUT for d in dates])

    X_train = torch.from_numpy(images[train_mask]).float().unsqueeze(1) / 255.0
    y_train = torch.from_numpy(labels[train_mask]).long()
    X_val = torch.from_numpy(images[val_mask]).float().unsqueeze(1) / 255.0
    y_val = torch.from_numpy(labels[val_mask]).long()
    X_test = torch.from_numpy(images[test_mask]).float().unsqueeze(1) / 255.0
    y_test = torch.from_numpy(labels[test_mask]).long()

    print(f"   Train: {len(X_train)} | Val: {len(X_val)} | Test: {len(X_test)}")
    print(f"   Train up rate: {y_train.float().mean():.3f}")
    print(f"   Test up rate:  {y_test.float().mean():.3f}\n")

    # 5. Train
    print("4. Training CNN...")
    model = ChartCNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    criterion = nn.CrossEntropyLoss()

    train_ds = TensorDataset(X_train, y_train)
    val_ds = TensorDataset(X_val, y_val)
    train_dl = DataLoader(train_ds, batch_size=BATCH, shuffle=True, num_workers=0)
    val_dl = DataLoader(val_ds, batch_size=BATCH, shuffle=False, num_workers=0)

    best_val_loss = float("inf")
    patience = 2
    wait = 0

    for epoch in range(EPOCHS):
        model.train()
        losses = []
        for xb, yb in train_dl:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            losses.append(loss.item())

        model.eval()
        val_losses = []
        correct = 0
        total = 0
        with torch.no_grad():
            for xb, yb in val_dl:
                out = model(xb)
                val_losses.append(criterion(out, yb).item())
                correct += (out.argmax(1) == yb).sum().item()
                total += len(yb)

        val_loss = np.mean(val_losses)
        val_acc = correct / total if total else 0
        print(f"   Epoch {epoch+1}/{EPOCHS}: train_loss={np.mean(losses):.4f}  "
              f"val_loss={val_loss:.4f}  val_acc={val_acc:.3f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            wait = 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            wait += 1
            if wait >= patience:
                print(f"   Early stopping at epoch {epoch+1}")
                break

    model.load_state_dict(best_state)
    print()

    # 6. Test
    print("5. Evaluating on test set...")
    model.eval()
    test_dl = DataLoader(TensorDataset(X_test, y_test), batch_size=BATCH, shuffle=False)
    all_probs = []
    all_preds = []
    all_true = []
    with torch.no_grad():
        for xb, yb in test_dl:
            probs = torch.softmax(model(xb), dim=1)[:, 1]
            preds = (probs > 0.5).long()
            all_probs.extend(probs.numpy().tolist())
            all_preds.extend(preds.numpy().tolist())
            all_true.extend(yb.numpy().tolist())

    all_probs = np.array(all_probs)
    all_preds = np.array(all_preds)
    all_true = np.array(all_true)

    accuracy = (all_preds == all_true).mean()
    baseline = max(all_true.mean(), 1 - all_true.mean())

    # AUC (manual, no sklearn needed)
    pos = all_probs[all_true == 1]
    neg = all_probs[all_true == 0]
    if len(pos) > 0 and len(neg) > 0:
        # Wilcoxon-Mann-Whitney statistic
        auc = np.mean(np.array([p > n for p in pos for n in neg], dtype=float))
    else:
        auc = 0.5

    # Decile analysis
    sorted_idx = np.argsort(-all_probs)
    decile_size = len(all_probs) // 10
    top_decile_up = all_true[sorted_idx[:decile_size]].mean() if decile_size > 0 else 0
    bottom_decile_up = all_true[sorted_idx[-decile_size:]].mean() if decile_size > 0 else 0

    print(f"   Accuracy:     {accuracy:.3f}")
    print(f"   Baseline:     {baseline:.3f} (majority class)")
    print(f"   AUC:          {auc:.3f}")
    print(f"   Top decile:   {top_decile_up:.3f} up rate")
    print(f"   Bottom decile: {bottom_decile_up:.3f} up rate")

    # 7. Save
    os.makedirs(OUT_DIR, exist_ok=True)
    pt_path = os.path.join(OUT_DIR, "chart_cnn.pt")
    meta_path = os.path.join(OUT_DIR, "chart_cnn.json")

    torch.save(model.state_dict(), pt_path)
    meta = {
        "accuracy": round(float(accuracy), 4),
        "baseline": round(float(baseline), 4),
        "auc": round(float(auc), 4),
        "top_decile_up_rate": round(float(top_decile_up), 4),
        "bottom_decile_up_rate": round(float(bottom_decile_up), 4),
        "test_samples": int(len(all_true)),
        "train_samples": int(len(X_train)),
        "val_samples": int(len(X_val)),
        "test_up_rate": round(float(all_true.mean()), 4),
        "stocks": len(data),
        "window": WINDOW,
        "forward_days": FORWARD_DAYS,
        "trained": dt.datetime.now().isoformat(timespec="minutes"),
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n   Saved to {pt_path}")
    print(f"   Metrics in {meta_path}")
    print(f"\n=== Done ===")


if __name__ == "__main__":
    train()
