# Application entry point and helpers for collection.
from backend.observability import stage, submit, mark
from backend.search.embedding_cache import CachedJobEmbeddings
from backend.search.collection_cache import CollectionCache
from backend.paths import JOB_EMBEDDING_CACHE_DIR
from difflib import SequenceMatcher
from backend.search.embedding_text import job_embedding_text
import os
import logging
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import json

load_dotenv()


def _text_value(item: dict, *keys: str, default: str = "") -> str:
    """Read the first useful text value across actor-specific field names."""
    for key in keys:
        value = item.get(key)
        if isinstance(value, list):
            parts = []
            for part in value:
                if isinstance(part, dict):
                    part = part.get("label") or part.get("name") or part.get("text")
                if part:
                    parts.append(str(part))
            value = ", ".join(parts)
        elif isinstance(value, dict):
            value = (
                value.get("label")
                or value.get("name")
                or value.get("text")
                or value.get("location")
            )
        if value:
            return str(value).strip()
    return default


def _description_value(item):
    """Prefer the richest description across board-specific response fields."""
    values = [
        _text_value(item, key)
        for key in (
            "description",
            "jobDescription",
            "jobDescriptionText",
            "descriptionText",
            "descriptionHtml",
            "description_html",
            "job_description",
            "job_description_html",
        )
    ]
    return max(values, key=lambda value: len(re.sub(r"<[^>]+>", "", value)), default="")


def _posted_value(item: dict) -> str:
    """Read common publication-date fields from different job sources."""
    return _text_value(
        item,
        "posted_at",
        "postedAt",
        "date_posted",
        "datePosted",
        "publishedAt",
        "published",
        "published_date",
        "listingDate",
        "posted",
        "created",
        "createdAt",
        "date",
    )


def _parse_posted_at(posted_at: str) -> datetime | None:
    """Parse absolute and relative dates returned by job-board scrapers."""
    if not posted_at:
        return None
    text = posted_at.strip().lower()
    try:
        posted = datetime.fromisoformat(text.replace("z", "+00:00"))
    except ValueError:
        try:
            posted = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            now = datetime.now(timezone.utc)
            if text in {"today", "just now", "just posted"}:
                return now
            if text == "yesterday":
                return now - timedelta(days=1)
            match = re.search(r"(\d+)\s*(hour|day|week|month)s?\s*ago", text)
            if match:
                amount = int(match.group(1))
                unit = match.group(2)
                delta = {
                    "hour": timedelta(hours=amount),
                    "day": timedelta(days=amount),
                    "week": timedelta(weeks=amount),
                    "month": timedelta(days=amount * 30),
                }[unit]
                return now - delta
            return None
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return posted.astimezone(timezone.utc)


def _is_recent(posted_at: str, days_old: int) -> bool:
    """Return true when a source date is inside the selected age window."""
    posted = _parse_posted_at(posted_at)
    if posted is None:
        # Keep undated records because some boards omit publication metadata.
        return True
    return posted >= datetime.now(timezone.utc) - timedelta(days=days_old)


def _newest_first(jobs: list[dict]) -> list[dict]:
    """Put dated postings first while keeping undated records at the end."""
    return sorted(
        jobs,
        key=lambda job: _parse_posted_at(job.get("posted_at", ""))
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


@stage("jobs.filter_age")
def _filter_recent_jobs(jobs: list[dict], days_old: int) -> list[dict]:
    """Apply the requested posting-age filter after source normalization."""
    if days_old == 0:
        return jobs
    recent = [job for job in jobs if _is_recent(job.get("posted_at", ""), days_old)]
    removed = len(jobs) - len(recent)
    if removed:
        print(f"Removed {removed} jobs older than {days_old} day(s).")
    return recent


# Recognize location inputs that request unrestricted geographic collection.
def _worldwide(locations: list[str]) -> bool:
    return not any(location.strip() for location in locations) or any(
        location.strip().casefold() == "worldwide" for location in locations
    )


def _location_matches(job_location: str, requested_locations: list[str]) -> bool:
    from backend.search.locations import location_matches

    return location_matches(job_location, requested_locations)


@stage("jobs.filter_location")
def _filter_requested_locations(
    jobs: list[dict], requested_locations: list[str]
) -> list[dict]:
    """Remove provider spillover before jobs are embedded or evaluated."""
    filtered = [
        job
        for job in jobs
        if _location_matches(job.get("location", ""), requested_locations)
    ]
    removed = len(jobs) - len(filtered)
    if removed:
        print(
            f"Removed {removed} jobs with unmatched or unknown locations before vectorization."
        )
    return filtered


def _canonical_url(value: str) -> str:
    """Remove tracking parameters so the same posting has one identity."""
    value = (value or "").strip()
    if not value or value.lower().startswith("no url"):
        return ""
    try:
        parts = urlsplit(value)
        if not parts.netloc:
            return value.lower().rstrip("/")
        query = [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith(("utm_", "trk", "ref", "source"))
        ]
        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                parts.path.rstrip("/"),
                urlencode(query),
                "",
            )
        )
    except ValueError:
        return value.lower().rstrip("/")


