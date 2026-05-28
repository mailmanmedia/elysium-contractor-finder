"""
Yellow Pages search scraper.

LEGAL NOTE: YellowPages.com's Terms of Use prohibit automated scraping.
This module is provided for personal research; respect robots.txt, throttle
requests, and review YP's ToS before using at scale. The app gates this
behind an opt-in toggle in the UI.
"""
from __future__ import annotations

import time
import urllib.parse

import pandas as pd
from bs4 import BeautifulSoup

from .common import extract_phones, http_get_text, normalize_company
from .trades import keywords_for

BASE = "https://www.yellowpages.com/search"


def _search_page(term: str, location: str, page: int) -> str:
    params = {
        "search_terms": term,
        "geo_location_terms": location,
        "page": page,
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    return http_get_text(url, ttl=60 * 60 * 6)


def _parse(html: str, trade_label: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select("div.result, div.v-card"):
        name_el = card.select_one("a.business-name, h2.n a")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)

        phone_el = card.select_one("div.phones, .phones.phone.primary")
        phone = phone_el.get_text(strip=True) if phone_el else ""
        phones = extract_phones(phone)

        addr_el = card.select_one("p.adr, .street-address")
        addr = addr_el.get_text(" ", strip=True) if addr_el else ""

        locality_el = card.select_one(".locality")
        locality = locality_el.get_text(" ", strip=True) if locality_el else ""

        website = ""
        site_el = card.select_one("a.track-visit-website, a.website")
        if site_el and site_el.has_attr("href"):
            website = site_el["href"]

        out.append({
            "contractor_name": name,
            "contractor_name_norm": normalize_company(name),
            "phone": phones[0] if phones else "",
            "address": addr,
            "city": locality,
            "state": "",
            "zipcode": "",
            "website": website,
            "trades": [trade_label],
            "trades_str": trade_label,
            "source": "Yellow Pages",
            "jobs_count": 0,
            "total_reported_cost": 0.0,
        })
    return out


def search(
    trades: list[str],
    location: str = "Chicago, IL",
    max_pages: int = 2,
    delay_sec: float = 1.5,
) -> pd.DataFrame:
    rows: list[dict] = []
    for trade in trades:
        # use the first keyword as the YP search term, fall back to label
        kws = keywords_for(trade)
        term = (kws[0] if kws else trade).strip() + " contractor"
        for page in range(1, max_pages + 1):
            try:
                html = _search_page(term, location, page)
            except Exception as e:  # noqa: BLE001
                print(f"[yellow_pages] {trade} p{page}: {e}")
                break
            rows.extend(_parse(html, trade))
            time.sleep(delay_sec)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates(subset=["contractor_name_norm", "phone"])
    return df
