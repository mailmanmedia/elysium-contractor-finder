"""
Better Business Bureau search scraper.

LEGAL NOTE: BBB.org's Terms of Use prohibit automated scraping.
This module is provided for personal research; respect robots.txt and rate
limits. The app gates this behind an opt-in toggle.
"""
from __future__ import annotations

import time
import urllib.parse

import pandas as pd
from bs4 import BeautifulSoup

from .common import http_get_text, normalize_company
from .trades import keywords_for

BASE = "https://www.bbb.org/search"


def _search_page(term: str, location: str, page: int) -> str:
    params = {
        "find_country": "USA",
        "find_loc": location,
        "find_text": term,
        "page": page,
    }
    return http_get_text(f"{BASE}?{urllib.parse.urlencode(params)}", ttl=60 * 60 * 6)


def _parse(html: str, trade_label: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select("div.result-card, div.MuiPaper-root"):
        name_el = card.select_one("a.text-blue-medium, h3 a, a[href*='/profile/']")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        addr_el = card.select_one("address, .text-size-5")
        addr = addr_el.get_text(" ", strip=True) if addr_el else ""

        out.append({
            "contractor_name": name,
            "contractor_name_norm": normalize_company(name),
            "phone": "",
            "address": addr,
            "city": "",
            "state": "",
            "zipcode": "",
            "website": "",
            "trades": [trade_label],
            "trades_str": trade_label,
            "source": "BBB",
            "jobs_count": 0,
            "total_reported_cost": 0.0,
        })
    return out


def search(trades: list[str], location: str = "Chicago, IL",
           max_pages: int = 2, delay_sec: float = 1.5) -> pd.DataFrame:
    rows = []
    for trade in trades:
        kws = keywords_for(trade)
        term = (kws[0] if kws else trade) + " contractor"
        for page in range(1, max_pages + 1):
            try:
                html = _search_page(term, location, page)
            except Exception as e:  # noqa: BLE001
                print(f"[bbb] {trade} p{page}: {e}")
                break
            rows.extend(_parse(html, trade))
            time.sleep(delay_sec)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["contractor_name_norm"])
