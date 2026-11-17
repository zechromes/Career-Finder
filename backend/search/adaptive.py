"""Bounded staged collection; yield is coverage, never a prediction of job fit."""

from backend.observability import stage, collection_batch, collection_step, mark
from backend.search import ingestion_log
from dataclasses import dataclass
import math
import os
import time


def _setting(name, default, maximum):
    try:
        return min(maximum, max(1, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


def settings():
    return {
        "batches": _setting("JOB_COLLECTION_MAX_BATCHES", 12, 100),
        "details": _setting("JOB_COLLECTION_MAX_DETAILS", 60, 500),
        "candidates": _setting("JOB_COLLECTION_MAX_CANDIDATES", 150, 1000),
        "seconds": _setting("JOB_COLLECTION_MAX_SECONDS", 240, 900),
    }


@dataclass
class Stream:
    board: str
    query: str
    location: str
    country: str = "usa"
    offset: int = 0
    calls: int = 0
    raw: int = 0
    useful: int = 0
    active: bool = True
    last_page: tuple = ()

    @property
    def size(self):
        # Align offset-based boards to their native search-page boundaries.
        # Adzuna's largest page (50) gets the most jobs per limited free-tier call.
        return {
            "linkedin": 10,
            "seek": 20,
            "google": 10,
            "adzuna": 50,
        }.get(self.board, 20)


class Budget:
    def __init__(self, config, cancelled=None, clock=time.monotonic):
        self.config = config
        self.cancelled = cancelled or (lambda: False)
        self.clock = clock
        self.deadline = clock() + config["seconds"]
        self.batches = self.details = 0
        # Set once search rounds end: descriptions of collected cards are then read
        # without the time or fetch limits; only cancellation stops them.
        self.finishing = False

    def stopped(self):
        return self.cancelled() or (
            not self.finishing and self.clock() >= self.deadline
        )

    def can_detail(self):
        return not self.stopped() and (
            self.finishing or self.details < self.config["details"]
        )

    def fetch_detail(self, operation, job):
        # The collector is sequential; each admitted fetch consumes one slot.
        self.details += 1
        return operation(job)


@stage("jobs.select_descriptions")
def select_details(jobs, queries, limit):
    """Reserve a quarter for board-order exploration outside title-ranked picks."""
    from backend.search.jobspy_details import screen_by_title

    if len(jobs) <= limit:
        return list(jobs)
    explore = max(1, math.ceil(limit / 4))
    ranked = screen_by_title(jobs, queries, limit - explore)
    identities = {id(job) for job in ranked}
    return ranked + [job for job in jobs if id(job) not in identities][:explore]


@stage("jobs.adaptive_collection")
def collect(
    streams,
    fetch_cards,
    hydrate,
    early,
    final,
    unique,
    config,
    *,
    on_status=None,
    on_progress=None,
    on_error=None,
    cancelled=None,
    clock=time.monotonic,
):
    budget = Budget(config, cancelled, clock)
    results, seen, pending = [], [], []
    # First occurrence of every board/role pair comes before additional locations.
    occurrences = {}
    ordered = []
    for index, stream in enumerate(streams):
        key = (stream.board, stream.query)
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        ordered.append((occurrence, index, stream))
    unvisited = [row[2] for row in sorted(ordered, key=lambda row: row[:2])]
    initial_slice = max(
        1, config["details"] // max(1, min(len(occurrences), config["batches"]))
    )

    def status(text):
        if on_status and not budget.cancelled():
            on_status(text)

    def enrich(rows):
        nonlocal results
        if not rows:
            return
        if budget.stopped():
            pending.extend(rows)
            return
        hydrated = hydrate(rows, budget)
        with collection_step("filter_descriptions") as trace:
            accepted = []
            for job in hydrated:
                if not job.get("description"):
                    if budget.can_detail():
                        ingestion_log.drop(job, "description", "no usable description")
                    else:
                        # Skipped for a round limit; read it at the checkpoint.
                        pending.append(job)
                elif final(job):
                    accepted.append(job)
            if trace is not None:
                trace["result_count"] = len(accepted)
        with collection_step("merge_unique_results") as trace:
            merged = unique(results + accepted, [])
            for job in merged[config["candidates"] :]:
                ingestion_log.drop(job, "budget", "over the candidate limit")
            results = merged[: config["candidates"]]
            if trace is not None:
                trace["result_count"] = len(results)
        if on_progress:
            on_progress(len(results))

    def waiting():
        # Cards that still need a fetched description (inline or cached text needs none).
        return sum(not job.get("description") for job in pending)

    def budget_filled():
        return waiting() >= config["details"] - budget.details

    # After every combination's first page, stop searching once waiting cards would
    # use the remaining fetch budget, so each collected card is read at the checkpoint.
    while (
        budget.batches < config["batches"]
        and not budget.stopped()
        and len(results) < config["candidates"]
        and (unvisited or not budget_filled())
    ):
        if unvisited:
            stream = unvisited.pop(0)
        else:
            available = [stream for stream in streams if stream.active]
            if not available:
                break
            stream = max(
                available,
                key=lambda item: ((item.useful + 1) / (item.raw + 2), -item.calls),
            )
        if not stream.active:
            continue
        with collection_batch(
            stream.board, budget.batches + 1, stream.offset
        ) as batch_trace:
            status(
                f"Collection round {budget.batches + 1}/{config['batches']}: {stream.board} — collecting another batch."
            )
            budget.batches += 1
            stream.calls += 1
            try:
                rows = fetch_cards(stream, budget)
            except Exception:
                mark("partial")
                stream.active = False
                if on_error:
                    on_error(
                        f"{stream.board}: collection failed. Other sources can continue; results may be incomplete."
                    )
                else:
                    raise
                continue
            signature = tuple(
                job.get("url")
                or (
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                )
                for job in rows
            )
            if signature and signature == stream.last_page:
                stream.active = False
                continue
            stream.last_page = signature
            raw_count = len(rows)
            ingestion_log.collected(stream.board, raw_count)
            stream.raw += raw_count
            stream.offset += stream.size
            if raw_count < stream.size:
                stream.active = False
            with collection_step("filter_cards") as trace:
                eligible = [job for job in rows if early(job)]
                if trace is not None:
                    trace["result_count"] = len(eligible)
            with collection_step("deduplicate_incoming") as trace:
                fresh = unique(eligible, seen)
                if trace is not None:
                    trace["result_count"] = len(fresh)
            seen.extend(fresh)
            # Stop fully filtered pages; history-only duplicates can advance to new pages.
            if rows and not eligible:
                stream.active = False
            selected = select_details(
                fresh,
                [stream.query],
                min(
                    10,
                    initial_slice if stream.calls == 1 else 10,
                    config["candidates"] - len(results),
                ),
            )
            selected_ids = {id(job) for job in selected}
            pending.extend(job for job in fresh if id(job) not in selected_ids)
            before = len(results)
            enrich(selected)
            stream.useful += len(results) - before
            if batch_trace is not None:
                batch_trace["result_count"] = len(results) - before
    # Checkpoint: card collection is over; read every remaining description.
    budget.finishing = True
    if pending and not budget.cancelled():
        status(
            f"Job search finished; reading descriptions for {len(pending)} collected postings…"
        )
    deferred_round = 1
    while pending and not budget.stopped() and len(results) < config["candidates"]:
        with collection_batch("mixed", deferred_round, deferred=True) as batch_trace:
            before = len(results)
            selected = select_details(
                pending,
                [stream.query for stream in streams],
                min(10, config["candidates"] - len(results)),
            )
            chosen = {id(job) for job in selected}
            pending = [job for job in pending if id(job) not in chosen]
            enrich(selected)
            if batch_trace is not None:
                batch_trace["result_count"] = len(results) - before
        deferred_round += 1
    if budget.cancelled():
        return []
    for job in pending:
        ingestion_log.drop(job, "budget", "not processed before the collection limit")
    coverage = sum(stream.calls > 0 for stream in streams)
    reason = (
        "time budget reached"
        if budget.clock() >= budget.deadline
        else "description budget filled"
        if budget.details >= config["details"]
        else "collection finished"
    )
    status(
        f"Adaptive {reason}: {len(results)} eligible postings; {budget.batches}/{config['batches']} search batches, {budget.details} new description fetches; {coverage}/{len(streams)} search combinations visited. Find more jobs can expand the pool."
    )
    return results
