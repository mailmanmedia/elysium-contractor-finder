"""
City of Chicago contract awards.

Dataset: "Contracts" on the Chicago Data Portal.
Endpoint: https://data.cityofchicago.org/resource/rsxa-ify5.json
Fields include vendor name, address, contract description, award amount,
start/end date, department.
"""
from __future__ import annotations

import pandas as pd

from .common import env, http_get_json, normalize_company
from .trades import classify

ENDPOINT = "https://data.cityofchicago.org/resource/rsxa-ify5.json"


def _headers() -> dict:
    tok = env("SOCRATA_APP_TOKEN")
    return {"X-App-Token": tok} if tok else {}


def fetch(limit: int = 20000, start_date: str | None = "2020-01-01") -> pd.DataFrame:
    params = {"$limit": min(limit, 50000), "$order": "start_date DESC"}
    if start_date:
        params["$where"] = f"start_date >= '{start_date}T00:00:00.000'"
    rows = http_get_json(ENDPOINT, params=params, headers=_headers())
    return pd.DataFrame(rows)


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    name_col = next((c for c in ("vendor_name", "vendor", "name") if c in df.columns), None)
    if name_col is None:
        return pd.DataFrame()

    df = df.rename(columns={name_col: "contractor_name"})
    for src, dst in [
        ("vendor_address_1", "address"),
        ("address_1", "address"),
        ("vendor_city", "city"),
        ("city", "city"),
        ("vendor_state", "state"),
        ("state", "state"),
        ("vendor_zip", "zipcode"),
        ("zip", "zipcode"),
    ]:
        if src in df.columns and dst not in df.columns:
            df = df.rename(columns={src: dst})

    award_col = next((c for c in ("award_amount", "contract_amount", "amount") if c in df.columns), None)
    desc_col = next((c for c in ("contract_description", "description", "purchase_order_description") if c in df.columns), None)

    df["contractor_name_norm"] = df["contractor_name"].astype(str).map(normalize_company)
    df["award_amount_num"] = pd.to_numeric(df.get(award_col), errors="coerce").fillna(0)
    if desc_col:
        df["trades_list"] = df[desc_col].astype(str).map(classify)
    else:
        df["trades_list"] = [[] for _ in range(len(df))]

    # Make sure expected location columns exist so .agg won't blow up
    for c in ("address", "city", "state", "zipcode"):
        if c not in df.columns:
            df[c] = ""

    agg = (
        df.groupby("contractor_name_norm", dropna=False)
        .agg(
            contractor_name_norm=("contractor_name_norm", "first"),
            contractor_name=("contractor_name", "first"),
            jobs_count=("contractor_name", "count"),
            total_reported_cost=("award_amount_num", "sum"),
            address=("address", "first"),
            city=("city", "first"),
            state=("state", "first"),
            zipcode=("zipcode", "first"),
            trades=("trades_list", lambda L: sorted({t for sub in L for t in sub})),
        )
        .reset_index(drop=True)
    )
    agg["trades_str"] = agg["trades"].map(lambda L: ", ".join(L))
    agg["source"] = "Chicago Contracts"
    agg["phone"] = ""
    return agg.sort_values(["jobs_count", "total_reported_cost"], ascending=False)


def search(start_date: str = "2020-01-01", limit: int = 20000) -> pd.DataFrame:
    return aggregate(fetch(limit=limit, start_date=start_date))
