"""
Elysium Contractor Finder - Streamlit UI.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from sources import (
    bbb,
    chicago_contracts,
    chicago_permits,
    enrichment,
    idfpr_licenses,
    search_engines,
    yellow_pages,
)
from sources.merge import merge_sources
from sources.trades import all_trade_labels

load_dotenv()

st.set_page_config(
    page_title="Elysium Contractor Finder",
    page_icon="🏗️",
    layout="wide",
)

# ---------- Sidebar: filters ----------
st.sidebar.title("🏗️ Elysium Contractor Finder")
st.sidebar.caption("Cast a wide net across public + scraped sources.")

with st.sidebar:
    st.header("Search")
    keyword = st.text_input("Keyword (company / project / address)", "")

    st.header("Trades")
    selected_trades = st.multiselect(
        "Filter by trade",
        options=all_trade_labels(),
        default=[],
        help="Leave empty to include all trades.",
    )

    st.header("Location")
    city_input = st.text_input("City for scraped sources", "Chicago, IL")
    zip_input = st.text_input(
        "ZIP codes (comma-separated, optional)",
        "",
        help="Filters Chicago permits to these contractor zips.",
    )

    st.header("Date range (permits/contracts)")
    default_since = date.today() - timedelta(days=365 * 2)
    issued_since = st.date_input("Issued since", value=default_since)

    st.header("Cost / activity filters")
    min_jobs = st.number_input("Min. jobs", min_value=0, value=0, step=1)
    min_cost = st.number_input("Min. total reported cost ($)", min_value=0, value=0, step=10000)

    st.header("Sources")
    use_permits = st.checkbox("Chicago Building Permits", value=True)
    use_contracts = st.checkbox("Chicago Contract Awards", value=True)
    use_idfpr = st.checkbox("IDFPR licensed contractors (local files)", value=True)
    use_yp = st.checkbox("Yellow Pages (scrape — opt-in)", value=False)
    use_bbb = st.checkbox("BBB (scrape — opt-in)", value=False)
    use_search = st.checkbox("DuckDuckGo search results (scrape — opt-in)", value=False)
    follow_search_links = st.checkbox(
        "Follow search result pages for phone/email extraction",
        value=False,
        help="If enabled, the scraper will fetch result URLs and look for contact details on the landing page.",
    )
    st.caption(
        "Chicago permit and contract datasets typically do not include contractor "
        "phone numbers or emails. Use optional scrapers, search engine results, or paid enrichment to "
        "populate contact details."
    )

    st.header("Enrichment (paid APIs)")
    use_google = st.checkbox("Google Places (phone/website/rating)", value=False)
    use_hunter = st.checkbox("Hunter.io emails", value=False)
    use_apollo = st.checkbox("Apollo.io org lookup", value=False)
    max_enrich = st.slider("Max contractors to enrich", 0, 200, 25)

    st.header("Contact priority")
    require_contact = st.checkbox(
        "Require phone or email",
        value=False,
        help="Only show contractors with at least one contact detail.",
    )
    sort_by_contact = st.checkbox(
        "Sort by contact completeness",
        value=True,
        help="Place contractors with phone/email at the top.",
    )
    if require_contact and not (use_yp or use_bbb or use_google or use_hunter or use_apollo):
        st.warning(
            "Contact details are likely unavailable unless scraping or enrichment is enabled. "
            "Turn on Yellow Pages, BBB, or paid APIs for better coverage."
        )

    st.header("Contact-first sourcing")
    contact_first_mode = st.checkbox(
        "Contact-priority sourcing (enable all contact sources)",
        value=False,
        help="If selected, the search will prioritize reachability by running scrapers and enrichment sources for phone/email details.",
    )
    if contact_first_mode:
        st.info(
            "Contact-first sourcing will also enable Yellow Pages, BBB, DuckDuckGo search results, "
            "and any configured paid APIs. This may take longer but is the best way to surface phone/email contacts."
        )

    st.header("Limits")
    permit_limit = st.number_input("Max permits to pull", 1000, 50000, 20000, step=1000)
    scrape_pages = st.number_input("Scrape pages per trade", 1, 10, 2)

    run = st.button("🔎 Run search", type="primary", use_container_width=True)


# ---------- Main: results ----------
st.title("Contractor Search Results")
st.caption(
    "Public sources (Chicago Data Portal, IDFPR) are recommended. "
    "Scraped sources are gated behind opt-in toggles; review the relevant ToS before scaling."
)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def _run_permits(since_iso: str, limit: int, zips: list[str]) -> pd.DataFrame:
    return chicago_permits.search(issued_since=since_iso, limit=int(limit), zipcodes=zips or None)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def _run_contracts(since_iso: str, limit: int) -> pd.DataFrame:
    return chicago_contracts.search(start_date=since_iso, limit=int(limit))


@st.cache_data(show_spinner=False, ttl=60 * 60)
def _run_idfpr() -> pd.DataFrame:
    return idfpr_licenses.load_local()


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def _run_yp(trades: tuple[str, ...], location: str, pages: int) -> pd.DataFrame:
    return yellow_pages.search(list(trades), location=location, max_pages=int(pages))


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def _run_bbb(trades: tuple[str, ...], location: str, pages: int) -> pd.DataFrame:
    return bbb.search(list(trades), location=location, max_pages=int(pages))


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def _run_search(trades: tuple[str, ...], location: str, pages: int, follow: bool) -> pd.DataFrame:
    return search_engines.search(list(trades), max_pages=int(pages), follow_pages=follow)


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if keyword:
        kw = keyword.lower()
        mask = (
            out["contractor_name"].astype(str).str.lower().str.contains(kw, na=False)
            | out["address"].astype(str).str.lower().str.contains(kw, na=False)
            | out["trades_str"].astype(str).str.lower().str.contains(kw, na=False)
        )
        out = out[mask]
    if selected_trades:
        sel = set(selected_trades)
        out = out[out["trades"].map(lambda L: bool(set(L) & sel) if isinstance(L, list) else False)]
    if min_jobs:
        out = out[pd.to_numeric(out["jobs_count"], errors="coerce").fillna(0) >= min_jobs]
    if min_cost:
        out = out[pd.to_numeric(out["total_reported_cost"], errors="coerce").fillna(0) >= min_cost]
    return out


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        export = df.copy()
        if "trades" in export.columns:
            export["trades"] = export["trades"].map(lambda L: ", ".join(L) if isinstance(L, list) else L)
        export.to_excel(writer, index=False, sheet_name="Contractors")
        ws = writer.sheets["Contractors"]
        for i, col in enumerate(export.columns):
            width = min(60, max(12, int(export[col].astype(str).str.len().quantile(0.9) or 12) + 2))
            ws.set_column(i, i, width)
    return buf.getvalue()


def _normalize_contact_fields(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "phone" in out.columns:
        out["phone"] = out["phone"].astype(str).fillna("")
        if "google_phone" in out.columns:
            mask = out["phone"].str.strip() == ""
            out.loc[mask, "phone"] = out.loc[mask, "google_phone"].astype(str).fillna("")
        if "apollo_phone" in out.columns:
            mask = out["phone"].str.strip() == ""
            out.loc[mask, "phone"] = out.loc[mask, "apollo_phone"].astype(str).fillna("")
    if "email" in out.columns:
        out["email"] = out["email"].astype(str).fillna("")
        if "hunter_email_1" in out.columns:
            mask = out["email"].str.strip() == ""
            out.loc[mask, "email"] = out.loc[mask, "hunter_email_1"].astype(str).fillna("")
        if "hunter_email_2" in out.columns:
            mask = out["email"].str.strip() == ""
            out.loc[mask, "email"] = out.loc[mask, "hunter_email_2"].astype(str).fillna("")
    if "website" in out.columns and "google_website" in out.columns:
        out["website"] = out["website"].astype(str).fillna("")
        mask = out["website"].str.strip() == ""
        out.loc[mask, "website"] = out.loc[mask, "google_website"].astype(str).fillna("")
    return out


def _ensure_contact_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["phone", "email"]:
        if col not in out.columns:
            out[col] = ""
    return out


def _contact_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = _ensure_contact_columns(df)
    out["has_phone"] = out["phone"].astype(str).str.strip().ne("")
    out["has_email"] = out["email"].astype(str).str.strip().ne("")
    out["contact_score"] = out["has_phone"].astype(int) + out["has_email"].astype(int)
    return out


def _apply_contact_source(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "contact_source" not in out.columns:
        out["contact_source"] = ""
    for idx, row in out.iterrows():
        sources = set()
        if isinstance(row.get("source"), str) and row["source"].strip():
            sources.update([s.strip() for s in row["source"].split(",") if s.strip()])
        if str(row.get("google_phone", "")).strip() or str(row.get("google_website", "")).strip():
            sources.add("Google Places")
        if str(row.get("hunter_email_1", "")).strip() or str(row.get("hunter_email_2", "")).strip():
            sources.add("Hunter.io")
        if str(row.get("apollo_phone", "")).strip() or str(row.get("apollo_domain", "")).strip():
            sources.add("Apollo.io")
        out.at[idx, "contact_source"] = ", ".join(sorted(sources))
    return out


if "results" not in st.session_state:
    st.session_state["results"] = pd.DataFrame()

if run:
    if contact_first_mode:
        use_yp = True
        use_bbb = True
        use_search = True
        use_google = True
        use_hunter = True
        use_apollo = True
    frames: list[pd.DataFrame] = []
    progress = st.progress(0.0, text="Starting…")
    steps = sum([use_permits, use_contracts, use_idfpr, use_yp, use_bbb, use_search]) or 1
    step = 0

    if use_permits:
        progress.progress(step / steps, text="Pulling Chicago building permits…")
        zips = [z.strip() for z in zip_input.split(",") if z.strip()]
        try:
            frames.append(_run_permits(issued_since.isoformat(), permit_limit, zips))
        except Exception as e:
            st.warning(f"Permits source failed: {e}")
        step += 1

    if use_contracts:
        progress.progress(step / steps, text="Pulling Chicago contract awards…")
        try:
            frames.append(_run_contracts(issued_since.isoformat(), permit_limit))
        except Exception as e:
            st.warning(f"Contracts source failed: {e}")
        step += 1

    if use_idfpr:
        progress.progress(step / steps, text="Loading IDFPR rosters…")
        try:
            frames.append(_run_idfpr())
        except Exception as e:
            st.warning(f"IDFPR loader failed: {e}")
        step += 1

    if use_yp:
        progress.progress(step / steps, text="Scraping Yellow Pages…")
        trades_for_scrape = selected_trades or all_trade_labels()[:6]
        try:
            frames.append(_run_yp(tuple(trades_for_scrape), city_input, scrape_pages))
        except Exception as e:
            st.warning(f"Yellow Pages failed: {e}")
        step += 1

    if use_bbb:
        progress.progress(step / steps, text="Scraping BBB…")
        trades_for_scrape = selected_trades or all_trade_labels()[:6]
        try:
            frames.append(_run_bbb(tuple(trades_for_scrape), city_input, scrape_pages))
        except Exception as e:
            st.warning(f"BBB failed: {e}")
        step += 1

    if use_search:
        progress.progress(step / steps, text="Searching DuckDuckGo…")
        trades_for_scrape = selected_trades or all_trade_labels()[:6]
        try:
            frames.append(_run_search(tuple(trades_for_scrape), city_input, scrape_pages, follow_search_links))
        except Exception as e:
            st.warning(f"Search engine scraping failed: {e}")
        step += 1

    progress.progress(1.0, text="Merging sources…")
    merged = merge_sources(frames)
    st.session_state["results"] = merged
    progress.empty()

# Enrichment (runs against current results, with user gating)
results: pd.DataFrame = st.session_state["results"]
results = _apply_filters(results)

if not results.empty and (use_google or use_hunter or use_apollo) and max_enrich > 0:
    with st.spinner(f"Enriching top {min(max_enrich, len(results))} contractors…"):
        head = results.head(max_enrich).copy()
        new_cols: dict[str, list] = {}
        for idx, row in head.iterrows():
            company = row["contractor_name"]
            updates = {}
            if use_google:
                updates.update(enrichment.google_places_lookup(company, row.get("city") or "Chicago"))
            domain = enrichment.domain_from_url(updates.get("google_website") or row.get("website") or "")
            if use_hunter and domain:
                emails = enrichment.hunter_emails(domain)
                if emails:
                    updates["hunter_email_1"] = emails[0].get("email", "")
                    updates["hunter_contact_1"] = emails[0].get("name", "")
                    updates["hunter_position_1"] = emails[0].get("position", "")
                    if len(emails) > 1:
                        updates["hunter_email_2"] = emails[1].get("email", "")
                        updates["hunter_contact_2"] = emails[1].get("name", "")
            if use_apollo:
                updates.update(enrichment.apollo_org_lookup(company))
            for k, v in updates.items():
                new_cols.setdefault(k, [None] * len(head))
                new_cols[k][list(head.index).index(idx)] = v
        for k, vals in new_cols.items():
            head[k] = vals
        # write back into results
        results = pd.concat([head, results.iloc[max_enrich:]], ignore_index=False)

results = _normalize_contact_fields(results)
results = _contact_metrics(results)
results = _apply_contact_source(results)
if require_contact:
    results = results[(results["has_phone"]) | (results["has_email"])].copy()
    if results.empty:
        st.warning(
            "No contractors with phone/email were found. Enable more contact sources or relax the filters."
        )
if sort_by_contact and not results.empty:
    results = results.sort_values(
        ["contact_score", "jobs_count", "total_reported_cost"],
        ascending=[False, False, False],
        na_position="last",
    )

# ---------- KPIs ----------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Contractors found", f"{len(results):,}")
c2.metric(
    "Total reported $",
    f"${pd.to_numeric(results.get('total_reported_cost'), errors='coerce').fillna(0).sum():,.0f}"
    if not results.empty else "$0",
)
c3.metric(
    "Avg jobs / contractor",
    f"{pd.to_numeric(results.get('jobs_count'), errors='coerce').fillna(0).mean():.1f}"
    if not results.empty else "0",
)
c4.metric("Sources merged", results["source"].nunique() if "source" in results.columns and not results.empty else 0)
contact_rows = int(results["contact_score"].gt(0).sum()) if not results.empty else 0
c5.metric("With phone/email", f"{contact_rows:,}")

# ---------- Table ----------
if results.empty:
    st.info("No results yet — set filters in the sidebar and click **Run search**.")
else:
    show_cols = [
        c for c in [
            "contractor_name", "trades_str", "phone", "email", "has_phone", "has_email", "contact_score", "contact_source", "website",
            "address", "city", "state", "zipcode",
            "jobs_count", "total_reported_cost", "last_seen",
            "license_number", "license_status", "expiration_date",
            "google_phone", "google_website", "google_rating", "google_reviews",
            "hunter_email_1", "hunter_contact_1", "hunter_position_1",
            "hunter_email_2", "hunter_contact_2",
            "apollo_domain", "apollo_phone", "apollo_linkedin", "apollo_industry", "apollo_employees",
            "source",
        ] if c in results.columns
    ]
    st.dataframe(
        results[show_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "total_reported_cost": st.column_config.NumberColumn(format="$%.0f"),
            "google_rating": st.column_config.NumberColumn(format="%.1f"),
        },
    )

    # ---------- Export ----------
    exports_dir = Path(__file__).parent / "exports"
    exports_dir.mkdir(exist_ok=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.download_button(
            "⬇️ Download Excel",
            data=_to_excel_bytes(results[show_cols]),
            file_name=f"contractors_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col_b:
        csv = results[show_cols].copy()
        if "trades" in csv.columns:
            csv["trades"] = csv["trades"].map(lambda L: ", ".join(L) if isinstance(L, list) else L)
        st.download_button(
            "⬇️ Download CSV",
            data=csv.to_csv(index=False).encode("utf-8"),
            file_name=f"contractors_{date.today().isoformat()}.csv",
            mime="text/csv",
            use_container_width=True,
        )

with st.expander("ℹ️ Notes & legal"):
    st.markdown(
        """
- **Public sources** (Chicago Data Portal, IDFPR) are the recommended primary
  data and require no API key (a free Socrata app token raises rate limits).
- **"Reported cost"** on permits and **"award amount"** on contracts are the
  closest legally-available proxy for what contractors were paid.
- **Yellow Pages / BBB scraping** is gated behind opt-in toggles. Both sites'
  Terms of Use prohibit automated scraping; review their ToS and robots.txt
  and throttle politely before using.
- **Paid enrichment** (Google Places, Hunter.io, Apollo.io) requires API keys
  in a `.env` file. They run only for the first *N* rows shown above to
  control cost.
        """
    )