def _job_key(job: dict) -> str:
    """Build a stable key, preferring the source URL over text fields."""
    url = _canonical_url(job.get("url", ""))
    if url:
        return f"url:{url}"
    fields = (job.get("title", ""), job.get("company", ""), job.get("location", ""))
    return "text:" + "|".join(
        re.sub(r"\s+", " ", str(field)).strip().lower() for field in fields
    )


def deduplicate_jobs(jobs: list[dict]) -> list[dict]:
    """Keep one copy of each posting returned by overlapping searches."""
    unique = {}
    for job in jobs:
        key = _job_key(job)
        existing = unique.get(key)
        # Prefer the record with a real description or URL when two records
        # have the same fallback identity.
        if existing is None or len(job.get("description", "")) > len(
            existing.get("description", "")
        ):
            unique[key] = job
    # Cross-board duplicates need matching role/employer/location plus highly
    # similar descriptions. Do not merge distinct openings on title alone.
    grouped = {}
    for job in unique.values():
        normalize = lambda value: re.sub(r"[^\w]+", " ", str(value).casefold()).strip()
        identity = tuple(
            normalize(job.get(field, "")) for field in ("company", "title", "location")
        )
        description = normalize(job.get("description", ""))
        group = grouped.setdefault(identity, [])
        duplicate = next(
            (
                existing
                for existing in group
                if all(identity)
                and len(description) >= 100
                and SequenceMatcher(
                    None,
                    description,
                    normalize(existing.get("description", "")),
                    autojunk=False,
                ).ratio()
                >= 0.95
            ),
            None,
        )
        if duplicate is None:
            group.append(job)
        elif len(job.get("description", "")) > len(duplicate.get("description", "")):
            group[group.index(duplicate)] = job
    result = [job for group in grouped.values() for job in group]
    removed = len(jobs) - len(result)
    if removed:
        print(f"Removed {removed} duplicate job postings before matching.")
    return result


# Adzuna exposes separate job indexes per country, without a global endpoint.
ADZUNA_COUNTRIES = {
    "at": "Austria",
    "au": "Australia",
    "be": "Belgium",
    "br": "Brazil",
    "ca": "Canada",
    "ch": "Switzerland",
    "de": "Germany",
    "es": "Spain",
    "fr": "France",
    "gb": "United Kingdom",
    "in": "India",
    "it": "Italy",
    "mx": "Mexico",
    "nl": "Netherlands",
    "nz": "New Zealand",
    "pl": "Poland",
    "sg": "Singapore",
    "us": "United States",
    "za": "South Africa",
}


def _country_for_location(location: str) -> str:
    """Map common locations to Adzuna's country path."""
    text = location.lower()
    country_codes = {
        "au": ("australia", "sydney", "melbourne", "brisbane", "perth", "adelaide"),
        "us": (
            "united states",
            "usa",
            "florida",
            "new york",
            "california",
            "texas",
            "seattle",
            "chicago",
        ),
        "gb": ("united kingdom", "uk", "england", "london", "manchester"),
        "ca": ("canada", "toronto", "vancouver", "montreal"),
        "nz": ("new zealand", "auckland", "wellington"),
        "sg": ("singapore",),
    }
    for code, terms in country_codes.items():
        if any(term in text for term in terms):
            return code
    return os.getenv("ADZUNA_COUNTRY", "au").lower()


