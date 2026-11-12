#!/usr/bin/env python3
"""Which ECMWF 0.25 deg grid point best matches the Polymarket settlement value at a station?

Truth: daily max of routine METAR temperatures (whole deg C, station local day), i.e. the
       value Polymarket settles on. Source: Iowa Environmental Mesonet METAR archive.
Model: ECMWF IFS 0.25 deg short-range daily max (Open-Meteo historical-forecast API) at the
       3x3 grid points around the station.

Scores each grid point on bias, MAE and how often (bias-corrected, rounded half-up)
it lands in the exact settlement bucket.

  python grid_fit.py                  # LFPB, last 365 days
  python grid_fit.py --station LFPG --days 180
"""
import argparse
import datetime as dt
import io
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from stations import STATIONS

IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
HIST = "https://historical-forecast-api.open-meteo.com/v1/forecast"
OUT = Path(__file__).parent / "data" / "grid_fit"
TEMP_RE = re.compile(r" (M?\d{2})/(M?\d{2}|//) ")


def metar_daily_max(station, tz, start, end):
    params = {
        "station": station, "data": "metar", "tz": "Etc/UTC", "format": "onlycomma",
        "latlon": "no", "missing": "M", "direct": "no",
        # IEM tags only on-the-hour reports as 3; LFPB's :30 reports are also routine METARs
        # (they count for Polymarket), and IEM files them under 4.
        "report_type": ["3", "4"],
        "year1": start.year, "month1": start.month, "day1": start.day,
        "year2": end.year, "month2": end.month, "day2": end.day,
    }
    for attempt in range(6):  # IEM rate-limits; back off and retry
        r = requests.get(IEM, params=params, timeout=300)
        if r.ok and not r.text.startswith("Too many"):
            break
        time.sleep(15 * (attempt + 1))
    else:
        raise SystemExit(f"IEM keeps refusing: {r.text[:200]}")
    df = pd.read_csv(io.StringIO(r.text))
    if df.empty:
        raise SystemExit("IEM returned no METARs")
    t = df.metar.str.extract(TEMP_RE)[0].dropna()
    df = df.loc[t.index].assign(temp_c=t.str.replace("M", "-").astype(int))
    df["date"] = pd.to_datetime(df.valid).dt.tz_localize("UTC").dt.tz_convert(tz).dt.date
    df = df[~df.metar.str.startswith("SPECI")]
    g = df.groupby("date").temp_c.agg(["max", "count"])
    return g[g["count"] >= 20]["max"].rename("obs")  # need near-complete day


def model_daily_max(lats, lons, tz, start, end):
    r = requests.get(HIST, params={
        "latitude": ",".join(map(str, lats)), "longitude": ",".join(map(str, lons)),
        "daily": "temperature_2m_max", "models": "ecmwf_ifs025", "timezone": tz,
        "start_date": start.isoformat(), "end_date": end.isoformat(), "cell_selection": "nearest",
    }, timeout=120)
    r.raise_for_status()
    res = r.json()
    cols, meta = {}, {}
    for j in res if isinstance(res, list) else [res]:
        key = f"{j['latitude']:.2f},{j['longitude']:.2f}"
        cols[key] = pd.Series(j["daily"]["temperature_2m_max"],
                              index=pd.to_datetime(j["daily"]["time"]).date, dtype=float)
        meta[key] = j["elevation"]
    return pd.DataFrame(cols), meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="LFPB")
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()

    lat, lon, tz, desc = STATIONS[args.station]
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=args.days)
    c_lat, c_lon = round(lat * 4) / 4, round(lon * 4) / 4
    lats = [c_lat + d for d in (-0.25, 0, 0.25) for _ in range(3)]
    lons = [c_lon + d for _ in range(3) for d in (-0.25, 0, 0.25)]

    obs = metar_daily_max(args.station, tz, start, end + dt.timedelta(days=1))
    fc, elev = model_daily_max(lats, lons, tz, start, end)
    df = fc.join(obs, how="inner").dropna()
    print(f"{args.station} ({desc}) at {lat},{lon}; {len(df)} days {df.index.min()} .. {df.index.max()}\n")

    rows = []
    for col in fc.columns:
        err = df[col] - df.obs
        bias = err.mean()
        hit = (np.floor(df[col] - bias + 0.5) == df.obs).mean()
        hit1 = (np.abs(np.floor(df[col] - bias + 0.5) - df.obs) <= 1).mean()
        glat, glon = map(float, col.split(","))
        km = np.hypot((glat - lat) * 111, (glon - lon) * 111 * np.cos(np.radians(lat)))
        rows.append(dict(grid_point=col, dist_km=round(km, 1), elev_m=elev[col], bias=bias,
                         mae=err.abs().mean(), mae_debiased=(err - bias).abs().mean(),
                         err_std=err.std(), exact_bucket=hit, within_1=hit1))
    score = pd.DataFrame(rows).sort_values("mae_debiased").round(3)

    out = OUT / args.station
    out.mkdir(parents=True, exist_ok=True)
    score.to_csv(out / "scores.csv", index=False)
    df.to_csv(out / "daily_obs_vs_model.csv")

    # bias by season: matters if one offset does not fit all
    best = score.iloc[0].grid_point
    month_bias = (df[best] - df.obs).groupby(pd.to_datetime(df.index).month).agg(["mean", "std", "count"]).round(2)
    month_bias.to_csv(out / f"monthly_bias_{best.replace(',', '_')}.csv")

    print(score.to_string(index=False))
    print(f"\nbest: {best}   monthly bias (model - obs):\n{month_bias.to_string()}")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
