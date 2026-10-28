"""Direct SEEK AU collector using the search/detail approach documented by SeekSpider.

Independent implementation; no upstream code, database or AI pipeline is imported.
"""

from backend.observability import stage
import json
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from bs4 import BeautifulSoup

_LOCK = threading.Lock()
_NEXT_REQUEST = 0.0
_COOLDOWN = 0.0


class SeekError(RuntimeError):
    pass


def _supported_url(url):
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in {"www.seek.com.au", "au.seek.com"}
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


class _SeekRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _supported_url(newurl):
            raise SeekError("SEEK redirected to an unsupported page.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def urlopen(request, timeout):
    return build_opener(_SeekRedirectHandler()).open(request, timeout=timeout)


def _request(url, cancelled):
    global _NEXT_REQUEST, _COOLDOWN
    if not _supported_url(url):
        raise SeekError("SEEK redirected to an unsupported page.")
    while not _LOCK.acquire(timeout=0.1):
        if cancelled():
            return None
    try:
        if time.monotonic() < _COOLDOWN:
            raise SeekError("SEEK is temporarily rate-limited. Retry later.")
        while time.monotonic() < _NEXT_REQUEST:
            if cancelled():
                return None
            time.sleep(0.1)
        if cancelled():
            return None
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "CareerTracker/1.0",
                    "Accept": "application/json,text/html",
                },
            )
            with urlopen(request, timeout=30) as response:
                if not _supported_url(response.url):
                    raise SeekError("SEEK redirected to an unsupported page.")
                payload = response.read(5 * 1024 * 1024 + 1)
                if len(payload) > 5 * 1024 * 1024:
                    raise SeekError("SEEK response exceeded the supported size.")
                return payload.decode("utf-8")
        except HTTPError as exc:
            if exc.code in (403, 429):
                try:
                    delay = float(exc.headers.get("Retry-After", "300"))
                except (ValueError, TypeError, AttributeError):
                    delay = 300
                _COOLDOWN = time.monotonic() + min(86400, max(60, delay))
                raise SeekError(
                    "SEEK blocked or rate-limited the request. Retry later."
                ) from None
            raise SeekError("SEEK request failed. Retry later.") from None
        except SeekError:
            raise
        except Exception:
            raise SeekError(
                "SEEK could not be reached or returned an unreadable response."
            ) from None
        finally:
            _NEXT_REQUEST = time.monotonic() + 1
    finally:
        _LOCK.release()


def formatted_description(element):
    """Preserve source block structure as safe text understood by JobDescription."""
    from bs4 import NavigableString

    def render(node):
        if isinstance(node, NavigableString):
            return re.sub(r"\s+", " ", str(node))
        if node.name in {"script", "style", "noscript"}:
            return ""
        if node.name == "br":
            return "\n"
        if node.name in {"ul", "ol"}:
            lines = []
            try:
                start = int(node.get("start", 1))
            except (TypeError, ValueError):
                start = 1
            for index, child in enumerate(node.find_all("li", recursive=False)):
                content = "".join(render(part) for part in child.children).strip()
                prefix = f"{start + index}. " if node.name == "ol" else "- "
                lines.append(prefix + content)
            return "\n\n" + "\n".join(lines) + "\n\n"
        content = "".join(render(child) for child in node.children)
        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return "\n\n## " + re.sub(r"\s+", " ", content).strip() + "\n\n"
        if node.name in {"p", "div", "section", "article"}:
            # SEEK often represents section headings as a bold-only paragraph.
            bold = node.find(["strong", "b"], recursive=False)
            if bold and node.get_text(strip=True) == bold.get_text(strip=True):
                return "\n\n## " + content.strip() + "\n\n"
            return "\n\n" + content.strip() + "\n\n"
        return content

    text = render(element)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def description(html):
    soup = BeautifulSoup(html, "html.parser")
    element = soup.select_one('[data-automation="jobAdDetails"]')
    if element:
        return formatted_description(element)
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        queue = data if isinstance(data, list) else [data]
        for item in queue:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("@graph"), list):
                queue.extend(item["@graph"])
            if item.get("@type") == "JobPosting" and isinstance(
                item.get("description"), str
            ):
                return formatted_description(
                    BeautifulSoup(item["description"], "html.parser")
                )
    return ""


@stage("seek.collect")
def collect(
    query,
    location,
    limit=50,
    days=30,
    remote=False,
    should_cancel=None,
    on_error=None,
    *,
    start_page=1,
    page_limit=20,
    fetch_description=True,
):
    cancelled = should_cancel or (lambda: False)
    jobs, seen = [], set()
    try:
        for page in range(start_page, min(21, start_page + page_limit)):
            if cancelled() or len(jobs) >= limit:
                break
            params = {
                "siteKey": "AU-Main",
                "sourcesystem": "houston",
                "keywords": query,
                "where": location,
                "page": page,
                "pageSize": 20,
                "locale": "en-AU",
            }
            if days:
                params["daterange"] = days
            raw = _request(
                "https://au.seek.com/api/jobsearch/v5/search?" + urlencode(params),
                cancelled,
            )
            if raw is None or cancelled():
                break
            try:
                data = json.loads(raw)
                rows = data["data"]
                if not isinstance(rows, list):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise SeekError(
                    "SEEK search response changed or access was blocked."
                ) from None
            if not rows:
                break
            new_ids = 0
            for row in rows:
                if cancelled() or len(jobs) >= limit:
                    break
                job_id = str(row.get("id", ""))
                if not job_id.isdigit() or job_id in seen:
                    continue
                seen.add(job_id)
                new_ids += 1
                url = "https://au.seek.com/job/" + job_id
                text = ""
                if fetch_description:
                    html = _request(url, cancelled)
                    if html is None or cancelled():
                        break
                    text = description(html)
                    if not text:
                        raise SeekError(
                            "SEEK job descriptions were unavailable. Results may be incomplete."
                        )
                places = row.get("locations") or []
                place = ", ".join(
                    p.get("label", "") for p in places if isinstance(p, dict)
                )
                if (
                    fetch_description
                    and remote
                    and "remote" not in (place + " " + text).lower()
                ):
                    continue
                jobs.append(
                    {
                        "title": row.get("title") or "Unknown Title",
                        "company": (row.get("advertiser") or {}).get("description")
                        or "Unknown Company",
                        "location": place,
                        "description": text,
                        "url": url,
                        "source_platform": "seek",
                        "posted_at": row.get("listingDate") or "",
                        "company_logo": "",
                    }
                )
            if not new_ids:
                break
            total = data.get("totalCount")
            if isinstance(total, int) and len(seen) >= total:
                break
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, SeekError)
            else "SEEK returned an unsupported response. Results may be incomplete."
        )
        if on_error:
            on_error(message)
        else:
            raise SeekError(message) from None
    return jobs
