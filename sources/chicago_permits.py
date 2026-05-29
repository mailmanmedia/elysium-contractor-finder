"""
Chicago Building Permits (Socrata Open Data API).

Dataset: https://data.cityofchicago.org/Buildings/Building-Permits/ydr8-5enu
Endpoint: https://data.cityofchicago.org/resource/ydr8-5enu.json

The dataset stores up to 11 contact slots per permit
(contact_1_type, contact_1_name, contact_1_city, contact_1_state,
 contact_1_zipcode). We keep only rows where contact_N_type identifies a
contractor (e.g. "GENERAL CONTRACTOR", "ELECTRICAL CONTRACTOR",
"CONTRACTOR-PLUMBER/PLUMBING", "MASON CONTRACTOR", etc.) and roll those up
per contractor.

Note: the current dataset no longer publishes contractor phone numbers.
Use the enrichment module (Google Places / Apollo / Hunter) to add phones
and emails.
"""
from __future__ import annotations

import pandas as pd

from .common import env, http_get_json, normalize_company
from .trades import classify

ENDPOINT = "https://data.cityofchicago.org/resource/ydr8-5enu.json"
MAX_PER_PAGE = 50000

CONTACT_SLOTS = list(range(1, 12))

# A contact slot counts as a "contractor" if the type contains any of these
# substrings (case-insensitive). We deliberately exclude OWNER-AS-* roles
# and design professionals.
CONTRACTOR_TYPE_HINTS = (
    "CONTRACTOR",
    "MASON",
    "ROOFER",
)
EXCLUDE_TYPE_HINTS = (
    "OWNER",
    "ARCHITECT",
    "ENGINEER",
    "DESIGN PROFESSIONAL",
    "TENANT",
    "EXPEDITER",
    "EXPEDITOR",
    "APPLICANT",
)


def _headers() -> dict:
    tok = env("SOCRATA_APP_TOKEN")
    return {"X-App-Token": tok} if tok else {}


def _is_contractor_type(t) -> bool:
    if not isinstance(t, str):
        return False
    tu = t.upper()
    if any(x in tu for x in EXCLUDE_TYPE_HINTS):
        return False
    return any(x in tu for x in CONTRACTOR_TYPE_HINTS)


def fetch_permits(
    issued_since: str | None = None,
    limit: int = 20000,
    zipcodes: list[str] | None = None,
    permit_types: list[str] | None = None,
) -> pd.DataFrame:
    """Returns the raw permits dataframe (one row per permit)."""
    where_clauses = []
    if issued_since:
        where_clauses.append(f"issue_date >= '{issued_since}T00:00:00.000'")
    if permit_types:
        types = ",".join(f"'{t}'" for t in permit_types)
        where_clauses.append(f"permit_type in ({types})")

    params: dict[str, str | int] = {
        "$limit": min(limit, MAX_PER_PAGE),
        "$order": "issue_date DESC",
    }
    if where_clauses:
        params["$where"] = " AND ".join(where_clauses)

    rows = http_get_json(ENDPOINT, params=params, headers=_headers())
    df = pd.DataFrame(rows)

    if zipcodes and not df.empty:
        zs = {z.strip() for z in zipcodes if z.strip()}
        zip_cols = [c for c in df.columns if c.endswith("_zipcode")]
        if zip_cols and zs:
            mask = pd.Series(False, index=df.index)
            for c in zip_cols:
                mask = mask | df[c].astype(str).isin(zs)
            df = df[mask]
    return df