def _group_apify_locations(locations: list[str]) -> list[tuple[str, list[str]]]:
    """Combine hierarchical city inputs into one broad search per country."""
    if _worldwide(locations):
        return [("Worldwide", ["Worldwide"])]
    groups = {}
    for location in locations:
        parts = [part.strip() for part in location.split(",") if part.strip()]
        # A full city/region/country value has a reliable country suffix. Keep
        # short or ambiguous values as independent searches for accuracy.
        country = parts[-1] if len(parts) >= 3 else location.strip()
        key = country.casefold()
        groups.setdefault(key, {"search_location": country, "locations": []})[
            "locations"
        ].append(location)
    return [(group["search_location"], group["locations"]) for group in groups.values()]


def _fetch_adzuna_jobs(
    queries: list[str],
    locations: list[str],
    n_result: int,
    remote: bool,
    posted_days_old: int,
    on_progress=None,
    on_error=None,
    should_cancel=None,
) -> list[dict]:
    """Fetch jobs through Adzuna's JSON API without starting scraper actors."""
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise ValueError(
            "Set ADZUNA_APP_ID and ADZUNA_APP_KEY to use the Adzuna search provider."
        )

    worldwide = _worldwide(locations)
    search_locations = list(ADZUNA_COUNTRIES) if worldwide else locations

    # Fetch one configured search unit so failures can be isolated from other sources.
    def fetch_one(query: str, location: str) -> list[dict]:
        if should_cancel and should_cancel():
            return []
        country = location if worldwide else _country_for_location(location)
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": min(max(n_result, 1), 50),
            "what": query,
            "where": location,
            "content-type": "application/json",
            "sort_by": "date",
        }
        if worldwide:
            params.pop("where")
        if posted_days_old:
            params["max_days_old"] = posted_days_old
        if remote:
            params["what"] = f"{query} remote"
        endpoint = (
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?{urlencode(params)}"
        )
        request = Request(endpoint, headers={"User-Agent": "CareerTracker/1.0"})
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            {
                "title": _text_value(item, "title", default="Unknown Title"),
                "company": _text_value(
                    item.get("company", {}), "display_name", default="Unknown Company"
                ),
                "location": _text_value(
                    item.get("location", {}),
                    "display_name",
                    default=ADZUNA_COUNTRIES[location] if worldwide else location,
                ),
                "description": _description_value(item),
                "company_logo": _text_value(
                    item, "company_logo", "companyLogo", "companyLogoUrl", "logoUrl"
                ),
                "url": _text_value(item, "redirect_url", default="No URL provided"),
                "source_platform": "adzuna",
                "requested_location": location,
                "posted_at": _posted_value(item),
            }
            for item in payload.get("results", [])
        ]

    jobs = []
    with ThreadPoolExecutor(
        max_workers=min(8, max(1, len(queries) * len(search_locations)))
    ) as executor:
        futures = [
            submit(executor, fetch_one, query, location)
            for query in queries
            for location in search_locations
        ]
        for future in as_completed(futures):
            if should_cancel and should_cancel():
                for pending in futures:
                    pending.cancel()
                break
            try:
                jobs.extend(future.result())
                if on_progress:
                    on_progress(len(deduplicate_jobs(jobs)))
            except Exception:
                if on_error:
                    on_error(
                        "A job search failed. Partial results are retained; retry scraping to try again."
                    )
                else:
                    raise
    jobs = deduplicate_jobs(jobs)
    jobs = _filter_requested_locations(jobs, locations)
    return _newest_first(_filter_recent_jobs(jobs, posted_days_old))


def _jobspy_countries(location: str, site: str) -> list[str]:
    """Select country indexes for boards that cannot search globally."""
    from jobspy.model import Country

    supported = [
        country
        for country in Country
        if country.name not in {"WORLDWIDE", "US_CANADA"}
        and (site != "glassdoor" or len(country.value) == 3)
    ]
    if _worldwide([location]):
        return [country.value[0].split(",")[0] for country in supported]
    parts = [part.strip().casefold() for part in location.split(",")]
    for part in reversed(parts):
        for country in supported:
            aliases = country.value[0].split(",") + [country.value[1].split(":")[-1]]
            if part in aliases:
                return [country.value[0].split(",")[0]]
    # City-only inputs retain the existing country inference and AU fallback.
    code = _country_for_location(location)
    for country in supported:
        if code == country.value[1].split(":")[-1]:
            return [country.value[0].split(",")[0]]
    raise ValueError(f"{site} does not support the country for {location}.")


