"""Streaming/timeout protocol regressions; synthetic HTTP only, no live API."""
import contextlib
import http.client
import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from helpers import HAS_ICARUS, RULES, TASKS, ImplementationTestCase as TemporaryTestCase, fixture
from rtlflow.cli import load_settings
from rtlflow.pipeline import run_group_comparison
from rtlflow.providers import GLMProvider, GenerationError
from rtlflow.skill_tools import SkillReader

SECRET = "PRIVATE_REASONING_OR_CREDENTIAL"
USAGE = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}


class SSE(io.BytesIO):
    headers = {"Content-Type": "text/event-stream; charset=utf-8"}

    def __init__(self, events, *, done=True, failure=None):
        wire = ": heartbeat\r\n\r\n" + "".join(
            "data: " + json.dumps(event, ensure_ascii=False) + "\r\n\r\n" for event in events
        )
        super().__init__((wire + ("data: [DONE]\r\n\r\n" if done else "")).encode())
        self.failure = failure

    def readline(self, size=-1):
        line = super().readline(size)
        if not line and self.failure:
            raise self.failure
        return line


def chunk(delta=None, stop=None, **extra):
    return {"model": "glm-5.3", "choices": [{"index": 0, "delta": delta or {}, "finish_reason": stop}], **extra}


def text_stream(text, **kwargs):
    middle = len(text) // 2
    return SSE([chunk({"reasoning_content": SECRET}), chunk({"content": text[:middle]}),
                chunk({"content": text[middle:]}, "stop"),
                {"model": "glm-5.3", "choices": [], "usage": USAGE}], **kwargs)


def tools_stream(paths):
    # Tool names, IDs and JSON arguments may span multiple events and interleave.
    events = []
    for index, path in enumerate(paths):
        arguments = json.dumps({"path": path})
        events.extend([
            chunk({"tool_calls": [{"index": index, "id": f"call_{path.replace('/', '_').replace('.', '_')}",
                                   "type": "function", "function": {"name": "read_", "arguments": arguments[:8]}}]}),
            chunk({"tool_calls": [{"index": index, "function": {"name": "skill", "arguments": arguments[8:]}}]}),
        ])
    return SSE([*events, chunk(stop="tool_calls"), {"model": "glm-5.3", "choices": [], "usage": USAGE}])


