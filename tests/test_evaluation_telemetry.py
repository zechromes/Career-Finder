"""Synthetic streaming metrics; no network or private payload exports."""

import unittest
from unittest.mock import Mock, patch
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult
from backend.evaluation.telemetry import model_request, streaming_options
from backend import observability


class MetricsTests(unittest.TestCase):
    def test_streamed_usage_and_timing_without_payloads(self):
        client = Mock()
        with patch.dict(
            "os.environ",
            {"CAREER_LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "synthetic"},
        ), patch.object(observability, "_client", return_value=client), patch(
            "backend.evaluation.telemetry.perf_counter", side_effect=[10, 12, 16]
        ):
            for provider in ["gpt"]:
                with model_request(provider, "synthetic-model") as callbacks:
                    callback = callbacks[0]
                    callback.on_chat_model_start({}, ["private resume"])
                    callback.on_llm_new_token("")
                    callback.on_llm_new_token("private output")
                    callback.on_llm_new_token("more private output")
                    callback.on_llm_end(
                        LLMResult(
                            generations=[
                                [
                                    ChatGeneration(
                                        message=AIMessage(
                                            content="private output",
                                            usage_metadata={
                                                "input_tokens": 100,
                                                "output_tokens": 13,
                                                "total_tokens": 113,
                                                "input_token_details": {
                                                    "cache_read": 80
                                                },
                                                "output_token_details": {
                                                    "reasoning": 10
                                                },
                                            },
                                        )
                                    )
                                ]
                            ]
                        )
                    )
        output = client.update_run.call_args.kwargs["outputs"]
        self.assertEqual(output["ttft"], 2)
        self.assertEqual(output["tpot"], 2)
        self.assertEqual(
            output["usage_metadata"]["input_token_details"]["cache_read"], 80
        )
        self.assertEqual(client.create_run.call_args.kwargs["run_type"], "llm")
        self.assertEqual(
            client.update_run.call_args.kwargs["events"][0]["name"], "new_token"
        )
        self.assertNotIn("private", str(client.mock_calls))

    def test_missing_usage_failure_and_single_chunk_do_not_invent_tpot(self):
        for provider in ("gpt", "claude", "gemini"):
            client = Mock()
            with patch.dict(
                "os.environ",
                {"CAREER_LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "synthetic"},
            ), patch.object(observability, "_client", return_value=client):
                with self.assertRaises(ValueError):
                    with model_request(provider, "synthetic-model") as callbacks:
                        callback = callbacks[0]
                        callback.on_chat_model_start({}, [])
                        callback.on_llm_new_token(
                            "",
                            chunk=ChatGenerationChunk(
                                message=AIMessageChunk(
                                    content="",
                                    tool_call_chunks=[
                                        {
                                            "name": None,
                                            "args": "{",
                                            "id": None,
                                            "index": 0,
                                        }
                                    ],
                                )
                            ),
                        )
                        raise ValueError("private failure")
            output = client.update_run.call_args.kwargs["outputs"]
            self.assertIn("ttft", output)
            self.assertNotIn("tpot", output)
            self.assertNotIn("usage_metadata", output)
            self.assertNotIn("private failure", str(client.mock_calls))

    def test_invoke_aggregates_stream_and_captures_usage_before_parser(self):
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.output_parsers import JsonOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        class SyntheticModel(BaseChatModel):
            streaming: bool = True

            @property
            def _llm_type(self):
                return "synthetic"

            def _generate(self, *args, **kwargs):
                raise AssertionError("Expected streaming")

            def _stream(self, messages, stop=None, run_manager=None, **kwargs):
                for text in ('{"ok":', "true}"):
                    yield ChatGenerationChunk(message=AIMessageChunk(content=text))
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        usage_metadata={
                            "input_tokens": 9,
                            "output_tokens": 5,
                            "total_tokens": 14,
                        },
                    )
                )

        chain = (
            ChatPromptTemplate.from_messages([("human", "{private}")])
            | SyntheticModel(streaming=True)
            | JsonOutputParser()
        )
        client = Mock()
        with patch.dict(
            "os.environ",
            {"CAREER_LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "synthetic"},
        ), patch.object(observability, "_client", return_value=client):
            with model_request("gpt", "synthetic") as callbacks:
                result = chain.invoke(
                    {"private": "private resume"}, config={"callbacks": callbacks}
                )
        self.assertEqual(result, {"ok": True})
        output = client.update_run.call_args.kwargs["outputs"]
        self.assertEqual(output["usage_metadata"]["output_tokens"], 5)
        self.assertIn("ttft", output)
        self.assertIn("tpot", output)
        self.assertNotIn("private resume", str(client.mock_calls))

    def test_disabled_and_streaming_options(self):
        with patch.dict("os.environ", {"CAREER_LANGSMITH_TRACING": "false"}):
            with model_request("gpt", "synthetic") as callbacks:
                self.assertEqual(callbacks, [])
            self.assertEqual(streaming_options("gpt"), {})
        with patch.dict(
            "os.environ",
            {"CAREER_LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "synthetic"},
        ):
            self.assertEqual(
                streaming_options("gpt"), {"streaming": True, "stream_usage": True}
            )
            self.assertEqual(streaming_options("gemini"), {"streaming": True})
            self.assertEqual(streaming_options("claude"), {"streaming": True})
