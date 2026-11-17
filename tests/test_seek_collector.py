import json
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from backend.search import seek


class SeekCollectorTests(unittest.TestCase):
    def row(self, job_id):
        return {
            "id": job_id,
            "title": "Engineer",
            "advertiser": {"description": "Example"},
            "locations": [{"label": "Sydney"}],
            "listingDate": "2026-10-15",
        }

    def test_pages_full_evidence_dedup_and_limit(self):
        first = json.dumps({"data": [self.row(1)], "totalCount": 3})
        second = json.dumps({"data": [self.row(1), self.row(2)], "totalCount": 3})
        html = '<div data-automation="jobAdDetails"><p>Requires Python</p><p>Two years experience</p></div>'
        with patch.object(
            seek, "_request", side_effect=[first, html, second, html]
        ) as request:
            jobs = seek.collect("Engineer", "Sydney", limit=2)
        self.assertEqual(len(jobs), 2)
        self.assertIn("Two years experience", jobs[0]["description"])
        self.assertIn("page=2", request.call_args_list[2].args[0])
        self.assertEqual(request.call_count, 4)

    def test_missing_description_reports_failure_not_empty_success(self):
        errors = []
        with patch.object(
            seek,
            "_request",
            side_effect=[
                json.dumps({"data": [self.row(1)]}),
                "<html>Access blocked</html>",
            ],
        ):
            self.assertEqual(
                seek.collect("Engineer", "Sydney", on_error=errors.append), []
            )
        self.assertIn("descriptions were unavailable", errors[0])

    def test_cancellation_no_requests(self):
        with patch.object(seek, "_request") as request:
            self.assertEqual(
                seek.collect("Engineer", "Sydney", should_cancel=lambda: True), []
            )
        request.assert_not_called()

    def test_partial_results_and_changed_search_format(self):
        errors = []
        with patch.object(
            seek,
            "_request",
            side_effect=[
                json.dumps({"data": [self.row(1)], "totalCount": 2}),
                '<div data-automation="jobAdDetails">Python</div>',
                '{"unexpected": true}',
            ],
        ):
            jobs = seek.collect("Engineer", "Sydney", on_error=errors.append)
        self.assertEqual(len(jobs), 1)
        self.assertIn("response changed", errors[0])

    def test_jsonld_description(self):
        html = (
            '<script type="application/ld+json">'
            + json.dumps(
                {"@type": "JobPosting", "description": "<p>Python required</p>"}
            )
            + "</script>"
        )
        self.assertEqual(seek.description(html), "Python required")

    def test_throttling_stops_requests_during_cooldown(self):
        with patch.object(seek, "_COOLDOWN", 0), patch.object(
            seek, "_NEXT_REQUEST", 0
        ), patch.object(
            seek,
            "urlopen",
            side_effect=HTTPError(
                "https://www.seek.com.au/",
                429,
                "throttled",
                {"Retry-After": "600"},
                None,
            ),
        ) as request:
            for _ in range(2):
                with self.assertRaises(seek.SeekError) as raised:
                    seek._request("https://www.seek.com.au/", lambda: False)
                self.assertTrue(raised.exception.rate_limited)
            self.assertEqual(request.call_count, 1)

    def test_block_is_not_reported_as_a_rate_limit(self):
        with patch.object(seek, "_COOLDOWN", 0), patch.object(
            seek, "_COOLDOWN_STATUS", 429
        ), patch.object(seek, "_NEXT_REQUEST", 0), patch.object(
            seek,
            "urlopen",
            side_effect=HTTPError("https://www.seek.com.au/", 403, "blocked", {}, None),
        ):
            # Both the first block and the cooldown that follows stay visible errors.
            for _ in range(2):
                with self.assertRaises(seek.SeekError) as raised:
                    seek._request("https://www.seek.com.au/", lambda: False)
                self.assertFalse(raised.exception.rate_limited)
                self.assertIn("block", str(raised.exception))

    def test_official_domain_redirect_is_accepted(self):
        from urllib.request import Request

        handler = seek._SeekRedirectHandler()
        redirected = handler.redirect_request(
            Request("https://www.seek.com.au/job/123"),
            None,
            301,
            "Moved",
            {},
            "https://au.seek.com/job/123",
        )
        self.assertEqual(redirected.full_url, "https://au.seek.com/job/123")
        response = MagicMock()
        response.url = "https://au.seek.com/job/123"
        response.read.return_value = b"content"
        response.__enter__.return_value = response
        with patch.object(seek, "_NEXT_REQUEST", 0), patch.object(
            seek, "_COOLDOWN", 0
        ), patch.object(seek, "urlopen", return_value=response):
            self.assertEqual(
                seek._request("https://www.seek.com.au/job/123", lambda: False),
                "content",
            )

    def test_unsupported_redirects_rejected_before_following(self):
        from urllib.request import Request

        handler = seek._SeekRedirectHandler()
        for url in [
            "https://au.seek.com.evil.test/job/1",
            "http://au.seek.com/job/1",
            "https://other.test/",
            "https://au.seek.com:444/job/1",
            "https://user@au.seek.com/job/1",
        ]:
            with self.subTest(url=url), self.assertRaises(seek.SeekError):
                handler.redirect_request(
                    Request("https://au.seek.com/job/1"), None, 302, "Moved", {}, url
                )

    def test_preserves_seek_headings_paragraphs_and_lists(self):
        html = """<div data-automation="jobAdDetails"><h2>About the role</h2>
        <p>Work with <strong>Python</strong> and SQL.</p><p>Support the team.</p>
        <p><strong>Requirements</strong></p><ul><li>Three years experience</li><li>SQL skills</li></ul>
        <ol start="2"><li>Apply online</li><li>Attend interview</li></ol>
        <script>unwanted()</script></div>"""
        text = seek.description(html)
        self.assertIn("## About the role", text)
        self.assertIn("Work with Python and SQL.\n\nSupport the team.", text)
        self.assertIn("## Requirements\n\n- Three years experience\n- SQL skills", text)
        self.assertIn("2. Apply online\n3. Attend interview", text)
        self.assertNotIn("unwanted", text)

    def test_jsonld_preserves_the_same_block_structure(self):
        source = "<h3>Requirements</h3><ul><li>Python</li></ul>"
        data = (
            '<script type="application/ld+json">'
            + json.dumps({"@type": "JobPosting", "description": source})
            + "</script>"
        )
        self.assertEqual(seek.description(data), "## Requirements\n\n- Python")
