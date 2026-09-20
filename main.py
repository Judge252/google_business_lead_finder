from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
import urllib.parse
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
APP_USER_AGENT = os.getenv(
    "APP_USER_AGENT",
    "BusinessLeadFinder/1.0 (+public-business-contact-research)",
)
WEBSITE_FETCH_TIMEOUT = max(3, min(int(os.getenv("WEBSITE_FETCH_TIMEOUT", "8")), 20))
MAX_WEBSITE_PAGES = max(1, min(int(os.getenv("MAX_WEBSITE_PAGES", "3")), 5))

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.primaryType",
        "places.primaryTypeDisplayName",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.rating",
        "places.userRatingCount",
        "nextPageToken",
    ]
)

GENERIC_EMAIL_PREFIXES = {
    "info", "contact", "hello", "sales", "support", "booking", "bookings",
    "office", "admin", "marketing", "business", "team", "care", "help",
    "reservations", "reservation", "reception", "enquiries", "inquiries",
    "customerservice", "customer.service", "service", "orders", "clinic",
}
SOCIAL_HOSTS = {
    "instagram.com": "instagram",
    "www.instagram.com": "instagram",
    "facebook.com": "facebook",
    "www.facebook.com": "facebook",
    "linkedin.com": "linkedin",
    "www.linkedin.com": "linkedin",
}
CONTACT_HINTS = (
    "contact", "contact-us", "about", "about-us", "reach-us", "get-in-touch",
)

EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b")


