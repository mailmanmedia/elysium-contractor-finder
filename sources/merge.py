"""
Merge contractors from multiple sources into a single deduplicated dataframe.

Dedup key: normalized company name. When duplicates exist, we keep the row
with the highest jobs_count, and merge phones / addresses / trades / sources.
"""
from __future__ import annotations

import pandas as pd

STANDARD_COLS = [
    "contractor_name_norm",
    "contractor_name",
    "trades",
    "trades_str",
    "phone",
    "email",
    "website",
    "address",
    "city",
    "state",
    "zipcode",
    "latitude",
    "longitude",
    "jobs_count",
    "total_reported_cost",
    "last_seen",
    "license_number",
    "license_status",
    "expiration_date",
    "contractor_type",
    "source",
    "sources",
]


def _ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=STANDARD_COLS)
    df = df.copy()
    for c in STANDARD_COLS:
        if c not in df.columns:
            if c in ("jobs_count", "total_reported_cost"):
                df[c] = 0
            elif c == "last_seen":
                df[c] = pd.NaT
            else:
                df[c] = ""
    # Coerce last_seen to datetime so groupby max() doesn't compare Timestamp vs str.
    df["last_seen"] = pd.to_datetime(df["last_seen"], errors="coerce")
    return df[STANDARD_COLS]


def _first_nonempty(series: pd.Series) -> str:
    for v in series:
        if isinstance(v, str) and v.strip():
            return v
        if v is not None and not isinstance(v, str) and str(v).strip():
            return str(v)
    return ""


def merge_sources(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [_ensure_cols(f) for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=STANDARD_COLS)

    cat = pd.concat(frames, ignore_index=True)

    def _merge_trades(rows: pd.Series) -> list[str]:
        out: set[str] = set()
        for v in rows:
            if isinstance(v, list):
                out.update(v)
            elif isinstance(v, str) and v:
                out.update([t.strip() for t in v.split(",") if t.strip()])
        return sorted(out)

    grouped = (
        cat.groupby("contractor_name_norm", dropna=False)
        .agg(
            contractor_name=("contractor_name", _first_nonempty),
            trades=("trades", _merge_trades),
            phone=("phone", _first_nonempty),
            email=("email", _first_nonempty),
            website=("website", _first_nonempty),
            address=("address", _first_nonempty),
            city=("city", _first_nonempty),
            state=("state", _first_nonempty),
            zipcode=("zipcode", _first_nonempty),
            latitude=("latitude", _first_nonempty),
            longitude=("longitude", _first_nonempty),
            jobs_count=("jobs_count", "max"),
            total_reported_cost=("total_reported_cost", "max"),
            last_seen=("last_seen", "max"),
            license_number=("license_number", _first_nonempty),
            license_status=("license_status", _first_nonempty),
            expiration_date=("expiration_date", _first_nonempty),
            contractor_type=("contractor_type", _first_nonempty),
            sources=("source", lambda s: ", ".join(sorted({x for x in s if isinstance(x, str) and x.strip()}))),
        )
        .reset_index()
    )

    grouped["trades_str"] = grouped["trades"].map(lambda L: ", ".join(L))
    grouped["source"] = grouped["sources"]
    return grouped.sort_values(["jobs_count", "total_reported_cost"], ascending=False).reset_index(drop=True)
