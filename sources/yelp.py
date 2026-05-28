"""Yelp search source adapter.

Uses DuckDuckGo site-specific search to discover Yelp listings, then follows those
URLs to extract contact details from linked business websites and listing pages.
"""
from __future__ import annotations

from .search_engines import search_query
from .trades import keywords_for

import pandas as pd


def search(
    trades: list[str],
    location: str = "Chicago, IL",
    max_pages: int = 2,
    follow_pages: bool = True,
    delay_sec: float = 1.5,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for trade in trades:
        kws = keywords_for(trade)
        query = (kws[0] if kws else trade).strip()
        query = f"site:yelp.com {query} {location}"
        df = search_query(query, label=trade, max_pages=max_pages, follow_pages=follow_pages, delay_sec=delay_sec)
        if not df.empty:
            df["source"] = "Yelp Search"
            rows.append(df)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).drop_duplicates(subset=["contractor_name_norm", "website"])
