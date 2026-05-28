"""Shared helpers: caching, normalization, retry."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TTL = 60 * 60 * 12  # 12 hours


def _cache_key(url: str, params: dict | None) -> Path:
    raw = url + json.dumps(params or {}, sort_keys=True)
    h = hashlib.sha1(raw.encode()).hexdigest()
    return CACHE_DIR / f"{h}.json"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def http_get_json(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    ttl: int = DEFAULT_TTL,
) -> Any:
    """GET JSON with on-disk caching + retries."""
    key = _cache_key(url, params)
    if key.exists() and (time.time() - key.stat().st_mtime) < ttl:
        try:
            return json.loads(key.read_text())
        except Exception:
            key.unlink(missing_ok=True)

    resp = requests.get(url, params=params, headers=headers or {}, timeout=45)
    resp.raise_for_status()
    data = resp.json()
    key.write_text(json.dumps(data))
    return data


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def http_get_text(url: str, headers: dict | None = None, ttl: int = DEFAULT_TTL) -> str:
    key = _cache_key(url, None)
    if key.exists() and (time.time() - key.stat().st_mtime) < ttl:
        return key.read_text()
    h = {"User-Agent": "Mozilla/5.0 ElysiumContractorFinder/1.0"}
    h.update(headers or {})
    resp = requests.get(url, headers=h, timeout=45)
    resp.raise_for_status()
    key.write_text(resp.text)
    return resp.text


_PHONE_RE = re.compile(r"(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+")


def extract_phones(text: str) -> list[str]:
    if not text:
        return []
    seen, out = set(), []
    for m in _PHONE_RE.findall(text):
        clean = re.sub(r"\D", "", m)
        if len(clean) == 10 and clean not in seen:
            seen.add(clean)
            out.append(f"({clean[0:3]}) {clean[3:6]}-{clean[6:]}")
    return out


def extract_emails(text: str) -> list[str]:
    if not text:
        return []
    seen, out = set(), []
    for m in _EMAIL_RE.findall(text):
        e = m.lower().strip(".,;)")
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def normalize_company(name: str | None) -> str:
    if not name:
        return ""
    s = name.upper().strip()
    s = re.sub(r"[.,]", "", s)
    for suffix in (" LLC", " INC", " CORP", " CO", " LTD", " LP", " LLP", " PC"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    s = re.sub(r"\s+", " ", s)
    return s


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()
