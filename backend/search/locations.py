"""Shared deterministic location matching; original labels remain untouched.

Curated AU metro examples, not exhaustive geographic boundaries or geocoding.
"""

import re
import unicodedata
from functools import lru_cache

ALIASES = {
    "new south wales": "nsw",
    "victoria": "vic",
    "queensland": "qld",
    "western australia": "wa",
    "south australia": "sa",
    "tasmania": "tas",
    "northern territory": "nt",
    "australian capital territory": "act",
    "united states of america": "usa",
    "united states": "usa",
    "united kingdom": "uk",
    "new zealand": "nz",
    "australia": "au",
}
STATES = {"nsw", "vic", "qld", "wa", "sa", "tas", "nt", "act"}
COUNTRIES = {
    "au",
    "usa",
    "uk",
    "nz",
    "canada",
    "india",
    "singapore",
    "japan",
    "germany",
    "france",
}
# Conservative known metro relationships; specific suburb requests stay specific.
METROS = {
    "sydney": (
        "nsw",
        ("parramatta", "chatswood", "north sydney", "sydney olympic park"),
    ),
    "melbourne": ("vic", ("clayton", "dandenong", "docklands", "southbank")),
    "brisbane": ("qld", ("fortitude valley", "south brisbane")),
    "perth": ("wa", ("fremantle", "joondalup")),
    "adelaide": ("sa", ("port adelaide",)),
    "hobart": ("tas", ()),
    "darwin": ("nt", ()),
    "canberra": ("act", ()),
}


def contains(text, phrase):
    return f" {phrase} " in f" {text} "


@lru_cache(maxsize=4096)
def normalize(value):
    value = "".join(
        c
        for c in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(c)
    )
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    for alias, canonical in sorted(ALIASES.items(), key=lambda pair: -len(pair[0])):
        value = re.sub(r"\b" + re.escape(alias) + r"\b", canonical, value)
    return value


def geography(text):
    words = set(text.split())
    states = words & STATES
    countries = words & COUNTRIES
    metros = set()
    for city, (state, suburbs) in METROS.items():
        if contains(text, city) or any(contains(text, suburb) for suburb in suburbs):
            # Explicit foreign country/state takes precedence over an AU place-name inference.
            if (not countries or countries == {"au"}) and (
                not states or state in states
            ):
                metros.add(city)
                states.add(state)
    if states and not countries:
        countries.add("au")
    return countries, states, metros


def location_matches(job_location, requested_locations):
    if not any(str(x).strip() for x in requested_locations) or any(
        normalize(x) == "worldwide" for x in requested_locations
    ):
        return True
    actual = normalize(job_location or "")
    if actual in {"", "unknown", "unknown location", "not specified", "n a"}:
        return False
    ac, ast, am = geography(actual)
    for label in requested_locations:
        request = normalize(label)
        if not request:
            continue
        rc, rst, _ = geography(request)
        if rc and ac and rc.isdisjoint(ac):
            continue
        if rst and ast and rst.isdisjoint(ast):
            continue
        words = request.split()
        remote = "remote" in words
        # Remove geographic qualifiers, not arbitrary words from multiword cities.
        place = " ".join(
            w
            for w in words
            if w
            not in COUNTRIES
            | STATES
            | {"remote", "greater", "all", "area", "region", "metropolitan"}
            and not w.isdigit()
        )
        if remote and not contains(actual, "remote"):
            continue
        if place in METROS:
            if place in am:
                return True
        elif place:
            if contains(actual, place):
                return True
        elif rst:
            if bool(rst & ast):
                return True
        elif rc:
            if bool(rc & ac):
                return True
        elif remote:
            return True
    return False