class StreamingTests(TemporaryTestCase):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {"GLM_API_KEY": SECRET}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        quiet = contextlib.redirect_stderr(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def generate(self, responses, *, skill=False, **settings):
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=responses) as http:
            result = GLMProvider(settings).generate("unit", [], trace_dir=self.directory,
                                                   skill=SkillReader("verilog") if skill else None)
        return result, http

    def trace(self):
        text = (self.directory / "agent_trace.json").read_text()
        self.assertNotIn(SECRET, text)
        self.assertNotIn("reasoning_content", text)
        self.assertNotIn("Authorization", text)
        return json.loads(text)

    def test_stream_reassembles_unicode_public_text_and_usage(self):
        text = "完整项目\n" + fixture("and2.v")
        result, http = self.generate([text_stream(text)])
        self.assertEqual(result.text, text)
        self.assertEqual(result.usage, USAGE)
        self.assertTrue(result.metadata["usage_complete"])
        self.assertEqual(result.metadata["model_calls"], 1)
        self.assertTrue(json.loads(http.call_args.args[0].data)["stream"])
        self.assertNotIn("max_tokens", json.loads(http.call_args.args[0].data))
        self.assertEqual(result.metadata["token_limit_mode"], "server_default")
        trace = self.trace()
        self.assertEqual(trace["status"], "passed")
        self.assertEqual(trace["turns"][0]["stream_chunks"], 4)
        self.assertIn("first_chunk_seconds", trace["turns"][0])

    def test_streamed_fragmented_tools_load_all_documents_before_candidate(self):
        result, http = self.generate([tools_stream(["SKILL.md"]),
                                      tools_stream(["rules.md", "references/verilog.md"]),
                                      text_stream(fixture("and2.v"))], skill=True)
        self.assertTrue(result.metadata["skill_loaded"])
        self.assertEqual(result.metadata["tool_calls"], 3)
        self.assertEqual(http.call_count, 3)
        self.assertEqual(result.usage["total_tokens"], 90)
        self.assertEqual(result.metadata["usage_observed_calls"], 3)
        self.assertTrue(all(t["status"] == "passed" for t in self.trace()["turns"]))
        self.assertTrue(all("max_tokens" not in json.loads(call.args[0].data) for call in http.call_args_list))

    def test_timeout_after_tools_keeps_usage_not_stale_stop_and_never_retries(self):
        responses = [tools_stream(["SKILL.md"]), tools_stream(["rules.md", "references/verilog.md"]),
                     SSE([chunk({"reasoning_content": SECRET})], done=False, failure=TimeoutError(SECRET))]
        with self.assertRaises(GenerationError) as error:
            self.generate(responses, skill=True, api_timeout_seconds=42)
        metadata = error.exception.metadata
        self.assertEqual(error.exception.code, "api_timeout")
        self.assertIn("42", str(error.exception))
        self.assertEqual(metadata["model_calls"], 3)
        self.assertEqual(metadata["usage"]["total_tokens"], 60)
        self.assertFalse(metadata["usage_complete"])
        self.assertTrue(metadata["skill_loaded"])
        self.assertNotIn("stop_reason", metadata)
        self.assertNotIn("response_model", metadata)
        trace = self.trace()
        self.assertEqual(trace["turns"][-1]["status"], "failed")
        self.assertEqual(trace["turns"][-1]["error_code"], "api_timeout")

    def test_eof_even_after_finish_reason_cannot_accept_partial_response(self):
        for response in (SSE([chunk({"content": "partial"})], done=False),
                         text_stream(fixture("and2.v"), done=False),
                         SSE([chunk({"content": "partial"})])):
            with self.subTest(), self.assertRaises(GenerationError) as error:
                self.generate([response])
            self.assertEqual(error.exception.code, "stream_incomplete")
            self.assertEqual(self.trace()["status"], "failed")

    def test_observed_stream_usage_is_not_lost_on_eof_or_double_counted(self):
        events = [chunk({"content": "partial"}, usage={"prompt_tokens": 10}),
                  chunk(stop="stop", usage=USAGE)]
        with self.assertRaises(GenerationError) as error:
            self.generate([SSE(events, done=False)])
        self.assertEqual(error.exception.metadata["usage"], USAGE)
        self.assertTrue(error.exception.metadata["usage_complete"])
        self.assertEqual(error.exception.code, "stream_incomplete")
        result, _ = self.generate([SSE(events)])
        self.assertEqual(result.usage, USAGE)

    def test_oversized_responses_fail_without_exporting_raw_data(self):
        for response in (text_stream(SECRET * 100), io.BytesIO(SECRET.encode() * 100)):
            with patch("rtlflow.providers.MAX_RESPONSE_BYTES", 128), self.assertRaises(GenerationError) as error:
                self.generate([response])
            self.assertEqual(error.exception.code, "response_too_large")
            self.trace()

    def test_interrupt_retains_stream_progress_without_reasoning(self):
        with self.assertRaises(KeyboardInterrupt):
            self.generate([SSE([chunk({"reasoning_content": SECRET})], done=False, failure=KeyboardInterrupt())])
        trace = self.trace()
        self.assertEqual(trace["status"], "interrupted")
        self.assertEqual(trace["turns"][0]["status"], "interrupted")
        self.assertEqual(trace["turns"][0]["stream_chunks"], 1)

    def test_truncation_preserves_only_public_response_for_audit(self):
        with self.assertRaises(GenerationError) as error:
            self.generate([SSE([chunk({"content": "partial", "reasoning_content": SECRET}, "length", usage=USAGE)])])
        self.assertEqual(error.exception.code, "output_truncated")
        self.assertIn("服务端默认值", str(error.exception))
        self.assertIsNone(error.exception.metadata["max_tokens_requested"])
        self.assertTrue(error.exception.metadata["usage_complete"])
        self.assertEqual(self.trace()["turns"][0]["response"]["content"], "partial")

    def test_stream_errors_wrong_model_and_malformed_deltas_are_redacted(self):
        for event in ({"error": SECRET}, chunk(model=SECRET),
                      chunk({"tool_calls": [{"index": 4}]}), chunk({"content": {"secret": SECRET}})):
            with self.subTest(event=event), self.assertRaises(GenerationError):
                self.generate([SSE([event])])
            self.assertEqual(self.trace()["status"], "failed")

    def test_wrapped_timeout_and_dropped_http_are_classified(self):
        for failure, code in ((urllib.error.URLError(TimeoutError(SECRET)), "api_timeout"),
                              (http.client.IncompleteRead(SECRET.encode()), "transport_error")):
            with self.subTest(code=code), self.assertRaises(GenerationError) as error:
                self.generate([failure])
            self.assertEqual(error.exception.code, code)
            self.assertEqual(error.exception.metadata["model_calls"], 1)
            self.assertNotIn(SECRET, str(error.exception))
            self.trace()

    def test_stream_deadline_stops_even_if_server_keeps_sending_heartbeats(self):
        with patch("rtlflow.providers.time.monotonic", side_effect=[0, 0, 2, 2]), \
                self.assertRaises(GenerationError) as error:
            self.generate([SSE([])], api_timeout_seconds=1)
        self.assertEqual(error.exception.code, "api_timeout")

    def test_explicit_nonstream_mode_and_missing_usage_remain_supported(self):
        payload = {"model": "glm-5.3", "choices": [{"message": {"content": fixture("and2.v")}, "finish_reason": "stop"}]}
        result, http = self.generate([io.BytesIO(json.dumps(payload).encode())], api_stream=False)
        self.assertNotIn("stream", json.loads(http.call_args.args[0].data))
        self.assertFalse(result.metadata["usage_complete"])
        self.assertEqual(result.usage, {})

    def test_config_rejects_non_boolean_stream_setting(self):
        config = self.directory / "config.json"
        for value in ("true", 1, None, []):
            config.write_text(json.dumps({"provider": "glm", "tasks": "unused", "api_stream": value}))
            with self.subTest(value=value), self.assertRaises(ValueError):
                load_settings(config)

    @unittest.skipUnless(HAS_ICARUS, "requires Icarus/vvp")
    def test_streaming_both_arms_generate_verify_and_repair_complete_projects(self):
        def respond(request, **kwargs):
            body = json.loads(request.data)
            self.assertTrue(body["stream"])
            if "tools" in body:
                loaded = {json.loads(m["content"])["path"] for m in body["messages"] if m["role"] == "tool"}
                allowed = body["tools"][0]["function"]["parameters"]["properties"]["path"]["enum"]
                missing = [path for path in allowed if path not in loaded]
                if missing:
                    return tools_stream(missing)
            repair = any(m["role"] == "user" and "上一个项目未通过" in m["content"] for m in body["messages"])
            return text_stream(fixture("add8.v" if repair else "add8.broken.v"))

        output = self.directory / "streamed-repair"
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=respond) as http:
            summary = run_group_comparison([TASKS["add8"]], GLMProvider,
                                           {"provider": "glm", "max_refactors": 0}, RULES,
                                           ["Baseline", "Skill"], output)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["repairs_succeeded"], 2)
        self.assertEqual(http.call_count, 8)
        self.assertEqual(summary["model_calls"], 8)
        self.assertEqual(summary["tool_calls"], 6)
        self.assertEqual(summary["usage"]["total_tokens"], 240)
        self.assertTrue(summary["usage_complete"])
        self.assertEqual(summary["generation_failures"], 0)
        for group in ("Baseline", "Skill"):
            report = json.loads((output / group / "add8/report.json").read_text())
            self.assertEqual(report["selected_attempt"], 1)
            self.assertEqual(report["skill_loaded"], group == "Skill")

    def test_both_group_summaries_expose_generation_errors_and_unknown_cost(self):
        output = self.directory / "comparison"
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=TimeoutError(SECRET)) as http:
            summary = run_group_comparison([TASKS["and2"], TASKS["add8"]], GLMProvider,
                                           {"provider": "glm"}, RULES, ["Baseline", "Skill"], output)
        self.assertEqual(http.call_count, 4)
        self.assertEqual(summary["not_run"], 4)
        self.assertEqual(summary["failed"], 0)  # Transport errors are not functional failures.
        self.assertEqual(summary["generation_failures"], 4)
        self.assertEqual(summary["generation_error_counts"], {"api_timeout": 4})
        self.assertFalse(summary["usage_complete"])
        self.assertEqual(summary["usage"], {})
        for task in summary["by_task"].values():
            for report in task.values():
                self.assertEqual(report["last_error_code"], "api_timeout")
                self.assertEqual(report["repair_calls"], 0)
                self.assertIsNone(report["final_source"])
        self.assertIn("last_error_code", (output / "summary.csv").read_text())
        for path in output.rglob("*.json"):
            self.assertNotIn(SECRET, path.read_text())
