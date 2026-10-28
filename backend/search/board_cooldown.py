"""Compatibility helpers: local timed JobSpy cooldowns have been removed."""

# Retained for older integrations; no cross-search timer is stored or enforced.
_UNTIL = {}


def remaining(board):
    return 0


def mark_limited(board):
    pass


def message(board):
    return f"{board.title()} rate-limited this search. Results may be incomplete; you can retry manually."
