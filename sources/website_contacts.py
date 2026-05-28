"""Website contact crawler utilities.

Extracts phone/email contact details from company websites and contact pages.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .common import extract_emails, extract_phones

SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

CONTACT_LINK_TOKENS = ["contact", "about", "team", "support", "help", "call", "email"]


def _get_session(session: requests.Session | None = None) -> requests.Session:
    if session is None:
        session = requests.Session()
    session.headers.update(SEARCH_HEADERS)
    return session


def _fetch_url(url: str, session: requests.Session | None = None) -> str:
    session = _get_session(session)
    try:
        resp = session.get(url, timeout=45)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


def _normalize_link(base: str, href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    return urljoin(base, href)


def _same_domain(url: str, candidate: str) -> bool:
    try:
        base = urlparse(url).netloc.lower().lstrip("www.")
        target = urlparse(candidate).netloc.lower().lstrip("www.")
        return base == target or target.endswith("." + base)
    except Exception:
        return False


def _walk_json(obj: Any) -> list[Any]:
    if isinstance(obj, dict):
        values = []
        for value in obj.values():
            values.extend(_walk_json(value))
        return values
    if isinstance(obj, list):
        values = []
        for item in obj:
            values.extend(_walk_json(item))
        return values
    return [obj]


def _extract_json_ld_contacts(html: str) -> tuple[list[str], list[str]]:
    phones: list[str] = []
    emails: list[str] = []
    soup = BeautifulSoup(html, "lxml")
    for script in soup.select("script[type='application/ld+json']"):
        try:
            payload = json.loads(script.string or "")
        except Exception:
            continue
        for item in _walk_json(payload):
            if isinstance(item, dict):
                for key, value in item.items():
                    normalized = str(key).lower()
                    if "phone" in normalized or "telephone" in normalized:
                        phones.extend(extract_phones(str(value)))
                    if "email" in normalized:
                        emails.extend(extract_emails(str(value)))
            elif isinstance(item, str):
                emails.extend(extract_emails(item))
                phones.extend(extract_phones(item))
    return phones, emails


def _extract_contact_links(html: str) -> tuple[list[str], list[str]]:
    phones = extract_phones(html)
    emails = extract_emails(html)
    soup = BeautifulSoup(html, "lxml")
    for link in soup.select("a[href]"):
        href = link["href"].strip()
        if href.lower().startswith("tel:"):
            phones.extend(extract_phones(href))
            continue
        if href.lower().startswith("mailto:"):
            email = href.split(":", 1)[1].split("?")[0].strip()
            if email:
                emails.append(email)
            continue
        # Expose object text near contact links too
        if any(token in href.lower() for token in CONTACT_LINK_TOKENS):
            node_text = link.get_text(" ", strip=True)
            phones.extend(extract_phones(node_text))
            emails.extend(extract_emails(node_text))
    json_phones, json_emails = _extract_json_ld_contacts(html)
    phones.extend(json_phones)
    emails.extend(json_emails)
    return phones, emails


def _find_contact_page(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    candidates: list[tuple[int, str]] = []
    for link in soup.select("a[href]"):
        href = link["href"].strip()
        if not href:
            continue
        normalized = href.lower()
        text = link.get_text(" ", strip=True).lower()
        if any(token in normalized for token in CONTACT_LINK_TOKENS) or any(token in text for token in CONTACT_LINK_TOKENS):
            candidate = _normalize_link(base_url, href)
            if _same_domain(base_url, candidate):
                score = sum(token in normalized or token in text for token in CONTACT_LINK_TOKENS)
                candidates.append((score, candidate))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def crawl_website_contacts(url: str, session: requests.Session | None = None) -> dict[str, Any]:
    if not url:
        return {"phone": "", "email": "", "contact_page": ""}
    html = _fetch_url(url, session)
    phones, emails = _extract_contact_links(html)
    contact_page = ""
    if not phones or not emails:
        contact_page = _find_contact_page(html, url) or ""
        if contact_page:
            contact_html = _fetch_url(contact_page, session)
            if contact_html:
                p, e = _extract_contact_links(contact_html)
                phones.extend(p)
                emails.extend(e)
    phone = phones[0] if phones else ""
    email = emails[0] if emails else ""
    return {
        "phone": phone,
        "email": email,
        "contact_page": contact_page,
    }