app = FastAPI(title="Google Business Lead Finder", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SearchRequest(BaseModel):
    service: str = Field(min_length=2, max_length=120)
    location: str = Field(min_length=2, max_length=160)
    max_results: int = Field(default=20, ge=1, le=60)
    enrich_websites: bool = True


def normalize_host(host: str) -> str:
    host = (host or "").lower().strip().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def is_public_http_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if not parsed.hostname:
            return False

        host = parsed.hostname.lower()
        if host in {"localhost"} or host.endswith(".local"):
            return False

        # Resolve every current address and reject private/reserved/link-local/etc.
        addr_infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        if not addr_infos:
            return False

        for info in addr_infos:
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                return False
        return True
    except Exception:
        return False


def allowed_by_robots(url: str, session: requests.Session) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        if not is_public_http_url(robots_url):
            return False

        resp = session.get(
            robots_url,
            headers={"User-Agent": APP_USER_AGENT},
            timeout=WEBSITE_FETCH_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            # No usable robots file: do not infer a prohibition.
            return True

        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(resp.text.splitlines())
        return rp.can_fetch(APP_USER_AGENT, url)
    except Exception:
        # Conservative fallback if robots check itself fails.
        return False


def safe_get_html(url: str, session: requests.Session) -> tuple[str, str] | None:
    if not is_public_http_url(url):
        return None
    if not allowed_by_robots(url, session):
        return None

    try:
        resp = session.get(
            url,
            headers={
                "User-Agent": APP_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=WEBSITE_FETCH_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        if not is_public_http_url(resp.url):
            return None
        if resp.status_code >= 400:
            return None

        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
            return None

        max_bytes = 1_000_000
        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=32768):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                break
            chunks.append(chunk)

        raw = b"".join(chunks)
        encoding = resp.encoding or "utf-8"
        text = raw.decode(encoding, errors="replace")
        return resp.url, text
    except Exception:
        return None


def business_email_ok(email: str) -> bool:
    email = email.strip().lower().strip(".,;:()[]{}<>")
    if "@" not in email:
        return False
    local, domain = email.rsplit("@", 1)
    if len(email) > 254 or len(local) > 64:
        return False
    if local in GENERIC_EMAIL_PREFIXES:
        return True
    if any(local.startswith(prefix + ".") or local.startswith(prefix + "-") for prefix in GENERIC_EMAIL_PREFIXES):
        return True
    return False


def contact_page_candidates(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    base_host = normalize_host(urllib.parse.urlparse(base_url).hostname or "")

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        label = " ".join(a.stripped_strings).lower()
        href_l = href.lower()

        if not any(hint in href_l or hint.replace("-", " ") in label for hint in CONTACT_HINTS):
            continue

        absolute = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if normalize_host(parsed.hostname or "") != base_host:
            continue

        clean = urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path or "/", "", "", "")
        )
        if clean not in candidates:
            candidates.append(clean)

    return candidates[: max(0, MAX_WEBSITE_PAGES - 1)]


def extract_contacts_from_html(page_url: str, html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    emails = set()
    phones = set()
    whatsapp = set()
    social = {"instagram": set(), "facebook": set(), "linkedin": set()}

    for email in EMAIL_RE.findall(text):
        email = email.lower()
        if business_email_ok(email):
            emails.add(email)

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue

        if href.lower().startswith("mailto:"):
            email = urllib.parse.unquote(href[7:].split("?", 1)[0]).strip().lower()
            if business_email_ok(email):
                emails.add(email)
            continue

        if href.lower().startswith("tel:"):
            phone = urllib.parse.unquote(href[4:]).strip()
            phone = re.sub(r"\s+", " ", phone)
            if 6 <= len(re.sub(r"\D", "", phone)) <= 16:
                phones.add(phone)
            continue

        absolute = urllib.parse.urljoin(page_url, href)
        parsed = urllib.parse.urlparse(absolute)
        host = (parsed.hostname or "").lower()

        if host in {"wa.me", "www.wa.me", "api.whatsapp.com", "whatsapp.com", "www.whatsapp.com"}:
            whatsapp.add(absolute)
        elif host in SOCIAL_HOSTS:
            social[SOCIAL_HOSTS[host]].add(absolute)

    return {
        "emails": sorted(emails),
        "website_phones": sorted(phones),
        "whatsapp": sorted(whatsapp),
        "instagram": sorted(social["instagram"]),
        "facebook": sorted(social["facebook"]),
        "linkedin": sorted(social["linkedin"]),
    }


def merge_contact_data(target: dict[str, set], data: dict[str, Any]) -> None:
    for key in target:
        for item in data.get(key, []):
            target[key].add(item)


def enrich_website(website: str) -> dict[str, Any]:
    empty = {
        "emails": [],
        "website_phones": [],
        "whatsapp": [],
        "instagram": [],
        "facebook": [],
        "linkedin": [],
        "enrichment_status": "not_enriched",
    }
    if not website or not is_public_http_url(website):
        return empty

    session = requests.Session()
    merged = {
        "emails": set(),
        "website_phones": set(),
        "whatsapp": set(),
        "instagram": set(),
        "facebook": set(),
        "linkedin": set(),
    }

    first = safe_get_html(website, session)
    if not first:
        empty["enrichment_status"] = "blocked_or_unavailable"
        return empty

    final_url, html = first
    merge_contact_data(merged, extract_contacts_from_html(final_url, html))

    candidates = contact_page_candidates(final_url, html)
    for candidate in candidates:
        time.sleep(0.15)
        page = safe_get_html(candidate, session)
        if not page:
            continue
        page_url, page_html = page
        merge_contact_data(merged, extract_contacts_from_html(page_url, page_html))

    result = {key: sorted(values) for key, values in merged.items()}
    result["enrichment_status"] = "ok"
    return result


def lead_score(lead: dict[str, Any]) -> int:
    score = 0
    if lead.get("phone"):
        score += 15
    if lead.get("website"):
        score += 10
    if lead.get("emails"):
        score += 20
    if lead.get("whatsapp"):
        score += 20
    if lead.get("instagram") or lead.get("facebook") or lead.get("linkedin"):
        score += 10

    rating = lead.get("rating")
    if isinstance(rating, (int, float)):
        score += min(10, max(0, round((rating / 5) * 10)))

    reviews = lead.get("review_count") or 0
    if reviews >= 500:
        score += 10
    elif reviews >= 100:
        score += 7
    elif reviews >= 20:
        score += 4

    if lead.get("address"):
        score += 5

    return min(score, 100)


def place_to_lead(place: dict[str, Any]) -> dict[str, Any]:
    display = place.get("displayName") or {}
    ptype = place.get("primaryTypeDisplayName") or {}
    return {
        "place_id": place.get("id", ""),
        "business_name": display.get("text", ""),
        "category": ptype.get("text") or place.get("primaryType", ""),
        "address": place.get("formattedAddress", ""),
        "phone": place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber", ""),
        "website": place.get("websiteUri", ""),
        "google_maps_url": place.get("googleMapsUri", ""),
        "rating": place.get("rating"),
        "review_count": place.get("userRatingCount", 0),
        "emails": [],
        "website_phones": [],
        "whatsapp": [],
        "instagram": [],
        "facebook": [],
        "linkedin": [],
        "enrichment_status": "not_requested",
        "lead_score": 0,
    }


def google_text_search(service: str, location: str, max_results: int) -> list[dict[str, Any]]:
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_MAPS_API_KEY is not configured. Add it to your .env file.",
        )

    text_query = f"{service.strip()} in {location.strip()}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": PLACES_FIELD_MASK,
    }

    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    page_token: str | None = None

    while len(collected) < max_results:
        remaining = max_results - len(collected)
        payload: dict[str, Any] = {
            "textQuery": text_query,
            "pageSize": min(20, remaining),
        }
        if page_token:
            payload["pageToken"] = page_token

        try:
            resp = requests.post(
                PLACES_SEARCH_URL,
                headers=headers,
                json=payload,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Google Places request failed: {exc}") from exc

        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text[:500]
            raise HTTPException(
                status_code=resp.status_code if resp.status_code < 500 else 502,
                detail={"message": "Google Places API returned an error", "google": detail},
            )

        data = resp.json()
        for place in data.get("places", []):
            place_id = place.get("id")
            if place_id and place_id in seen_ids:
                continue
            if place_id:
                seen_ids.add(place_id)
            collected.append(place)
            if len(collected) >= max_results:
                break

        page_token = data.get("nextPageToken")
        if not page_token or len(collected) >= max_results:
            break

    return collected[:max_results]


@app.get("/")
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "google_key_configured": bool(GOOGLE_MAPS_API_KEY),
        "max_results_per_query": 60,
        "website_enrichment": True,
    }


@app.post("/api/search")
def search(req: SearchRequest):
    service = req.service.strip()
    location = req.location.strip()

    places = google_text_search(service, location, req.max_results)
    leads = [place_to_lead(p) for p in places]

    if req.enrich_websites:
        indexes = [i for i, lead in enumerate(leads) if lead.get("website")]
        # Keep concurrency moderate so the tool doesn't hammer third-party websites.
        with ThreadPoolExecutor(max_workers=min(5, max(1, len(indexes)))) as pool:
            futures = {
                pool.submit(enrich_website, leads[i]["website"]): i
                for i in indexes
            }
            for future in as_completed(futures):
                i = futures[future]
                try:
                    leads[i].update(future.result())
                except Exception:
                    leads[i]["enrichment_status"] = "error"

    for lead in leads:
        lead["lead_score"] = lead_score(lead)

    leads.sort(key=lambda x: (x.get("lead_score", 0), x.get("review_count", 0)), reverse=True)

    return {
        "query": f"{service} in {location}",
        "count": len(leads),
        "leads": leads,
    }
