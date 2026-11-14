"""Fetch ensemble 2 m temperature at the grid point of each Polymarket city and save
each member's daily max. Source: Open-Meteo, free, no key.

Three models:
  ecmwf    ECMWF IFS ensemble, 51 members, 0.25 deg, 3-hourly output, 4 runs/day
  aifs     ECMWF AIFS ensemble (AI model), 51 members, 6-hourly, ~2 h earlier than ecmwf
  icon_d2  DWD ICON-D2-EPS, 20 members, 2 km, hourly, 8 runs/day, only 48 h ahead
Open-Meteo interpolates all to hourly values.

available_utc = when the run went online (earliest buy time). Exception: for icon_d2
Open-Meteo's metadata is stale, so its run time is derived from the forecast end
(+48 h) and available_utc is the time we fetched it (an upper bound).
"""
import datetime as dt
from pathlib import Path

import pandas as pd
import requests

# station: settlement airport, used for the 2 km icon_d2 grid.
# ecmwf_grid: ECMWF 0.25 deg grid point that best matched the station's daily max
# (Nov 2025 - Nov 2026), used for ecmwf and aifs.
POINTS = {
    "paris":  {"station": (48.9694, 2.4414), "ecmwf_grid": (49.0, 2.25), "tz": "Europe/Paris"},   # LFPB
    "london": {"station": (51.5053, 0.0553), "ecmwf_grid": (51.5, 0.25), "tz": "Europe/London"},  # EGLC
    "munich": {"station": (48.3538, 11.7861), "ecmwf_grid": (48.5, 12.0), "tz": "Europe/Berlin"}, # EDDM
}
MODELS = {  # folder name: Open-Meteo model name
    "ecmwf": "ecmwf_ifs025_ensemble",
    "aifs": "ecmwf_aifs025_ensemble",
    "icon_d2": "icon_d2_eps",
}
DAYS = 4  # today + 3 days; Polymarket lists each day ~2 days ahead

for folder, model in MODELS.items():
    if folder != "icon_d2":
        # Which run Open-Meteo is serving (needed to know the lead time later).
        meta = requests.get(f"https://ensemble-api.open-meteo.com/data/{model}/static/meta.json", timeout=30).json()
        run = dt.datetime.fromtimestamp(meta["last_run_initialisation_time"], dt.UTC)
        available = dt.datetime.fromtimestamp(meta["last_run_availability_time"], dt.UTC)

    for city, p in POINTS.items():
        lat, lon = p["station"] if folder == "icon_d2" else p["ecmwf_grid"]
        tz = p["tz"]
        r = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": lat, "longitude": lon, "hourly": "temperature_2m",
            "models": model, "forecast_days": DAYS,
            "timezone": tz, "cell_selection": "nearest",
        }, timeout=30)
        r.raise_for_status()

        hourly = pd.DataFrame(r.json()["hourly"])  # one column per member
        hourly["time"] = pd.to_datetime(hourly["time"])

        if folder == "icon_d2":
            last = hourly.dropna()["time"].max().tz_localize(tz).tz_convert("UTC")
            run = (last - pd.Timedelta(hours=48)).to_pydatetime()
            available = dt.datetime.now(dt.UTC)

        out = Path("data") / folder / city / run.strftime("run_%Y%m%dT%HZ")
        if out.exists():
            print("already saved", out)
            continue

        # daily max only for complete days (23 h allows the daylight-saving day)
        daily_max = hourly.groupby(hourly["time"].dt.date).max(numeric_only=True, min_count=23).dropna(how="all")
        for table in (hourly, daily_max):
            table.insert(0, "run_utc", run.strftime("%Y-%m-%d %H:%M"))
            table.insert(1, "available_utc", available.strftime("%Y-%m-%d %H:%M"))

        out.mkdir(parents=True, exist_ok=True)
        hourly.to_csv(out / "hourly.csv", index=False)
        daily_max.round(2).to_csv(out / "daily_max.csv")
        print("saved", out)
