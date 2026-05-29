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

CONTACT_LINK_TOKENS = ["contact", "about", "team", "support", "help", "call", "email", "sales", "customer", "request", "quote", "location", "office"]
MAX_CONTACT_PAGE_CANDIDATES = 5


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


def _fetch_script_text(url: str, session: requests.Session | None = None) -> str:
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


JUNK_EMAIL_DOMAINS = {
    "example.com",
    "test.com",
    "localhost",
    "local",
    "greensock.com",
    "slick-carousel.com",
    "jquery.com",
    "github.com",
    "cdnjs.com",
    "npmjs.com",
    "google.com",
    "googleapis.com",
}

JUNK_EMAIL_LOCALS = {
    "example",
    "test",
    "demo",
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "webmaster",
    "postmaster",
}


def _is_valid_email(email: str) -> bool:
    normalized = email.lower().strip()
    if "@" not in normalized:
        return False
    local, domain = normalized.split("@", 1)
    local = local.strip()
    domain = domain.strip().strip(".")
    if not local or not domain:
        return False
    if any(normalized.endswith(f"@{junk}") for junk in JUNK_EMAIL_DOMAINS):
        return False
    if local in JUNK_EMAIL_LOCALS:
        return False
    if local.startswith("test") or local.startswith("demo") or local.startswith("example"):
        return False
    return True


def _filter_emails(emails: list[str]) -> list[str]:
    seen = set()
    filtered: list[str] = []
    for email in emails:
        candidate = email.lower().strip()
        if not candidate or candidate in seen:
            continue
        if not _is_valid_email(candidate):
            continue
        seen.add(candidate)
        filtered.append(candidate)
    return filtered


def _decode_cfemails(html: str) -> list[str]:
    emails: list[str] = []
    for match in re.finditer(r'data-cfemail="([0-9a-fA-F]+)"', html):
        encoded = match.group(1)
        try:
            data = bytes.fromhex(encoded)
            if not data:
                continue
            key = data[0]
            decoded = "".join(chr(b ^ key) for b in data[1:])
            emails.extend(extract_emails(decoded))
        except ValueError:
            continue
    return _filter_emails(emails)


def _extract_contact_links(html: str, base_url: str = "", session: requests.Session | None = None) -> tuple[list[str], list[str]]:
    phones = extract_phones(html)
    emails = extract_emails(html)
    emails.extend(_decode_cfemails(html))
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
        if any(token in href.lower() for token in CONTACT_LINK_TOKENS):
            node_text = link.get_text(" ", strip=True)
            phones.extend(extract_phones(node_text))
            emails.extend(extract_emails(node_text))
    # Also examine script content and external script assets for explicit contact details.
    for script in soup.select("script"):
        if script.has_attr("src"):
            script_url = _normalize_link(base_url, script["src"])
            if _same_domain(base_url, script_url):
                script_text = _fetch_script_text(script_url, session=session)
                phones.extend(extract_phones(script_text))
                emails.extend(extract_emails(script_text))
                emails.extend(_decode_cfemails(script_text))
        else:
            script_text = script.string or script.get_text()
            phones.extend(extract_phones(script_text))
            emails.extend(extract_emails(script_text))
            emails.extend(_decode_cfemails(script_text))
    json_phones, json_emails = _extract_json_ld_contacts(html)
    phones.extend(json_phones)
    emails.extend(json_emails)
    return phones, _filter_emails(emails)


def _find_contact_pages(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    candidates: list[tuple[int, str]] = []
    for link in soup.select("a[href]"):
        href = link["href"].strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "#")):
            continue
        normalized = href.lower()
        text = link.get_text(" ", strip=True).lower()
        if any(token in normalized for token in CONTACT_LINK_TOKENS) or any(token in text for token in CONTACT_LINK_TOKENS):
            candidate = _normalize_link(base_url, href)
            if _same_domain(base_url, candidate):
                score = sum(token in normalized or token in text for token in CONTACT_LINK_TOKENS)
                candidates.append((score, candidate))
    if not candidates:
        return []
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    seen = set()
    urls: list[str] = []
    for _, candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)
        if len(urls) >= MAX_CONTACT_PAGE_CANDIDATES:
            break
    return urls


def crawl_website_contacts(url: str, session: requests.Session | None = None) -> dict[str, Any]:
    if not url:
        return {"phone": "", "email": "", "contact_page": ""}
    html = _fetch_url(url, session)
    phones, emails = _extract_contact_links(html, base_url=url, session=session)
    contact_pages = []
    candidates = _find_contact_pages(html, url)
    for candidate in candidates:
        contact_pages.append(candidate)
        if candidate == url:
            continue
        candidate_html = _fetch_url(candidate, session)
        if not candidate_html:
            continue
        p, e = _extract_contact_links(candidate_html, base_url=candidate, session=session)
        phones.extend(p)
        emails.extend(e)
        # Also follow nested contact pages from the candidate page if no email found yet.
        if not emails:
            nested = _find_contact_pages(candidate_html, candidate)
            for nested_url in nested:
                if nested_url in contact_pages:
                    continue
                contact_pages.append(nested_url)
                nested_html = _fetch_url(nested_url, session)
                if nested_html:
                    p2, e2 = _extract_contact_links(nested_html, base_url=nested_url, session=session)
                    phones.extend(p2)
                    emails.extend(e2)
    phone = phones[0] if phones else ""
    email = emails[0] if emails else ""
    return {
        "phone": phone,
        "email": email,
        "contact_page": contact_pages[0] if contact_pages else "",
        "contact_pages": contact_pages,
    }
