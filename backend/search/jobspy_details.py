"""Shared screening and cached descriptions for the supported JobSpy boards."""

from backend.observability import stage
import os
import logging
from urllib.parse import parse_qs, urlsplit
from types import SimpleNamespace

from backend.paths import JOB_DESCRIPTION_CACHE_DIR
from backend.search import linkedin_details, board_cooldown

screen_by_title = linkedin_details.screen_by_title


def pool_factor(board):
    configured = os.getenv("JOBSPY_SCREEN_POOL_FACTOR")
    if configured is None:
        return linkedin_details.pool_factor() if board == "linkedin" else 3
    try:
        return min(5, max(1, int(configured)))
    except ValueError:
        return 3


class DescriptionCache(linkedin_details.DescriptionCache):
    def __init__(self, directory=None, ttl=None, **kwargs):
        if ttl is None:
            try:
                ttl = int(os.getenv("JOBSPY_DESCRIPTION_CACHE_TTL_SECONDS", "604800"))
            except ValueError:
                ttl = 604800
        super().__init__(
            directory
            or os.getenv("JOBSPY_DESCRIPTION_CACHE_DIR")
            or JOB_DESCRIPTION_CACHE_DIR,
            ttl,
            **kwargs,
        )


class _CheckedSession:
    """Surface statuses JobSpy's detail parser otherwise converts into empty text."""

    def __init__(self, session):
        self.session = session

    def _request(self, method, *args, **kwargs):
        kwargs.setdefault("timeout", 30)
        response = getattr(self.session, method)(*args, **kwargs)
        if response.status_code == 429:
            raise linkedin_details.RateLimited()
        response.raise_for_status()
        return response

    def get(self, *args, **kwargs):
        return self._request("get", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._request("post", *args, **kwargs)


class GlassdoorDetails:
    """Reuse JobSpy's country/session setup and parser, without repeating searches."""

    def __init__(self):
        self.clients = {}

    def __call__(self, job):
        from jobspy.glassdoor import Glassdoor, headers
        from jobspy.model import Country, DescriptionFormat
        from jobspy.util import create_session

        identifier = parse_qs(urlsplit(job.get("url", "")).query).get("jl", [""])[0]
        if not identifier.isdigit():
            return {}
        country = job.get("collection_country", "australia")
        if country not in self.clients:
            client = Glassdoor()
            client.base_url = Country.from_string(country).get_glassdoor_url()
            session = create_session()
            session.headers.update(headers)
            client.session = _CheckedSession(session)
            client.scraper_input = SimpleNamespace(
                description_format=DescriptionFormat.MARKDOWN
            )
            # This establishes the cookies used by JobSpy's detail endpoint.
            client._get_location(job.get("requested_location", ""), False)
            self.clients[country] = client
        return {
            "description": self.clients[country]._fetch_job_description(int(identifier))
            or ""
        }


@stage("jobs.descriptions")
def hydrate(
    board,
    jobs,
    should_cancel=None,
    *,
    allow_network=True,
    on_error=None,
    cache=None,
    fetch=None,
    on_status=None,
    can_fetch=None,
):
    """Use inline text, then cache, then supported details; retain incomplete rows."""
    if cache is None:
        cache = (
            linkedin_details.DescriptionCache()
            if board == "linkedin"
            else DescriptionCache()
        )
    if fetch is None:
        if board == "linkedin":
            fetch = lambda job: linkedin_details.fetch_details(
                linkedin_details.job_id(job.get("url", ""))
            )
        elif board == "glassdoor":
            fetch = GlassdoorDetails()
    limited = not allow_network
    label = {
        "linkedin": "LinkedIn",
        "indeed": "Indeed",
        "glassdoor": "Glassdoor",
        "seek": "SEEK",
    }[board]
    reported = set()

    def report(message):
        if message not in reported:
            reported.add(message)
            if on_error:
                on_error(message)
            else:
                name = {
                    "linkedin": "LinkedIn",
                    "indeed": "Indeed",
                    "glassdoor": "Glassdoor",
                    "seek": "SEEK",
                }[board]
                logging.getLogger("JobSpy:" + name).error(message)

    checked = ready = reused = 0

    def progress():
        if on_status and not (should_cancel and should_cancel()):
            on_status(
                f"{label}: loading descriptions — {checked}/{len(jobs)} checked, {ready} ready ({reused} cached)."
            )

    progress()
    for job in jobs:
        if should_cancel and should_cancel():
            break
        url = job.get("url", "")
        identifier = (
            linkedin_details.job_id(url)
            if board == "linkedin"
            else (f"{board}:{url}" if url and url != "No URL provided" else None)
        )
        if job.get("description"):
            if identifier:
                cache.put(identifier, job)
            checked += 1
            ready += 1
            if checked % 5 == 0:
                progress()
            continue
        details = cache.get(identifier) if identifier else None
        if details:
            reused += 1
        if not details and can_fetch and not can_fetch():
            checked += 1
            continue
        if not details and not limited and fetch and identifier:
            if board_cooldown.remaining(board):
                limited = True
                report(board_cooldown.message(board))
        if not details and not limited and fetch and identifier:
            try:
                details = fetch(job)
            except linkedin_details.RateLimited:
                limited = True
                board_cooldown.mark_limited(board)
                report(
                    f"{label} rate-limited description requests (HTTP 429). Remaining detail requests were skipped; results may be incomplete."
                )
            except Exception:
                report(
                    f"{label} description request failed. Partial results are retained; collection may be incomplete."
                )
            if details:
                cache.put(identifier, details)
        if details and details.get("description"):
            ready += 1
            job["description"] = details["description"]
            if details.get("fetched_at"):
                job["collection_fetched_at"] = min(
                    job.get("collection_fetched_at", details["fetched_at"]),
                    details["fetched_at"],
                )
            if details.get("company_logo") and not job.get("company_logo"):
                job["company_logo"] = details["company_logo"]
        elif not limited:
            report(
                f"{label} descriptions are unavailable for some selected jobs. Partial results are retained; collection may be incomplete."
            )
        checked += 1
        if checked % 5 == 0:
            progress()
    progress()
    return jobs
