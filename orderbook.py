"""Snapshot the Polymarket order book (top 5 levels each side) of every open
"Highest temperature in <city>" bucket. Read-only public endpoints, no key.
Only the Yes book is saved; the No book is its mirror (No ask = 1 - Yes bid).

Writes data/orderbook/<UTC date>/<UTC time>.csv
"""
import datetime as dt
import json
from pathlib import Path

import pandas as pd
import requests

CITIES = ["paris", "london", "munich"]
LEVELS = 5

now = dt.datetime.now(dt.UTC)
buckets = []  # (city, market date, bucket, yes token)
for city in CITIES:
    for i in range(-1, 4):  # yesterday (may still trade) .. +3 days
        day = now.date() + dt.timedelta(days=i)
        slug = f"highest-temperature-in-{city}-on-{day:%B}-{day.day}-{day.year}".lower()
        events = requests.get("https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=30).json()
        if events and not events[0].get("closed"):
            for m in events[0]["markets"]:
                buckets.append((city, day, m["groupItemTitle"], json.loads(m["clobTokenIds"])[0]))

books = requests.post("https://clob.polymarket.com/books",
                      json=[{"token_id": b[3]} for b in buckets], timeout=30).json()
books = {b["asset_id"]: b for b in books}

rows = []
for city, day, bucket, token in buckets:
    book = books.get(token, {"bids": [], "asks": []})
    for side, reverse in (("bid", True), ("ask", False)):  # best price first
        levels = sorted(book[side + "s"], key=lambda x: float(x["price"]), reverse=reverse)[:LEVELS]
        for level, x in enumerate(levels, start=1):
            rows.append({"snapshot_utc": now.strftime("%Y-%m-%d %H:%M"), "city": city, "date": day,
                         "bucket": bucket, "side": side, "level": level,
                         "price": float(x["price"]), "size": float(x["size"])})

out = Path("data/orderbook") / now.strftime("%Y-%m-%d")
out.mkdir(parents=True, exist_ok=True)
pd.DataFrame(rows).to_csv(out / now.strftime("%H%MZ.csv"), index=False)
print(f"saved {len(buckets)} buckets, {len(rows)} rows to {out}")
