"""Fetch LinkedIn descriptions only for screened jobs, reusing cached public text.

LinkedIn search cards expose title, company, location and date but no
description. Opening every job page triggers rate limits, so the collector
first screens cards by title, then fetches descriptions for the kept pool.
Only public posting text is cached; candidate data is never stored here.
"""

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

from backend.paths import LINKEDIN_DESCRIPTION_CACHE_DIR

LOGGER = logging.getLogger(__name__)
# Reuse JobSpy's LinkedIn logger so existing failure reporting shows the 429.
JOBSPY_LOGGER = logging.getLogger("JobSpy:LinkedIn")
# LinkedIn's guest pages answer HTTP 429 to quick bursts; space job-page requests.
REQUEST_INTERVAL_SECONDS = 2.0
_last_request = [0.0]
_JOB_ID = re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d+)")
_WORD = re.compile(r"[a-z0-9+#]+")
_STOPWORDS = {"and", "or", "the", "a", "an", "of", "for", "in", "to", "with", "at"}


def pool_factor() -> int:
    """How many search cards to screen per kept LinkedIn job (1 disables screening)."""
    try:
        return min(5, max(1, int(os.getenv("LINKEDIN_SCREEN_POOL_FACTOR", "3"))))
    except ValueError:
        return 3


def job_id(url: str) -> str | None:
    match = _JOB_ID.search(url or "")
    return match.group(1) if match else None


def _tokens(text: str) -> set[str]:
    return {
        word for word in _WORD.findall((text or "").lower()) if word not in _STOPWORDS
    }


def screen_by_title(jobs: list[dict], queries: list[str], keep: int) -> list[dict]:
    """Keep the jobs whose titles best overlap a requested role; ties keep board order."""
    if len(jobs) <= keep:
        return list(jobs)
    roles = [_tokens(query) for query in queries if _tokens(query)]

    def score(job):
        title = _tokens(job.get("title", ""))
        if not roles or not title:
            return 0.0
        return max(len(title & role) / len(role) for role in roles)

    ranked = sorted(enumerate(jobs), key=lambda pair: (-score(pair[1]), pair[0]))
    return [job for _, job in ranked[:keep]]


class DescriptionCache:
    """Small per-posting cache keyed by LinkedIn job id with a bounded lifetime."""

    def __init__(self, directory=None, ttl=None, clock=time.time):
        self.directory = Path(
            directory
            or os.getenv("LINKEDIN_DESCRIPTION_CACHE_DIR")
            or LINKEDIN_DESCRIPTION_CACHE_DIR
        )
        if ttl is None:
            try:
                ttl = int(os.getenv("LINKEDIN_DESCRIPTION_CACHE_TTL_SECONDS", "604800"))
            except ValueError:
                ttl = 604800
        self.ttl = max(0, ttl)
        self.clock = clock

    def _path(self, identifier: str) -> Path:
        return (
            self.directory / f"{hashlib.sha256(identifier.encode()).hexdigest()}.json"
        )

    def get(self, identifier: str) -> dict | None:
        path = self._path(identifier)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                0 <= self.clock() - payload["fetched_at"] < self.ttl
                and payload["description"]
            ):
                return payload
        except (OSError, ValueError, KeyError, TypeError):
            return None
        try:
            path.unlink()  # Expired entries are removed opportunistically.
        except OSError:
            pass
        return None

    def put(self, identifier: str, details: dict) -> None:
        if not self.ttl or not details.get("description"):
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self._path(identifier)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "fetched_at": self.clock(),
                        "description": details["description"],
                        "company_logo": details.get("company_logo") or "",
                        "posted_at": details.get("posted_at") or "",
                    }
                ),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            LOGGER.warning("LinkedIn description cache write failed")


class RateLimited(Exception):
    """LinkedIn returned HTTP 429; stop contacting it for the rest of the run."""


def fetch_details(identifier: str, session=None) -> dict:
    """Fetch one public job page. Raises RateLimited on HTTP 429."""
    from bs4 import BeautifulSoup
    from jobspy.util import markdown_converter, remove_attributes

    if session is None:
        import requests

        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0"
    # The collector is sequential, so one shared timestamp is enough.
    time.sleep(max(0.0, _last_request[0] + REQUEST_INTERVAL_SECONDS - time.monotonic()))
    _last_request[0] = time.monotonic()
    response = session.get(
        f"https://www.linkedin.com/jobs/view/{identifier}", timeout=15
    )
    if response.status_code == 429:
        raise RateLimited()
    if response.status_code != 200 or "linkedin.com/signup" in str(response.url):
        return {}
    soup = BeautifulSoup(response.text, "html.parser")
    markup = soup.find("div", class_=lambda x: x and "show-more-less-html__markup" in x)
    logo = soup.find("img", {"class": "artdeco-entity-image"})
    # The page shows the latest posting ("Reposted 6 days ago"); search cards keep
    # the original date. Store it as a date so cached copies stay correct.
    from backend.search.collection import _parse_posted_at

    shown = soup.find(class_="posted-time-ago__text")
    posted = _parse_posted_at(shown.get_text(" ", strip=True)) if shown else None
    return {
        "posted_at": posted.date().isoformat() if posted else "",
        "description": (
            (
                markdown_converter(remove_attributes(markup).prettify(formatter="html"))
                or ""
            ).strip()
            if markup is not None
            else ""
        ),
        "company_logo": (logo.get("data-delayed-url") or "") if logo else "",
    }


def hydrate(
    jobs: list[dict], should_cancel=None, cache=None, fetch=fetch_details
) -> list[dict]:
    """Fill missing descriptions from cache first, then from LinkedIn until rate-limited."""
    cache = cache or DescriptionCache()
    limited = False
    fetched = reused = 0
    for job in jobs:
        identifier = job_id(job.get("url", ""))
        if job.get("description") or not identifier:
            continue
        details = cache.get(identifier)
        if details:
            reused += 1
        elif limited or (should_cancel and should_cancel()):
            continue
        else:
            try:
                details = fetch(identifier)
            except RateLimited:
                limited = True
                JOBSPY_LOGGER.error("LinkedIn response status code 429")
                continue
            except Exception:
                LOGGER.warning("LinkedIn description request failed")
                continue
            fetched += 1
            cache.put(identifier, details)
        job["description"] = details.get("description") or ""
        if details.get("posted_at"):
            job["posted_at"] = details["posted_at"]
        if details.get("company_logo") and not job.get("company_logo"):
            job["company_logo"] = details["company_logo"]
    LOGGER.info(
        "LinkedIn descriptions fetched=%d reused=%d rate_limited=%s",
        fetched,
        reused,
        limited,
    )
    return jobs