class _ScraperFailures(logging.Handler):
    """JobSpy sometimes logs an error and returns partial rows instead of raising."""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.failed = False
        self.failures = set()

    def emit(self, record):
        self.failed = True
        # Persist only an allowlisted source and status category, never raw logs
        # (which can contain request URLs, search terms or credentials).
        board = {
            "linkedin": "LinkedIn",
            "indeed": "Indeed",
            "glassdoor": "Glassdoor",
        }.get(record.name.partition(":")[2].lower(), "A job board")
        message = record.getMessage()
        status = re.search(
            r"\b(?:status(?:\s+code)?|HTTP)\s*[:=]?\s*(429|403)\b", message, re.I
        )
        self.failures.add((board, status.group(1) if status else "unknown"))

    def messages(self):
        messages = []
        for board, status in sorted(self.failures):
            if status == "429":
                detail = "rate-limited the request (HTTP 429). Wait before searching this board again, or deselect it to continue with other sources."
            elif status == "403":
                detail = "blocked the request (HTTP 403). You can deselect this board and continue with other sources."
            else:
                detail = "reported a request failure. The cause was not confirmed; try this board again later."
            messages.append(
                f"{board} {detail} Results already collected are retained, but may be incomplete."
            )
        return messages


class _RateLimitObserver(logging.Handler):
    """Flag a board's HTTP 429 so its remaining searches in this run are skipped."""

    def __init__(self, board):
        super().__init__(logging.ERROR)
        self.board = board
        self.hit = False

    def emit(self, record):
        if re.search(
            r"\b(?:status(?:\s+code)?|HTTP)\s*[:=]?\s*429\b", record.getMessage(), re.I
        ):
            from backend.search import board_cooldown

            self.hit = True
            board_cooldown.mark_limited(self.board)


@stage("jobs.collect")
def fetch_job_vacancies(
    queries: list[str],
    locations: list[str],
    platforms: list[str],
    n_result: int = 50,
    remote: bool = False,
    posted_days_old: int = 30,
    on_progress=None,
    on_error=None,
    should_cancel=None,
    force_refresh: bool = False,
    search_filters: dict | None = None,
    on_status=None,
    adaptive=False,
    seen_postings=None,
):
    """Reuse recent complete searches; expired and failed searches are recollected."""
    provider = os.getenv("JOB_SEARCH_PROVIDER", "jobspy").lower()
    platforms = [site for site in platforms if site not in {"greenhouse", "lever"}]
    if not platforms:
        raise ValueError(
            "Select at least one supported job board: LinkedIn, Indeed, Glassdoor or SEEK."
        )
    search_filters = search_filters or {}
    constrained = (
        bool(search_filters.get("exclusions"))
        or search_filters.get("work_type", "any") != "any"
        or search_filters.get("seniority", "auto") not in {"auto", "any"}
    )
    from backend.search.adaptive import settings

    adaptive_config = settings() if adaptive and provider != "adzuna" else None
    collection_limit = n_result * 3 if constrained and not adaptive_config else n_result
    from backend.search.jobspy_details import pool_factor

    parameters = {
        "screen_pool_factors": {
            site: pool_factor(site)
            for site in platforms
            if site in {"linkedin", "indeed", "glassdoor"}
        },
        "policy": "collection-v11-jobspy-descriptions",
        "adaptive": adaptive_config,
        "previous_postings": (
            sorted(_job_key(job) for job in (seen_postings or []))
            if adaptive_config
            else []
        ),
        "provider": provider,
        "search_filters": search_filters,
        # Preserve order: board budgets can make query/country order significant.
        "queries": queries,
        "locations": locations,
        "platforms": platforms,
        "limit": n_result,
        "remote": remote,
        "posted_days_old": posted_days_old,
    }

    def fetch():
        errors = []
        reported = set()

        def report(message):
            mark("partial")
            # A detail failure and later skipped batches are one rate-limit event.
            # Keep the first cause, without accumulating changing cooldown text.
            lowered = message.lower()
            board = next(
                (name for name in platforms if lowered.startswith(name.lower())), None
            )
            key = (
                (board, "rate-limit")
                if board
                and (
                    "rate-limit" in lowered
                    or "rate limit" in lowered
                    or "429" in lowered
                )
                else message
            )
            if key in reported:
                return
            reported.add(key)
            errors.append(message)
            if on_error:
                on_error(message)

        handler = _ScraperFailures()
        loggers = []
        if provider != "adzuna":
            import jobspy  # Create its loggers before attaching the observer.

            loggers = [
                logger
                for name, logger in logging.Logger.manager.loggerDict.copy().items()
                if name.startswith("JobSpy:")
                and name.split(":", 1)[1].lower()
                in {site.lower() for site in platforms}
                and isinstance(logger, logging.Logger)
            ]
        for logger in loggers:
            logger.addHandler(handler)
        try:
            jobs = _fetch_job_vacancies_uncached(
                queries,
                locations,
                platforms,
                collection_limit,
                remote,
                posted_days_old,
                on_progress,
                report if on_error or adaptive_config else None,
                should_cancel,
                **({"on_status": on_status} if on_status else {}),
                **(
                    {
                        "adaptive_config": adaptive_config,
                        "search_filters": search_filters,
                        "seen_postings": seen_postings,
                    }
                    if adaptive_config
                    else {}
                ),
            )
            if constrained and not adaptive_config:
                from backend.search.filters import matches_search_filters

                counts = {}
                eligible = []
                for job in jobs:
                    source = job.get("source_platform", "unknown")
                    if (
                        matches_search_filters(job, search_filters)
                        and counts.get(source, 0) < n_result
                    ):
                        eligible.append(job)
                        counts[source] = counts.get(source, 0) + 1
                jobs = eligible
            if handler.failed:
                messages = handler.messages()
                if not on_error:
                    raise RuntimeError(" ".join(messages))
                for message in messages:
                    report(message)
            return jobs, not errors and not handler.failed
        finally:
            for logger in loggers:
                logger.removeHandler(handler)

    start = time.perf_counter()
    jobs, hit = CollectionCache().collect(
        parameters, fetch, should_cancel, force_refresh
    )
    # Recheck date eligibility now, not only when the cache entry was created.
    jobs = _newest_first(_filter_recent_jobs(jobs, posted_days_old))
    if should_cancel and should_cancel():
        return []
    if hit and on_status:
        on_status(f"Loaded {len(jobs)} postings from the collection cache.")
    if hit and on_progress:
        on_progress(len(jobs))
    logging.getLogger(__name__).info(
        "Job collection cache_hit=%s count=%d elapsed_ms=%.1f",
        hit,
        len(jobs),
        (time.perf_counter() - start) * 1000,
    )
    return jobs


