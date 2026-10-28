# Job search providers

Install the backend dependencies with `python -m pip install -r backend/requirements.txt` in the environment that runs the API, then restart the backend.

`JOB_SEARCH_PROVIDER=jobspy` is the default. LinkedIn, Indeed and Glassdoor use `python-jobspy` directly. Existing `auto` and `apify` settings also use JobSpy for these boards. They do not require an Apify key. Explicit `JOB_SEARCH_PROVIDER=adzuna` retains the alternate Adzuna path.

SEEK now uses a direct Australian search/detail collector in `backend/search/seek.py`.
It follows the search endpoint approach documented by
[SeekSpider](https://github.com/qinscode/SeekSpider), with independently written
parsing and full-description extraction. It does not import SeekSpider or require
PostgreSQL, Supabase, Scrapy, Apify credentials, or extra AI calls. No upstream code
was vendored because a reusable license was not verified.

Searches use keywords and location on `au.seek.com`, followed by detail-page requests.
HTTPS redirects between `www.seek.com.au` and `au.seek.com` are supported; other
hosts, credentials in URLs, and nonstandard ports are rejected before following. An empty
location searches SEEK Australia, not worldwide SEEK markets. Each query/location
is bounded to 20 pages and the requested result limit. Requests are serialized
across searches with at least one second between completed requests, a 30-second
timeout and a 5 MiB response cap. HTTP 403/429 starts a shared cooldown; there is
no automatic proxy fallback or challenge bypass. Cancellation stops subsequent
requests; an in-flight request can finish. Missing full descriptions or changed
response formats produce a visible error; partial results are retained and not
cached as complete. Existing location/date filters and collection caching apply.

The search endpoint is undocumented by SEEK and may change or block access.
Mocked tests establish integration behavior, not current live availability or
speed. SEEK's [terms](https://au.seek.com/terms/en) require prior written consent
for automated scraping. The old Apify collector is no longer called.

Each JobSpy request searches one role, location and board. Results are normalized,
deduplicated and filtered by location/date before title screening. Missing cells
become empty fields rather than the text `nan`.

## Adaptive web collection

Web searches use `adaptive=True` with one combined budget across boards, roles
and locations. The user still enters ordinary locations and shortlist preferences.

JobSpy requests use `fetch_description=True`: returned postings include descriptions
when available. LinkedIn/Glassdoor can fetch each description internally before
application filtering. Missing descriptions still use the existing cache/fallback
path. SEEK retains its separate staged collector.

1. Visit each board/role combination before expanding visited combinations, when
   the batch/time budget permits. Additional locations/country indexes follow
   those first combinations. Native batch sizes are LinkedIn 10, Indeed 20,
   Glassdoor 30 and SEEK 20. No board gets a fixed 50-posting quota.
2. Apply location, age, exclusions and available work-type/seniority evidence,
   then deduplicate against this search and previously collected jobs. Unknown
   work arrangement waits for the description before the final filter.
3. Select small description batches, prioritizing title overlap while reserving
   approximately 25% (rounded up) for board-order exploration outside those picks.
   Reuse inline text and cached descriptions before fetching missing details.
   Indeed supplies inline text; it has no separate detail endpoint here.
4. After initial coverage, prefer streams with a higher yield of eligible unique
   postings. Exhausted, repeated-page, fully filtered and failed streams stop.
   Previously seen full pages can advance so **Find more jobs** can reach new jobs.
   Remaining collected cards use spare description capacity before collection ends.
5. Rank the resulting pool with the existing semantic/BM25 retrieval and then
   evaluate the shortlist. Eligibility yield is not a prediction of candidate fit.

| Setting | Default | Maximum |
| --- | ---: | ---: |
| `JOB_COLLECTION_MAX_BATCHES` | 12 | 100 |
| `JOB_COLLECTION_MAX_DETAILS` | 60 | 500 |
| `JOB_COLLECTION_MAX_CANDIDATES` | 150 | 1000 |
| `JOB_COLLECTION_MAX_SECONDS` | 120 | 900 |

Settings are positive integers; invalid values use defaults. The time limit is
soft: in-flight calls can finish afterward. Batch and detail counts bound collector
operations, **not raw HTTP requests**: JobSpy may paginate/retry internally and
Glassdoor may need session setup. Indeed offsets can refetch earlier pages, so
adaptive paging does not guarantee faster collection for that board. Collection
is sequential; legacy worker settings do not apply to adaptive web searches.

Description limits count application fallback fetch attempts, not JobSpy-internal
description requests. Inline/cache hits do not consume
those slots. Rows without usable descriptions are excluded from the adaptive
retrieval pool. Source errors retain usable partial results and prevent collection
cache writes. Cancellation stops subsequent work. Rate-limited JobSpy boards stop for the current collection only;
a new manual search can retry immediately. No automatic retry is scheduled.

Budgets can leave roles, locations and countries unvisited. Title exploration
reduces dependence on exact title wording but does not establish recall. No
human-labeled dataset or live speed comparison is available; accuracy and latency
improvements are unverified. A bounded successful pool may be cached even when
budgets end collection; “complete” does not mean every matching vacancy was found.

Direct Python/CLI callers retain fixed collection unless they opt into
`adaptive=True`. Their `JOBSPY_SCREEN_POOL_FACTOR` (default 3, range 1–5;
LinkedIn fallback `LINKEDIN_SCREEN_POOL_FACTOR`) and explicit-filter allowance
remain supported. Adzuna retains its existing collection path.

LinkedIn's existing `.cache/linkedin_descriptions/` and settings remain supported.
Indeed/Glassdoor/SEEK public text uses `.cache/job_descriptions/`, keyed by board and
posting URL. `JOBSPY_DESCRIPTION_CACHE_DIR` overrides that directory;
`JOBSPY_DESCRIPTION_CACHE_TTL_SECONDS` defaults to seven days (0 disables reuse
and writes). Expired descriptions are removed when read. Reusing descriptions
preserves their original timestamp for collection freshness. These caches do not
verify that vacancies remain open. An HTTP 429 stops additional requests to that board in the
current collection. New manual searches can retry immediately. Existing results
retain their historical warning; SEEK and Adzuna retain separate collectors.

Empty locations mean worldwide: LinkedIn receives no location filter, and Indeed/Glassdoor search their supported country indexes. Country coverage therefore depends on the board. Worldwide searches can take longer because they issue multiple country requests. In legacy fixed collection, `JOB_SEARCH_MAX_WORKERS` limits concurrent requests (default 4, maximum 8); the legacy `APIFY_MAX_WORKERS` setting is accepted as a fallback.

For specific places, include the country in the location label for reliable Indeed/Glassdoor country selection. City-only inputs use the existing country inference, defaulting to Australia when unrecognized. Remote Indeed searches apply the date limit locally because JobSpy does not support combining those two filters for Indeed.

JobSpy documentation: https://github.com/speedyapply/JobSpy

For legacy fixed collection, Indeed and Glassdoor each share one result budget across all requested roles,
locations and country indexes (`n_result`, default 50 jobs per board). Searches
stop when that board's budget is filled. Duplicate or filtered-out jobs do not
consume the budget, and oversized provider responses are capped. Worldwide
searches visit country indexes in order until the budget is filled; they do not
promise coverage of every country within that limit. Fewer jobs may be returned
when sources have insufficient matching results or requests fail.

Successful, non-empty identical searches are reused for 15 minutes by default.
The cache key includes provider, ordered roles/locations/boards, remote setting,
posting-age limit and collection budget. Explicit **Find more jobs** bypasses it.
Failures, empty results, cancellation and detected JobSpy error logs are not cached.
See [cache behavior and benchmark](collection-caching.md).

Greenhouse and Lever collection has been removed. Supported source options are
LinkedIn, Indeed, Glassdoor and SEEK. Older saved preferences discard retired
feed selections; users with no remaining board must select one before searching.
Shared posting indexing and collection caching remain enabled.

## General location input

The input remains unchanged: users can enter a city, state or country. Collection
and retrieval now share `backend/search/locations.py` instead of using separate
first-word filters. State/country aliases and punctuation are normalized locally,
with a bounded normalization cache and no geocoding requests or extra credentials.
Original posting labels remain unchanged for display and evaluation.

Broad Australian capital-city searches include a curated set of known metro
locations: Sydney includes Parramatta, Chatswood, North Sydney and Sydney Olympic
Park; Melbourne includes Clayton, Dandenong, Docklands and Southbank; Brisbane
includes Fortitude Valley and South Brisbane; Perth includes Fremantle and
Joondalup; Adelaide includes Port Adelaide. This is an initial lookup, not complete
suburb coverage or an implementation of geographic boundary polygons. The
[ABS metro-area definition](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/main-structure-and-greater-capital-city-statistical-areas/greater-capital-city-statistical-areas)
explains why a metro search can include locations outside the central city.

Specific suburb inputs stay specific. Explicit state/country conflicts reject a
match; multiword places must match completely rather than sharing a first word.
Remote-country restrictions are respected when supplied in the location field;
remote eligibility is not inferred from an unqualified label. Unknown locations
remain excluded from constrained searches and the log now describes unmatched
or unknown locations rather than asserting all exclusions are outside the area.
Unsupported places use complete-phrase matching. No worldwide geocoding coverage
or suitable-job recall improvement is claimed; human labels are unavailable.

A collection-policy version change invalidates old exact-search cache hits so
previously filtered pools are recollected. Saved results are not rewritten.

SEEK descriptions preserve source headings, paragraph breaks, bullets and numbered
lists as safe display text, including the JSON-LD fallback. Inline text stays in
its sentence; script/style content is discarded. Existing saved descriptions
cannot recover discarded HTML structure automatically. New collections use the
formatter; the collection cache policy is bumped to avoid older flattened entries.

## Frontend progress

The Find opportunities timeline displays a loading bar with status text below it.
Collection/matching use an indeterminate activity bar because their total work is
unknown. JobSpy status updates name the board, title screening and description
loading (checked, ready and cached counts); updates are emitted at start, every
five descriptions and completion. Concurrent boards may alternate status messages.
SEEK reports collection/detail activity without a fabricated percentage. Evaluation
uses the actual completed-job/total count. Finished, cancelled and failed runs stop
the loading animation. Reduced-motion preferences and accessible progress labels
are supported. This uses the existing run `message` field, polling and events.


### Rate-limit warnings

A collection reports one rate-limit cause per board. Missing-description warnings
caused by that same pause are suppressed; cached descriptions remain usable.
Cooldown messages describe the state at search time, not a live countdown.
Completed results retain their warning because their coverage was incomplete;
a new search clears run warnings and can retry immediately. Existing saved
warnings are historical records and are not rewritten. LinkedIn may reject
subsequent requests with another 429.


### Cooldown removal (2026-10-20)

LinkedIn, Indeed and Glassdoor no longer have a local timed cooldown between
searches. Manual retry can start immediately. A 429 still stops additional
requests to that board within the same collection; other boards and cached text
can continue. The previous `JOBSPY_RATE_LIMIT_COOLDOWN_SECONDS` setting is ignored.
SEEK's separate collector pacing/backoff is unchanged. No automatic retry is added.
