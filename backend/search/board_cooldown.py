"""Compatibility helpers: local timed JobSpy cooldowns have been removed."""

import re

# Retained for older integrations; no cross-search timer is stored or enforced.
_UNTIL = {}


def remaining(board):
    return 0


def mark_limited(board):
    pass


class RateLimitNotice(str):
    """A board message created where an HTTP 429 was confirmed; checked by type, not wording."""


def message(board):
    return RateLimitNotice(
        f"{board.title()} rate-limited this search. Results may be incomplete; you can retry manually."
    )


def busy_note(message):
    """A calm page note for a rate-limited board; the user has nothing to fix."""
    name = next(
        (
            board
            for board in ("LinkedIn", "Indeed", "Glassdoor", "SEEK")
            if str(message).lower().startswith(board.lower())
        ),
        "A job board",
    )
    return f"{name} limited how many jobs could be loaded this time, so you may see fewer jobs from it. Nothing needs to change on your side."


def is_rate_limit(message):
    """Job-board rate limits are expected and retried; they are not shown as failures."""
    return isinstance(message, RateLimitNotice)


# Older saved runs hold plain text, so match only the wording this app wrote for a 429.
_SAVED_RATE_LIMIT = re.compile(
    r"\(HTTP 429\)|rate-limited this search|SEEK is temporarily rate-limited"
)


def saved_rate_limit(text):
    return bool(_SAVED_RATE_LIMIT.search(str(text)))
