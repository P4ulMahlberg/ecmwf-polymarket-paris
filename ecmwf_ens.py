"""Fetch the ECMWF ensemble (51 members) 2 m temperature at the grid point of each
Polymarket city and save each member's daily max. Source: Open-Meteo, free, no key."""
import datetime as dt
from pathlib import Path

import pandas as pd
import requests

# ECMWF 0.25 deg grid point that best matched each settlement station's daily max (Nov 2025 - Nov 2026).
POINTS = {
    "paris": (49.0, 2.25, "Europe/Paris"),     # station LFPB, Le Bourget
    "london": (51.5, 0.25, "Europe/London"),   # station EGLC, London City
}
DAYS = 4  # today + 3 days; Polymarket lists each day ~2 days ahead

# Which ECMWF run Open-Meteo is serving (needed to know the lead time later).
meta = requests.get("https://ensemble-api.open-meteo.com/data/ecmwf_ifs025_ensemble/static/meta.json",
                    timeout=30).json()
run = dt.datetime.fromtimestamp(meta["last_run_initialisation_time"], dt.UTC)

for city, (lat, lon, tz) in POINTS.items():
    out = Path("data/ecmwf") / city / run.strftime("run_%Y%m%dT%HZ")
    if out.exists():
        print("already saved", out)
        continue

    r = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
        "latitude": lat, "longitude": lon, "hourly": "temperature_2m",
        "models": "ecmwf_ifs025", "forecast_days": DAYS,
        "timezone": tz, "cell_selection": "nearest",
    }, timeout=30)
    r.raise_for_status()

    hourly = pd.DataFrame(r.json()["hourly"])  # one column per member
    hourly["time"] = pd.to_datetime(hourly["time"])
    daily_max = hourly.groupby(hourly["time"].dt.date).max(numeric_only=True)

    out.mkdir(parents=True, exist_ok=True)
    hourly.to_csv(out / "hourly.csv", index=False)
    daily_max.round(2).to_csv(out / "daily_max.csv")
    print("saved", out)