def _fetch_job_vacancies_uncached(
    queries: list[str],
    locations: list[str],
    platforms: list[str],
    n_result: int = 50,
    remote: bool = False,
    posted_days_old: int = 30,
    on_progress=None,
    on_error=None,
    should_cancel=None,
    on_status=None,
    adaptive_config=None,
    search_filters=None,
    seen_postings=None,
):
    """Fetch and normalize jobs using the configured provider."""
    locations = [location.strip() for location in locations if location.strip()] or [
        "Worldwide"
    ]
    provider = os.getenv("JOB_SEARCH_PROVIDER", "jobspy").lower()
    if provider == "adzuna":
        print("Using Adzuna's direct jobs API.")
        return _fetch_adzuna_jobs(
            queries,
            locations,
            n_result,
            remote,
            posted_days_old,
            on_progress,
            on_error,
            should_cancel,
        )

    fetched_jobs = []
    seek_platform_requested = "seek" in [platform.lower() for platform in platforms]
    general_platforms = [
        platform.lower() for platform in platforms if platform.lower() != "seek"
    ]

    print(
        f"Starting scraping for {len(queries)} keywords across {len(locations)} locations..."
    )

    location_groups = _group_apify_locations(locations)

    # Collect general-board results for the requested role and location.
    @stage("jobspy.search")
    def fetch_general(
        query: str,
        location: str,
        site: str,
        country: str,
        limit: int = n_result,
        offset=0,
    ) -> list[dict]:
        from jobspy import scrape_jobs

        if should_cancel and should_cancel():
            return []
        if on_status:
            on_status(f"{site.title()}: collecting job postings…")
        options = {
            "site_name": [site],
            "search_term": query,
            "location": None if _worldwide([location]) else location,
            "country_indeed": country,
            "results_wanted": limit,
            **({"offset": offset} if offset else {}),
            "is_remote": remote,
            # Ask JobSpy to include descriptions in its returned postings.
            # LinkedIn/Glassdoor may perform per-posting requests internally.
            "fetch_description": True,
            "description_format": "markdown",
        }
        # Indeed cannot combine remote and date filters. Local filtering below
        # still applies the requested posting age to its returned jobs.
        if posted_days_old and not (site == "indeed" and remote):
            options["hours_old"] = posted_days_old * 24
        frame = scrape_jobs(**options)
        # Pandas uses NaN/NaT for missing cells; never serialize them as text.
        records = frame.astype(object).where(frame.notna(), None).to_dict("records")
        return [
            {
                "title": _text_value(item, "title", default="Unknown Title"),
                "company": _text_value(item, "company", default="Unknown Company"),
                "location": _text_value(
                    item,
                    "location",
                    default="Worldwide" if _worldwide([location]) else location,
                ),
                "description": _description_value(item),
                "company_logo": _text_value(item, "company_logo"),
                "url": _text_value(
                    item, "job_url_direct", "job_url", default="No URL provided"
                ),
                "source_platform": _text_value(item, "site", default=site),
                "work_type": "remote" if item.get("is_remote") is True else "unknown",
                "collection_country": country,
                "requested_location": location,
                "requested_locations": [location],
                "posted_at": _posted_value(item),
            }
            for item in records[:limit]
        ]

    def fetch_seek(
        query: str, search_location: str, requested_locations: list[str]
    ) -> list[dict]:
        from backend.search.seek import collect

        if on_status:
            on_status("SEEK: collecting postings and descriptions…")
        rows = collect(
            query,
            "" if _worldwide(requested_locations) else search_location,
            limit=n_result,
            days=posted_days_old,
            remote=remote,
            should_cancel=should_cancel,
            on_error=on_error,
        )
        for row in rows:
            row.update(
                requested_location=search_location,
                requested_locations=requested_locations,
            )
        return rows

    if adaptive_config:
        from backend.search import (
            adaptive as rounds,
            jobspy_details,
            board_cooldown,
            seek,
        )
        from backend.search.filters import matches_search_filters, work_arrangement
        from backend.search.history import unseen_postings

        filters = dict(search_filters or {})
        if remote and filters.get("work_type", "any") == "any":
            filters["work_type"] = "remote"
        streams = []
        # Role-first interleaving ensures a small budget doesn't all go to one board.
        for query in dict.fromkeys(queries):
            for board in dict.fromkeys(platforms):
                for location in locations:
                    try:
                        countries = (
                            _jobspy_countries(location, board)
                            if board in {"indeed", "glassdoor"}
                            else ["usa"]
                        )
                    except ValueError:
                        if on_error:
                            on_error(
                                f"{board}: unsupported search location; other sources can continue."
                            )
                            continue
                        raise
                    for country in countries:
                        streams.append(rounds.Stream(board, query, location, country))

        blocked_boards = set()

        def cards(stream, budget):
            if stream.board in blocked_boards:
                stream.active = False
                return []
            if board_cooldown.remaining(stream.board):
                stream.active = False
                if on_error:
                    on_error(board_cooldown.message(stream.board))
                return []
            if stream.board == "seek":

                def failure(message):
                    for item in streams:
                        if item.board == "seek":
                            item.active = False
                    if on_error:
                        on_error(message)

                rows = seek.collect(
                    stream.query,
                    "" if _worldwide([stream.location]) else stream.location,
                    limit=stream.size,
                    days=posted_days_old,
                    remote=remote,
                    should_cancel=budget.stopped,
                    on_error=failure if on_error else None,
                    start_page=stream.offset // 20 + 1,
                    page_limit=1,
                    fetch_description=False,
                )
                for row in rows:
                    row.update(
                        requested_location=stream.location,
                        requested_locations=[stream.location],
                    )
                return rows
            observer = _RateLimitObserver(stream.board)
            logger = logging.getLogger(
                {
                    "linkedin": "JobSpy:LinkedIn",
                    "indeed": "JobSpy:Indeed",
                    "glassdoor": "JobSpy:Glassdoor",
                }[stream.board]
            )
            logger.addHandler(observer)
            try:
                rows = fetch_general(
                    stream.query,
                    stream.location,
                    stream.board,
                    stream.country,
                    stream.size,
                    stream.offset,
                )
                if observer.hit:
                    blocked_boards.add(stream.board)
                    for item in streams:
                        if item.board == stream.board:
                            item.active = False
                return rows
            finally:
                logger.removeHandler(observer)

        def early(job):
            if not _location_matches(job.get("location", ""), locations) or (
                posted_days_old
                and not _is_recent(job.get("posted_at", ""), posted_days_old)
            ):
                return False
            # Unknown work arrangement may need a description; don't reject it yet.
            early_filters = dict(filters)
            if work_arrangement(job) == "unknown":
                early_filters["work_type"] = "any"
            return matches_search_filters(job, early_filters)

        glassdoor = jobspy_details.GlassdoorDetails()

        def fetch_seek_detail(job, budget):
            try:
                html = seek._request(job["url"], budget.stopped)
            except seek.SeekError as exc:
                if "rate-limit" in str(exc):
                    raise jobspy_details.linkedin_details.RateLimited() from None
                raise
            return {"description": seek.description(html) if html else ""}

        def hydrate(rows, budget):
            for board in dict.fromkeys(job["source_platform"] for job in rows):
                selected = [job for job in rows if job["source_platform"] == board]
                fetch = None
                if board == "linkedin":
                    fetch = lambda job: jobspy_details.linkedin_details.fetch_details(
                        jobspy_details.linkedin_details.job_id(job.get("url", ""))
                    )
                elif board == "glassdoor":
                    fetch = glassdoor
                elif board == "seek":
                    fetch = lambda job: fetch_seek_detail(job, budget)
                wrapped = (
                    (lambda job, operation=fetch: budget.fetch_detail(operation, job))
                    if fetch
                    else None
                )

                def detail_error(message):
                    if "429" in message or "rate-limit" in message.lower():
                        blocked_boards.add(board)
                    if on_error:
                        on_error(message)

                jobspy_details.hydrate(
                    board,
                    selected,
                    budget.stopped,
                    allow_network=board not in blocked_boards,
                    fetch=wrapped,
                    on_error=detail_error,
                    on_status=on_status,
                    can_fetch=budget.can_detail,
                )
            return rows

        return rounds.collect(
            streams,
            cards,
            hydrate,
            early,
            lambda job: matches_search_filters(job, filters),
            lambda jobs, previous: unseen_postings(
                jobs, list(seen_postings or []) + previous
            ),
            adaptive_config,
            on_status=on_status,
            on_progress=on_progress,
            on_error=on_error,
            cancelled=should_cancel,
        )

    def fetch_limited_board(searches: list[tuple]) -> list[dict]:
        """Share a single board budget across roles, locations and countries."""
        from backend.search import jobspy_details, board_cooldown

        if not searches:
            return []
        board = searches[0][2]
        if board_cooldown.remaining(board):
            message = board_cooldown.message(board)
            if on_status:
                on_status(message)
            if on_error:
                on_error(message)
                return []
            raise RuntimeError(message)
        budget = n_result * jobspy_details.pool_factor(board)
        limited = _RateLimitObserver(board)
        logger = logging.getLogger(
            {
                "linkedin": "JobSpy:LinkedIn",
                "indeed": "JobSpy:Indeed",
                "glassdoor": "JobSpy:Glassdoor",
            }[board]
        )
        logger.addHandler(limited)
        jobs = []
        try:
            for query, location, site, country in searches:
                remaining = max(0, budget - len(jobs))
                if (
                    not remaining
                    or limited.hit
                    or board_cooldown.remaining(board)
                    or (should_cancel and should_cancel())
                ):
                    break
                try:
                    batch = fetch_general(query, location, site, country, remaining)
                except Exception:
                    if not on_error:
                        raise
                    on_error(
                        "A job-board search failed. Other sources may still return results; retry scraping to try again."
                    )
                    continue
                # Only usable, unique jobs consume the shared budget.
                batch = _filter_requested_locations(batch, locations)
                batch = _filter_recent_jobs(batch, posted_days_old)
                jobs = deduplicate_jobs(jobs + batch)[:budget]
        finally:
            logger.removeHandler(limited)
        if on_status:
            on_status(f"{board.title()}: screening {len(jobs)} job titles…")
        jobs = jobspy_details.screen_by_title(jobs, queries, n_result)
        return jobspy_details.hydrate(
            board,
            jobs,
            should_cancel,
            allow_network=not limited.hit and not board_cooldown.remaining(board),
            on_error=on_error,
            **({"on_status": on_status} if on_status else {}),
        )

    tasks = []
    for site in dict.fromkeys(general_platforms):
        board_searches = []
        for location in ["Worldwide"] if _worldwide(locations) else locations:
            try:
                countries = (
                    _jobspy_countries(location, site)
                    if site in {"indeed", "glassdoor"}
                    else ["usa"]
                )
            except ValueError:
                if on_error:
                    on_error(
                        f"{site} does not support the country for {location}; other boards will continue."
                    )
                    continue
                raise
            board_searches.extend(
                (query, location, site, country)
                for country in countries
                for query in queries
            )
        if site in {"indeed", "glassdoor", "linkedin"}:
            tasks.append((fetch_limited_board, board_searches))
        else:
            tasks.extend((fetch_general, *search) for search in board_searches)
    if seek_platform_requested:
        tasks.extend(
            (fetch_seek, query, search_location, requested_locations)
            for query in queries
            for search_location, requested_locations in location_groups
        )

    # Bound concurrent board requests, including country-specific searches.
    worker_count = min(
        max(
            int(
                os.getenv("JOB_SEARCH_MAX_WORKERS", os.getenv("APIFY_MAX_WORKERS", "4"))
            ),
            1,
        ),
        8,
    )
    with ThreadPoolExecutor(
        max_workers=min(worker_count, max(1, len(tasks)))
    ) as executor:
        futures = [
            submit(executor, function, *arguments) for function, *arguments in tasks
        ]
        for future in as_completed(futures):
            if should_cancel and should_cancel():
                for pending in futures:
                    pending.cancel()
                break
            try:
                fetched_jobs.extend(future.result())
                if on_progress:
                    on_progress(len(deduplicate_jobs(fetched_jobs)))
            except Exception:
                if on_error:
                    on_error(
                        "A job-board search failed. Other sources may still return results; retry scraping to try again."
                    )
                else:
                    raise

    # Apply hard location and date constraints before the vector database is
    # created, so irrelevant jobs never reach semantic matching or Claude.
    fetched_jobs = deduplicate_jobs(fetched_jobs)
    fetched_jobs = _filter_requested_locations(fetched_jobs, locations)
    fetched_jobs = _newest_first(_filter_recent_jobs(fetched_jobs, posted_days_old))
    print(f"{len(fetched_jobs)} Suitable Jobs Retrieved")
    return fetched_jobs


