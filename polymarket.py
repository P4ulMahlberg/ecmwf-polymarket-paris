"""Fetch Polymarket "Highest temperature in <city>" markets for Paris and London: current
price per bucket and hourly price history. Read-only public endpoints, no key.

Usage: python polymarket.py                        today .. today+2
       python polymarket.py 2026-11-01 2026-11-11  date range
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import requests


CITIES = ["paris", "london"]


def fetch_day(city, day):
    slug = f"highest-temperature-in-{city}-on-{day:%B}-{day.day}-{day.year}".lower()
    events = requests.get("https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=30).json()
    if not events:
        return None
    event = events[0]

    # price history window: 3 days before the date until 2 days after
    start = int(dt.datetime.combine(day - dt.timedelta(days=3), dt.time(), dt.UTC).timestamp())
    buckets, history = [], []
    for m in event["markets"]:
        bucket = m["groupItemTitle"]  # e.g. "11°C", "5°C or below"
        buckets.append({"bucket": bucket, "yes_price": json.loads(m["outcomePrices"])[0],
                        "volume": m.get("volume"), "closed": m.get("closed")})
        yes_token = json.loads(m["clobTokenIds"])[0]
        h = requests.get("https://clob.polymarket.com/prices-history", params={
            "market": yes_token, "startTs": start, "endTs": start + 5 * 86400, "fidelity": 60,
        }, timeout=30).json()
        for p in h.get("history", []):
            history.append({"bucket": bucket, "time_utc": pd.to_datetime(p["t"], unit="s", utc=True),
                            "yes_price": p["p"]})
    return event, pd.DataFrame(buckets), pd.DataFrame(history)


today = dt.date.today()
start = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else today
end = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else today + dt.timedelta(days=2)

for city in CITIES:
    day = start
    while day <= end:
        result = fetch_day(city, day)
        if result is None:
            print(city, day, "no market")
        else:
            event, buckets, history = result
            out = Path("data/polymarket") / city / day.isoformat()
            out.mkdir(parents=True, exist_ok=True)
            buckets.to_csv(out / "buckets.csv", index=False)
            history.to_csv(out / "history.csv", index=False)
            # which station the market settles on has changed over time - always check
            (out / "resolution_source.txt").write_text(event.get("resolutionSource", "") + "\n")
            print(city, day, event.get("resolutionSource"))
        day += dt.timedelta(days=1)
