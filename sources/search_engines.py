"""
DuckDuckGo search result scraper.

This source performs keyword searches for contractor trades and extracts
business names, websites, and any phone/email data it can find from snippets
or optionally by following result pages.

LEGAL NOTE: This scraper is intentionally opt-in and should be used for
research only. Review DuckDuckGo's policies and throttle requests.
"""
from __future__ import annotations

import time
import urllib.parse
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .common import extract_emails, extract_phones, http_get_text, normalize_company
from .trades import keywords_for
from .website_contacts import crawl_website_contacts

DUCK_URL = "https://html.duckduckgo.com/html"
SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 ElysiumContractorFinder/1.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://duckduckgo.com/",
}


def _duck_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(SEARCH_HEADERS)
    session.get("https://duckduckgo.com/", timeout=45)
    return session


def _normalize_url(href: str) -> str:
    if not href:
        return ""
    parsed = urllib.parse.urlparse(href)
    if parsed.path.startswith("/l/") or parsed.path.startswith("/cam/"):
        params = urllib.parse.parse_qs(parsed.query)
        target = params.get("uddg") or params.get("uddg")
        if target:
            return urllib.parse.unquote(target[0])
    return href


def _search_page(query: str, page: int) -> str:
    params = {
        "q": query,
        "s": str((page - 1) * 50),
        "kl": "us-en",
    }
    url = f"{DUCK_URL}?{urllib.parse.urlencode(params)}"
    session = _duck_session()
    resp = session.get(url, timeout=45)
    resp.raise_for_status()
    return resp.text


def _fetch_page_text(url: str, session: requests.Session | None = None) -> str:
    if session is None:
        session = requests.Session()
        session.headers.update(SEARCH_HEADERS)
    try:
        resp = session.get(url, timeout=45)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


def _parse(html: str, trade_label: str, follow_pages: bool) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    session = _duck_session() if follow_pages else None
    for card in soup.select("div.result, div.result__body, article.result"):
        link_el = card.select_one("a.result__a, a[href]")
        if not link_el or not link_el.has_attr("href"):
            continue
        url = _normalize_url(link_el["href"])
        title = link_el.get_text(strip=True)
        snippet_el = card.select_one("a.result__snippet, .result__snippet, .result__content, .result__snippet--long")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        phones = extract_phones(snippet)
        emails = extract_emails(snippet)
        if follow_pages and url:
            details = crawl_website_contacts(url, session=session)
            phones.extend(extract_phones(details.get("phone", "")))
            emails.extend(extract_emails(details.get("email", "")))
        phone = phones[0] if phones else ""
        email = emails[0] if emails else ""
        rows.append({
            "contractor_name": title or trade_label,
            "contractor_name_norm": normalize_company(title or trade_label),
            "phone": phone,
            "email": email,
            "website": url,
            "address": "",
            "city": "",
            "state": "",
            "zipcode": "",
            "trades": [trade_label],
            "trades_str": trade_label,
            "source": "DuckDuckGo Search",
            "jobs_count": 0,
            "total_reported_cost": 0.0,
        })
    return rows


def search_query(
    query: str,
    label: str,
    max_pages: int = 2,
    follow_pages: bool = False,
    delay_sec: float = 1.5,
) -> pd.DataFrame:
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        try:
            html = _search_page(query, page)
        except Exception:
            break
        rows.extend(_parse(html, label, follow_pages=follow_pages))
        time.sleep(delay_sec)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["contractor_name_norm", "website"])


def search(
    trades: list[str],
    keyword: str = "",
    location: str = "Chicago, IL",
    max_pages: int = 2,
    follow_pages: bool = False,
    delay_sec: float = 1.5,
) -> pd.DataFrame:
    rows: list[dict] = []
    for trade in trades:
        if keyword and keyword.strip():
            query = f"{keyword} {location}".strip()
        else:
            kws = keywords_for(trade)
            query = f"{(kws[0] if kws else trade).strip()} contractor {location}".strip()
        for page in range(1, max_pages + 1):
            try:
                html = _search_page(query, page)
            except Exception:
                break
            rows.extend(_parse(html, trade, follow_pages=follow_pages))
            time.sleep(delay_sec)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["contractor_name_norm", "website"])
