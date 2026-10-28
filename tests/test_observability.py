"""Tracing must preserve behavior and never export private function payloads."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock, patch
from backend import observability as tracing


class TracingTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        p = patch.object(tracing, "_client", return_value=self.client)
        p.start()
        self.addCleanup(p.stop)
        p = patch.dict(
            "os.environ",
            {"CAREER_LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "synthetic"},
        )
        p.start()
        self.addCleanup(p.stop)

    def test_disabled_never_creates_client(self):
        with patch.dict("os.environ", {"CAREER_LANGSMITH_TRACING": "false"}):
            self.assertEqual(tracing.stage("stage")(lambda: 12)(), 12)
        tracing._client.assert_not_called()

    def test_payloads_and_raw_errors_are_not_exported(self):
        @tracing.stage("test")
        def operation(private):
            raise ValueError(private)

        with self.assertRaisesRegex(ValueError, "private-resume"):
            operation("private-resume")
        serialized = str(self.client.mock_calls)
        self.assertNotIn("private-resume", serialized)
        self.assertEqual(self.client.update_run.call_args.kwargs["error"], "ValueError")
        self.assertEqual(self.client.create_run.call_args.kwargs["inputs"], {})

    def test_nested_threads_share_parent_and_keep_result_counts(self):
        @tracing.stage("child")
        def child():
            return ["private contents"]

        @tracing.stage("parent")
        def parent():
            with ThreadPoolExecutor() as executor:
                return tracing.submit(executor, child).result()

        self.assertEqual(parent(), ["private contents"])
        root, child_call = [
            call.kwargs for call in self.client.create_run.call_args_list
        ]
        self.assertEqual(child_call["parent_run_id"], root["id"])
        self.assertEqual(child_call["trace_id"], root["trace_id"])
        self.assertEqual(
            self.client.update_run.call_args.kwargs["outputs"]["result_count"], 1
        )
        self.assertNotIn("private contents", str(self.client.mock_calls))
        self.assertIsNone(tracing._CURRENT.get())

    def test_async_and_handled_failure(self):
        @tracing.stage("async")
        async def operation():
            tracing.mark("failed")
            return {"secret": "not exported"}

        asyncio.run(operation())
        self.assertEqual(
            self.client.update_run.call_args.kwargs["outputs"], {"outcome": "failed"}
        )
        self.assertNotIn("not exported", str(self.client.mock_calls))

    def test_telemetry_failure_does_not_repeat_or_fail_work(self):
        self.client.create_run.side_effect = RuntimeError("connection")
        self.client.update_run.side_effect = RuntimeError("connection")
        work = Mock(return_value="result")
        with self.assertLogs("backend.observability", level="WARNING"):
            self.assertEqual(tracing.stage("test")(work)(), "result")
        work.assert_called_once()

    def test_implicit_langchain_tracing_disabled(self):
        from langsmith.run_helpers import get_tracing_context

        @tracing.stage("test")
        def operation():
            return get_tracing_context()["enabled"]

        self.assertFalse(operation())

    def test_only_allowlisted_provider_metadata(self):
        @tracing.stage("provider")
        def operation(provider, private):
            return private

        operation("claude", "secret")
        self.assertEqual(
            self.client.create_run.call_args.kwargs["extra"]["metadata"]["provider"],
            "claude",
        )
        self.assertNotIn("secret", str(self.client.mock_calls))

    def test_missing_key_disables_delivery(self):
        with patch.dict("os.environ", {"LANGSMITH_API_KEY": ""}):
            self.assertEqual(tracing.stage("test")(lambda: "value")(), "value")
        tracing._client.assert_not_called()

    def test_partial_child_marks_parent_without_exporting_details(self):
        @tracing.stage("child")
        def child():
            tracing.mark("partial")

        @tracing.stage("parent")
        def parent():
            child()

        parent()
        self.assertEqual(
            self.client.update_run.call_args.kwargs["outputs"]["outcome"], "partial"
        )

    def test_client_setup_failure_preserves_operation(self):
        tracing._client.side_effect = RuntimeError("private connection information")
        with self.assertLogs("backend.observability", level="WARNING") as logs:
            self.assertEqual(tracing.stage("test")(lambda: 42)(), 42)
        self.assertNotIn("private connection information", str(logs.output))

    def test_sdk_updates_preserve_child_parent_in_serialized_payload(self):
        from langsmith import Client

        client = Client(
            api_url="https://example.test",
            api_key="synthetic",
            auto_batch_tracing=False,
        )
        tracing._client.return_value = client

        @tracing.stage("child")
        def child():
            return []

        @tracing.stage("root")
        def root():
            child()

        # Exercise actual SDK update serialization, intercepting before any HTTP call.
        with patch.object(Client, "create_run") as create, patch.object(
            Client, "_update_run"
        ) as update:
            root()
        root_create, child_create = [call.kwargs for call in create.call_args_list]
        child_update, root_update = [call.args[0] for call in update.call_args_list]
        self.assertEqual(child_update["parent_run_id"], root_create["id"])
        self.assertEqual(child_update["parent_run_id"], child_create["parent_run_id"])
        self.assertEqual(child_update["trace_id"], root_create["trace_id"])
        self.assertEqual(child_update["dotted_order"], child_create["dotted_order"])
        self.assertIsNone(root_update["parent_run_id"])
        self.assertEqual(len(root_update["dotted_order"].split(".")), 1)

    def test_collection_batches_group_each_provider_and_processing_steps(self):
        from backend.search.adaptive import collect, Stream

        @tracing.stage("jobspy.search")
        def fetch(stream, budget):
            return [{"url": stream.board, "description": "private description"}]

        @tracing.stage("jobs.descriptions")
        def hydrate(rows, budget):
            return rows

        rows = collect(
            [
                Stream(board, "private role", "private location")
                for board in ["linkedin", "indeed"]
            ],
            fetch,
            hydrate,
            lambda job: True,
            lambda job: True,
            lambda rows, previous: rows,
            dict(batches=2, details=10, candidates=50, seconds=120),
        )
        self.assertEqual(len(rows), 2)
        created = [call.kwargs for call in self.client.create_run.call_args_list]
        root = created[0]
        batches = [row for row in created if row["name"].startswith("jobs.batch.")]
        self.assertEqual(
            [row["name"] for row in batches],
            ["jobs.batch.linkedin", "jobs.batch.indeed"],
        )
        for number, batch in enumerate(batches, 1):
            self.assertEqual(batch["parent_run_id"], root["id"])
            self.assertEqual(batch["extra"]["metadata"]["batch_number"], number)
            children = {
                row["name"] for row in created if row["parent_run_id"] == batch["id"]
            }
            self.assertTrue(
                {
                    "jobspy.search",
                    "jobs.filter_cards",
                    "jobs.deduplicate_incoming",
                    "jobs.select_descriptions",
                    "jobs.descriptions",
                    "jobs.filter_descriptions",
                    "jobs.merge_unique_results",
                }.issubset(children)
            )
        self.assertNotIn("private", str(self.client.mock_calls))

    def test_deferred_batches_are_separate_and_close_on_failure(self):
        with self.assertRaises(ValueError):
            with tracing.collection_batch("linkedin", 1):
                raise ValueError("private")
        self.assertEqual(
            self.client.update_run.call_args.kwargs["outputs"]["outcome"], "failed"
        )
        self.assertIsNone(tracing._CURRENT.get())
        with tracing.collection_batch("mixed", 1, deferred=True):
            pass
        self.assertEqual(
            self.client.create_run.call_args.kwargs["name"], "jobs.deferred_batch.mixed"
        )
        self.assertIsNone(self.client.create_run.call_args.kwargs["parent_run_id"])
