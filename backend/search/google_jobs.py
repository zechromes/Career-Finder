"""Google Jobs through SerpApi: one paid search per page of up to 10 postings."""

import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.search.board_cooldown import RateLimitNotice


class GoogleJobsError(RuntimeError):
    """Carries a page-safe message; it never contains the API key or request URL."""


class NoResults(GoogleJobsError):
    """One search found nothing; other searches can still run."""


# Countries Google Jobs does not serve (https://serpapi.com/google-jobs-countries).
# shortcut: lists only the codes collection's country lookup can return; extend it
# if that lookup learns more countries.
UNSUPPORTED_COUNTRIES = {"au", "nz"}

# Entered place (normalized) -> SerpApi canonical location, for this process.
_LOCATIONS = {}


def resolve_location(location, country="", timeout=15):
    """Map an entered place to SerpApi's canonical location; None when unknown.

    Uses SerpApi's free Locations API. Later comma parts (state, country) pick
    between same-named places, then the expected country; ties keep reach order.
    """
    parts = [part.strip() for part in location.split(",") if part.strip()]
    key = ",".join(parts).casefold()
    if not parts:
        return None
    if key not in _LOCATIONS:
        try:
            with urlopen(
                "https://serpapi.com/locations.json?"
                + urlencode({"q": parts[0], "limit": 10}),
                timeout=timeout,
            ) as response:
                rows = json.loads(response.read(1024 * 1024)) or []
        except Exception:
            return None
        wanted = [part.casefold() for part in parts[1:]]
        best = max(
            rows,
            key=lambda row: (
                sum(w in row.get("canonical_name", "").casefold() for w in wanted),
                str(row.get("country_code", "")).lower() == country,
            ),
            default=None,
        )
        _LOCATIONS[key] = (best or {}).get("canonical_name")
    return _LOCATIONS[key]


def search_page(query, location="", token="", country="", timeout=30):
    """Return (jobs, next_page_token); an empty token means there are no more pages."""
    key = os.getenv("SERPAPI_API_KEY")
    if not key:
        raise GoogleJobsError(
            "Google Jobs needs SERPAPI_API_KEY in .env; other sources can continue."
        )
    canonical = resolve_location(location, country) if location else None
    params = {"engine": "google_jobs", "q": query, "hl": "en", "api_key": key}
    if canonical:
        # Google searches from the entered place, as SerpApi names it.
        params["location"] = canonical
    else:
        # Unknown place: name it in the query and search from its country.
        params["q"] = " ".join(part for part in (query, location) if part)
        if country:
            params["gl"] = country
    if token:
        params["next_page_token"] = token
    try:
        with urlopen(
            "https://serpapi.com/search?" + urlencode(params), timeout=timeout
        ) as response:
            data = json.loads(response.read(5 * 1024 * 1024))
    except HTTPError as exc:
        if exc.code == 429:
            raise GoogleJobsError(
                RateLimitNotice(
                    "Google Jobs rate-limited the request (HTTP 429). Results may be incomplete."
                )
            ) from None
        # SerpApi explains a rejected request in its JSON body; it holds no key.
        try:
            reason = str(json.loads(exc.read(64 * 1024)).get("error", ""))[:200]
        except Exception:
            reason = ""
        raise GoogleJobsError(
            f"Google Jobs request failed (HTTP {exc.code})"
            + (f": {reason}" if reason else "")
            + ". Other sources can continue."
        ) from None
    except Exception:
        raise GoogleJobsError(
            "Google Jobs could not be reached. Other sources can continue."
        ) from None
    searched = f"'{params['q']}'" + (f" near {canonical}" if canonical else "")
    # SerpApi reports an empty first page as an error string; say so instead of
    # returning silently, so an empty search is visible.
    if data.get("error"):
        if "hasn't returned any results" not in data["error"]:
            raise GoogleJobsError(f"Google Jobs (SerpApi): {data['error'][:200]}")
        if token:
            return [], ""
        raise NoResults(f"Google Jobs found no jobs for {searched}.")
    if not token and not data.get("jobs_results"):
        raise NoResults(f"Google Jobs found no jobs for {searched}.")
    jobs = []
    for row in data.get("jobs_results") or []:
        options = row.get("apply_options") or []
        jobs.append(
            {
                "title": row.get("title") or "Unknown Title",
                "company": row.get("company_name") or "Unknown Company",
                "location": row.get("location") or "",
                "description": row.get("description") or "",
                "url": (options[0].get("link") if options else "")
                or row.get("share_link")
                or "",
                "source_platform": "google",
                "posted_at": (row.get("detected_extensions") or {}).get(
                    "posted_at", ""
                ),
                "company_logo": row.get("thumbnail") or "",
            }
        )
    return jobs, (data.get("serpapi_pagination") or {}).get("next_page_token", "")