def explode_contractors(permits: pd.DataFrame) -> pd.DataFrame:
    """Flatten contact slots into one row per (permit, contractor)."""
    if permits.empty:
        return pd.DataFrame()

    base_cols = [
        c for c in [
            "id", "permit_", "permit_type", "issue_date",
            "reported_cost", "total_fee",
            "street_name", "street_number", "work_description", "work_type",
            "community_area", "ward", "latitude", "longitude",
        ] if c in permits.columns
    ]

    long_rows = []
    for slot in CONTACT_SLOTS:
        type_col = f"contact_{slot}_type"
        name_col = f"contact_{slot}_name"
        if type_col not in permits.columns or name_col not in permits.columns:
            continue

        slot_cols = [c for c in permits.columns if c.startswith(f"contact_{slot}_")]
        sub = permits[base_cols + slot_cols].copy()
        sub = sub[sub[type_col].map(_is_contractor_type)]
        if sub.empty:
            continue

        rename = {
            name_col: "contractor_name",
            type_col: "contractor_type",
            f"contact_{slot}_city": "contractor_city",
            f"contact_{slot}_state": "contractor_state",
            f"contact_{slot}_zipcode": "contractor_zipcode",
        }
        rename = {k: v for k, v in rename.items() if k in sub.columns}
        sub = sub.rename(columns=rename)

        drop_cols = [c for c in sub.columns if c.startswith("contact_")]
        sub = sub.drop(columns=drop_cols, errors="ignore")

        sub = sub[sub["contractor_name"].notna() & (sub["contractor_name"].astype(str).str.strip() != "")]
        if not sub.empty:
            long_rows.append(sub)

    if not long_rows:
        return pd.DataFrame()

    df = pd.concat(long_rows, ignore_index=True)
    df["source"] = "Chicago Building Permits"
    df["contractor_name_norm"] = df["contractor_name"].astype(str).map(normalize_company)
    return df


def aggregate_by_contractor(long_df: pd.DataFrame) -> pd.DataFrame:
    """One row per contractor with jobs_count, total_reported_cost, trades, etc."""
    if long_df.empty:
        return pd.DataFrame()

    df = long_df.copy()
    df["reported_cost"] = pd.to_numeric(df.get("reported_cost"), errors="coerce").fillna(0)
    df["issue_date"] = pd.to_datetime(df.get("issue_date"), errors="coerce")

    def _row_trades(r):
        blob = " ".join(
            str(r.get(c, "") or "")
            for c in ("work_description", "work_type", "contractor_type", "permit_type")
        )
        return classify(blob)

    df["trades"] = df.apply(_row_trades, axis=1)

    id_col = "id" if "id" in df.columns else "contractor_name"

    agg = (
        df.groupby("contractor_name_norm", dropna=False)
        .agg(
            contractor_name_norm=("contractor_name_norm", "first"),
            contractor_name=("contractor_name", "first"),
            jobs_count=(id_col, "nunique"),
            total_reported_cost=("reported_cost", "sum"),
            last_seen=("issue_date", "max"),
            city=("contractor_city", lambda s: next((x for x in s if isinstance(x, str) and x.strip()), "")),
            state=("contractor_state", lambda s: next((x for x in s if isinstance(x, str) and x.strip()), "")),
            zipcode=("contractor_zipcode", lambda s: next((x for x in s if isinstance(x, str) and x.strip()), "")),
            latitude=("latitude", lambda s: next((x for x in s if x is not None and str(x).strip()), "")),
            longitude=("longitude", lambda s: next((x for x in s if x is not None and str(x).strip()), "")),
            contractor_type=(
                "contractor_type",
                lambda s: ", ".join(sorted({str(x).strip() for x in s if isinstance(x, str) and x.strip()})),
            ),
            trades=("trades", lambda lists: sorted({t for sub in lists for t in sub})),
        )
        .reset_index(drop=True)
    )

    agg["source"] = "Chicago Building Permits"
    agg["trades_str"] = agg["trades"].map(lambda L: ", ".join(L))
    agg["address"] = ""
    agg["phone"] = ""
    return agg.sort_values(["jobs_count", "total_reported_cost"], ascending=False)


def search(
    issued_since: str = "2023-01-01",
    limit: int = 20000,
    zipcodes: list[str] | None = None,
) -> pd.DataFrame:
    permits = fetch_permits(issued_since=issued_since, limit=limit, zipcodes=zipcodes)
    long_df = explode_contractors(permits)
    return aggregate_by_contractor(long_df)
