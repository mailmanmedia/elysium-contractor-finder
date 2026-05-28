"""
IDFPR (Illinois Department of Financial & Professional Regulation) licensed
contractor lookups.

IDFPR publishes weekly Excel rosters of currently-licensed professionals:
  https://idfpr.illinois.gov/profs/licenselookup.html

The "Roofing Contractor" and "Plumbing Contractor" rosters are public.
Electrical licensing is mostly handled at the municipal level (e.g. the City
of Chicago Electrical Contractor Registration).

Because IDFPR's download URLs change each release, this module supports two
modes:

1. Drop a downloaded roster .xlsx/.csv into ``data/idfpr/`` and the loader
   will pick it up automatically.
2. Override the URL at runtime via the ``url`` argument.

Expected columns in the IDFPR Excel: License Number, Licensee Name, Address,
City, State, Zip, License Status, Original Issue Date, Expiration Date.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .common import normalize_company

LOCAL_DIR = Path(__file__).resolve().parent.parent / "data" / "idfpr"
LOCAL_DIR.mkdir(parents=True, exist_ok=True)


def _coerce(df: pd.DataFrame, trade: str) -> pd.DataFrame:
    # Try to standardize a few common column names.
    rename_map = {}
    for c in df.columns:
        cl = c.strip().lower()
        if cl in ("licensee name", "business name", "licensee", "name"):
            rename_map[c] = "contractor_name"
        elif cl in ("address", "business address", "address line 1"):
            rename_map[c] = "address"
        elif cl == "city":
            rename_map[c] = "city"
        elif cl in ("state", "st"):
            rename_map[c] = "state"
        elif cl in ("zip", "zipcode", "zip code"):
            rename_map[c] = "zipcode"
        elif cl in ("license number", "license #", "license_no"):
            rename_map[c] = "license_number"
        elif cl in ("license status", "status"):
            rename_map[c] = "license_status"
        elif cl in ("expiration date", "expires", "expire date"):
            rename_map[c] = "expiration_date"
        elif "phone" in cl:
            rename_map[c] = "phone"
    df = df.rename(columns=rename_map)
    if "contractor_name" not in df.columns:
        return pd.DataFrame()

    keep = [c for c in ["contractor_name", "address", "city", "state", "zipcode",
                        "license_number", "license_status", "expiration_date", "phone"]
            if c in df.columns]
    df = df[keep].copy()
    df["contractor_name_norm"] = df["contractor_name"].astype(str).map(normalize_company)
    df["trades"] = [[trade] for _ in range(len(df))]
    df["trades_str"] = trade
    df["source"] = f"IDFPR ({trade})"
    df["jobs_count"] = 0
    df["total_reported_cost"] = 0.0
    return df


def load_local() -> pd.DataFrame:
    """Read any IDFPR rosters the user has dropped into data/idfpr/.

    Filename convention (case-insensitive substring):
      * contains "roof"    -> Roofing
      * contains "plumb"   -> Plumbing
      * contains "elect"   -> Electrical
      * otherwise          -> file stem used as trade label
    """
    frames = []
    for path in LOCAL_DIR.glob("*"):
        if path.suffix.lower() not in (".xlsx", ".xls", ".csv"):
            continue
        name = path.stem.lower()
        if "roof" in name:
            trade = "Roofing"
        elif "plumb" in name:
            trade = "Plumbing"
        elif "elect" in name:
            trade = "Electrical"
        else:
            trade = path.stem.replace("_", " ").title()

        try:
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(path, dtype=str)
            else:
                df = pd.read_excel(path, dtype=str)
        except Exception as e:  # noqa: BLE001
            print(f"[idfpr] failed to read {path.name}: {e}")
            continue

        frames.append(_coerce(df, trade))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
