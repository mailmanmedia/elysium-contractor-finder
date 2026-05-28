"""
Optional paid enrichment: Google Places, Hunter.io, Apollo.io.

Each function returns dict updates that can be merged onto a contractor row.
All functions short-circuit cleanly if the relevant API key is missing.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

import requests

from .common import env

# ---------- Google Places ----------

def google_places_lookup(company: str, city: str = "Chicago") -> dict[str, Any]:
    key = env("GOOGLE_PLACES_API_KEY")
    if not key or not company:
        return {}
    # 1) Find Place From Text
    find_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": f"{company} {city}",
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address",
        "key": key,
    }
    try:
        r = requests.get(find_url, params=params, timeout=20).json()
    except Exception:  # noqa: BLE001
        return {}
    candidates = r.get("candidates") or []
    if not candidates:
        return {}
    place_id = candidates[0].get("place_id")
    if not place_id:
        return {}

    # 2) Place Details for phone + website
    detail_url = "https://maps.googleapis.com/maps/api/place/details/json"
    dparams = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,international_phone_number,website,rating,user_ratings_total",
        "key": key,
    }
    try:
        d = requests.get(detail_url, params=dparams, timeout=20).json().get("result", {})
    except Exception:  # noqa: BLE001
        return {}
    return {
        "google_phone": d.get("formatted_phone_number", ""),
        "google_website": d.get("website", ""),
        "google_address": d.get("formatted_address", ""),
        "google_rating": d.get("rating"),
        "google_reviews": d.get("user_ratings_total"),
    }


# ---------- Hunter.io ----------

def hunter_emails(domain: str) -> list[dict[str, Any]]:
    key = env("HUNTER_API_KEY")
    if not key or not domain:
        return []
    url = "https://api.hunter.io/v2/domain-search"
    try:
        r = requests.get(url, params={"domain": domain, "api_key": key}, timeout=20).json()
    except Exception:  # noqa: BLE001
        return []
    emails = (r.get("data") or {}).get("emails") or []
    out = []
    for e in emails[:5]:
        out.append({
            "email": e.get("value", ""),
            "name": f"{e.get('first_name','')} {e.get('last_name','')}".strip(),
            "position": e.get("position", ""),
            "confidence": e.get("confidence"),
        })
    return out


def domain_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        return urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:  # noqa: BLE001
        return ""


# ---------- Apollo.io ----------

def apollo_org_lookup(company: str) -> dict[str, Any]:
    key = env("APOLLO_API_KEY")
    if not key or not company:
        return {}
    url = "https://api.apollo.io/v1/organizations/search"
    try:
        r = requests.post(
            url,
            json={"q_organization_name": company, "page": 1, "per_page": 1},
            headers={"Cache-Control": "no-cache", "Content-Type": "application/json", "X-Api-Key": key},
            timeout=20,
        ).json()
    except Exception:  # noqa: BLE001
        return {}
    orgs = r.get("organizations") or []
    if not orgs:
        return {}
    o = orgs[0]
    return {
        "apollo_domain": o.get("primary_domain", ""),
        "apollo_phone": o.get("phone", ""),
        "apollo_linkedin": o.get("linkedin_url", ""),
        "apollo_industry": o.get("industry", ""),
        "apollo_employees": o.get("estimated_num_employees"),
    }
