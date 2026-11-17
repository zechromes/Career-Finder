"""Provider pacing and safe failure reporting for job evaluations."""

import re
import threading
import time


# Carry a safe failure category and retry metadata without raw provider payloads.
class EvaluationFailure(Exception):
    def __init__(self, category, message, *, retry_after=0, skipped=False):
        super().__init__(message)
        self.category = category
        self.retry_after = retry_after
        self.skipped = skipped


def classify_failure(exc):
    """Inspect chained SDK errors without persisting prompts or credentials."""
    if isinstance(exc, EvaluationFailure):
        return exc
    chain = []
    current = exc
    while current is not None and len(chain) < 5:
        chain.append(current)
        current = current.__cause__ or current.__context__
    text = " ".join(type(item).__name__ + " " + str(item) for item in chain).lower()
    statuses = {
        str(getattr(item, "status_code", getattr(item, "code", ""))) for item in chain
    }
    if "429" in statuses or "ratelimit" in text or "resource_exhausted" in text:
        if any(
            term in text
            for term in [
                "perday",
                "per day",
                "daily quota",
                "limit: 0",
                "insufficient_quota",
                "spending cap",
                "spend cap",
            ]
        ):
            return EvaluationFailure(
                "quota",
                "Provider quota is exhausted. Check account usage, billing and daily limits before retrying.",
            )
        delay = re.search(
            r"(?:retry in\s+|retrydelay[\s\x27\x22:]+)(\d+(?:\.\d+)?)s", text
        )
        retry_after = float(delay.group(1)) if delay else 60.0
        for item in chain:
            headers = getattr(getattr(item, "response", None), "headers", {}) or {}
            try:
                retry_after = max(retry_after, float(headers.get("retry-after", 0)))
            except (TypeError, ValueError):
                pass
        return EvaluationFailure(
            "rate_limit",
            "Provider rate limit reached. Reduce requests per minute or check the project quota.",
            retry_after=retry_after,
        )
    if statuses & {"401", "403"} or any(
        term in text
        for term in ["authentication", "permissiondenied", "api_key_invalid"]
    ):
        return EvaluationFailure(
            "credentials",
            "Provider credentials or model access were rejected. Check the configured API key and permissions.",
        )
    if "404" in statuses or "modelnotfound" in text:
        return EvaluationFailure(
            "model", "The configured evaluation model is unavailable for this account."
        )
    if "schema is too complex" in text:
        return EvaluationFailure(
            "request",
            "Provider rejected the structured-output schema as too complex. Restart the backend with the schema compatibility fix, then retry failed evaluations.",
        )
    if "400" in statuses or "invalidrequest" in text:
        return EvaluationFailure(
            "request",
            "Provider rejected the request configuration or schema. Check model compatibility.",
        )
    if isinstance(exc, TimeoutError) or "timeout" in text or "deadline" in text:
        return EvaluationFailure("timeout", "The evaluation request timed out.")
    if any(
        term in text
        for term in ["validationerror", "parserexception", "structuredoutput"]
    ):
        return EvaluationFailure(
            "invalid_output", "The model did not return a valid structured assessment."
        )
    return EvaluationFailure(
        "provider_error",
        "The provider request failed. Check connectivity and provider availability.",
    )


def retry_invalid_assessment(operation):
    """Retry one malformed assessment, never a whole batch or another provider."""
    for attempt in range(2):
        try:
            return operation()
        except Exception as exc:
            if attempt or classify_failure(exc).category != "invalid_output":
                raise


class RequestPacer:
    """Share spacing and cooldown across workers and concurrent app runs."""

    def __init__(self, requests_per_minute, clock=time.monotonic, sleep=time.sleep):
        self.interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self.clock = clock
        self.sleep = sleep
        self.next_start = 0.0
        self.lock = threading.Lock()

    # Wait in short intervals so blocked batches can stop before starting a request.
    def wait(self, check_blocked):
        while True:
            check_blocked()
            with self.lock:
                now = self.clock()
                remaining = self.next_start - now
                if remaining <= 0:
                    self.next_start = now + self.interval
                    return
            self.sleep(min(remaining, 1.0))

    # Extend the shared cooldown without shortening an existing delay.
    def cool_down(self, seconds):
        with self.lock:
            self.next_start = max(self.next_start, self.clock() + seconds)


_PACERS = {}
_PACERS_LOCK = threading.Lock()


# Reuse pacing state across workers targeting the same model and request limit.
def shared_pacer(model, requests_per_minute):
    with _PACERS_LOCK:
        return _PACERS.setdefault(
            (model, requests_per_minute), RequestPacer(requests_per_minute)
        )


class GeminiRequestPolicy:
    """Retry temporary limits, but stop a batch after repeated rejections."""

    def __init__(self, pacer):
        self.pacer = pacer
        self.lock = threading.Lock()
        self.blocked = None
        self.consecutive_limits = 0

    # Prevent new requests after a batch-level credentials, quota, or configuration failure.
    def check_blocked(self):
        with self.lock:
            if self.blocked:
                raise EvaluationFailure(
                    self.blocked.category, str(self.blocked), skipped=True
                )

    # Apply bounded retries and shared pacing; permanent failures block the batch.
    def invoke(self, operation):
        for attempt in range(3):
            self.pacer.wait(self.check_blocked)
            self.check_blocked()
            try:
                result = operation()
                with self.lock:
                    self.consecutive_limits = 0
                return result
            except Exception as exc:
                failure = classify_failure(exc)
                with self.lock:
                    if failure.category in {"quota", "credentials", "model", "request"}:
                        self.blocked = failure
                    if failure.category == "rate_limit":
                        self.consecutive_limits += 1
                        if self.consecutive_limits >= 3:
                            self.blocked = failure
                    blocked = self.blocked is not None
                if blocked:
                    raise failure from exc
                if failure.category == "rate_limit":
                    self.pacer.cool_down(max(failure.retry_after, 15 * 2**attempt))
                elif failure.category in {"timeout", "provider_error"}:
                    self.pacer.cool_down(2 ** (attempt + 1))
                else:
                    raise failure from exc
                if attempt == 2:
                    raise failure from exc
