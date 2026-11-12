"""Fetch the ECMWF ensembles (51 members) 2 m temperature at the grid point of each
Polymarket city and save each member's daily max. Source: Open-Meteo, free, no key.

Two models:
  ecmwf  IFS ensemble, physics model, 3-hourly output
  aifs   AIFS ensemble, ECMWF's AI model, 6-hourly output, available ~2 h earlier
Open-Meteo interpolates both to hourly values.
"""
import datetime as dt
from pathlib import Path

import pandas as pd
import requests

# ECMWF 0.25 deg grid point that best matched each settlement station's daily max (Nov 2025 - Nov 2026).
POINTS = {
    "paris": (49.0, 2.25, "Europe/Paris"),     # station LFPB, Le Bourget
    "london": (51.5, 0.25, "Europe/London"),   # station EGLC, London City
}
MODELS = {  # folder name: Open-Meteo model name
    "ecmwf": "ecmwf_ifs025_ensemble",
    "aifs": "ecmwf_aifs025_ensemble",
}
DAYS = 4  # today + 3 days; Polymarket lists each day ~2 days ahead

for folder, model in MODELS.items():
    # Which run Open-Meteo is serving (needed to know the lead time later).
    meta = requests.get(f"https://ensemble-api.open-meteo.com/data/{model}/static/meta.json", timeout=30).json()
    run = dt.datetime.fromtimestamp(meta["last_run_initialisation_time"], dt.UTC)
    # when the run was first downloadable = earliest possible buy time
    available = dt.datetime.fromtimestamp(meta["last_run_availability_time"], dt.UTC)

    for city, (lat, lon, tz) in POINTS.items():
        out = Path("data") / folder / city / run.strftime("run_%Y%m%dT%HZ")
        if out.exists():
            print("already saved", out)
            continue

        r = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": lat, "longitude": lon, "hourly": "temperature_2m",
            "models": model, "forecast_days": DAYS,
            "timezone": tz, "cell_selection": "nearest",
        }, timeout=30)
        r.raise_for_status()

        hourly = pd.DataFrame(r.json()["hourly"])  # one column per member
        hourly["time"] = pd.to_datetime(hourly["time"])
        daily_max = hourly.groupby(hourly["time"].dt.date).max(numeric_only=True)
        for table in (hourly, daily_max):
            table.insert(0, "run_utc", run.strftime("%Y-%m-%d %H:%M"))
            table.insert(1, "available_utc", available.strftime("%Y-%m-%d %H:%M"))

        out.mkdir(parents=True, exist_ok=True)
        hourly.to_csv(out / "hourly.csv", index=False)
        daily_max.round(2).to_csv(out / "daily_max.csv")
        print("saved", out)