@stage("jobs.embed_index")
def vectorize_jobs_to_db(
    jobs: list,
    persist_dir: str = "./vector_db",
    shared: bool = False,
    should_cancel=None,
):
    """Embed each job description and store the job documents in ChromaDB."""
    from langchain_chroma import Chroma
    from langchain_core.documents import Document
    from langchain_openai import OpenAIEmbeddings

    documents = []

    for job in jobs:
        # Keep full evidence in metadata, outside the embedded document text.
        original_content = (
            f"Job Title: {job['title']}\n"
            f"Company: {job['company']}\n"
            f"Location: {job['location']}\n"
            f"Description: {job['description']}"
        )

        # Keep identifying metadata so matching results can be traced back to
        # the original job posting.
        metadata = {
            "original_content": original_content,
            "company_logo": job.get("company_logo") or "",
            "job_description": job.get("description") or "",
            "embedding_text_version": "focused-v1",
            "title": job["title"] or "Unknown Title",
            "company": job["company"] or "Unknown Company",
            "location": job["location"] or "Unknown Location",
            "url": job["url"] or "No URL provided",
            "source": job["source_platform"],
            "requested_location": job.get("requested_location", job["location"]),
            "posted_at": job.get("posted_at", ""),
            # A career-pivot note is informational only; it helps Claude
            # distinguish a review candidate from an automatic exclusion.
            "pre_screen_note": job.get("pre_screen_note", ""),
        }

        doc = Document(page_content=job_embedding_text(job), metadata=metadata)
        documents.append(doc)

    # Convert all job documents into vectors and persist them for Phase 3.
    embeddings = CachedJobEmbeddings(
        OpenAIEmbeddings(model="text-embedding-3-small"),
        os.getenv("JOB_EMBEDDING_CACHE_DIR", str(JOB_EMBEDDING_CACHE_DIR)),
    )

    if shared:
        from backend.search.shared_index import publish

        return publish(documents, persist_dir, embeddings, should_cancel)

    vector = Chroma.from_documents(
        documents=documents, embedding=embeddings, persist_directory=persist_dir
    )

    print(
        f"{len(documents)} jobs are vectorized and succesfully stored in {persist_dir}"
    )
    return vector
