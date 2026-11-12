"""Fetch the ECMWF ensemble (51 members) 2 m temperature for the Paris-Le Bourget grid
point and save each member's daily max. Source: Open-Meteo, free, no key."""
import datetime as dt
from pathlib import Path

import pandas as pd
import requests

# ECMWF 0.25 deg grid point that best matched the LFPB (Le Bourget) daily max.
LAT, LON = 49.0, 2.25
DAYS = 4  # today + 3 days; Polymarket lists each day ~2 days ahead

# Which ECMWF run Open-Meteo is serving (needed to know the lead time later).
meta = requests.get("https://ensemble-api.open-meteo.com/data/ecmwf_ifs025_ensemble/static/meta.json",
                    timeout=30).json()
run = dt.datetime.fromtimestamp(meta["last_run_initialisation_time"], dt.UTC)
out = Path("data/ecmwf") / run.strftime("run_%Y%m%dT%HZ")
if out.exists():
    print("already saved", out)
    raise SystemExit

r = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
    "latitude": LAT, "longitude": LON, "hourly": "temperature_2m",
    "models": "ecmwf_ifs025", "forecast_days": DAYS,
    "timezone": "Europe/Paris", "cell_selection": "nearest",
}, timeout=30)
r.raise_for_status()

hourly = pd.DataFrame(r.json()["hourly"])  # one column per member
hourly["time"] = pd.to_datetime(hourly["time"])
daily_max = hourly.groupby(hourly["time"].dt.date).max(numeric_only=True)

out.mkdir(parents=True, exist_ok=True)
hourly.to_csv(out / "hourly.csv", index=False)
daily_max.round(2).to_csv(out / "daily_max.csv")

print(daily_max.T.describe().round(1))
print("saved to", out)
