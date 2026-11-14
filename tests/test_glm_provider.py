"""GLM adapter/default routing tests; all model responses are local mocks."""

import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from helpers import HAS_ICARUS, ROOT, RULES, TASKS, SkillHTTPReplay, TemporaryTestCase, fixture
from rtlflow.cli import load_settings, main
from rtlflow.pipeline import initial_messages, run_batch, run_task
from rtlflow.providers import GLMProvider, GenerationError


KEY = "fake-glm-key-for-tests"
REASONING = "PRIVATE_REASONING_NOT_FOR_REPORTS"


def api_response(code=None, model="glm-5.3", stop="stop"):
    return io.BytesIO(json.dumps({
        "model": model,
        "choices": [{"message": {"content": fixture("and2.v") if code is None else code,
                                 "reasoning_content": REASONING}, "finish_reason": stop}],
        "usage": {"prompt_tokens": 22, "completion_tokens": 35, "total_tokens": 57},
    }).encode())


class GLMProviderTests(TemporaryTestCase):
    def setUp(self):
        super().setUp()
        self.settings = {**load_settings(ROOT / "configs/glm.json"), "group": "Skill", "max_refactors": 0}
        environment = patch.dict(os.environ, {"GLM_API_KEY": KEY}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_single_group_cli_selects_default_glm_without_live_call(self):
        with patch("rtlflow.cli.GLMProvider") as provider, patch("rtlflow.cli.MockProvider") as replay, \
                patch("rtlflow.cli.run_batch") as batch, patch("builtins.print"):
            batch.return_value = {"passed": 1, "total": 1}
            self.assertEqual(main(["--task", "aes", "--group", "Skill"]), 0)
        settings = provider.call_args.args[0]
        self.assertEqual(settings["model"], "glm-5.3")
        self.assertEqual(settings["thinking"], "high")
        self.assertEqual(settings["api_key_env"], "GLM_API_KEY")
        self.assertEqual(batch.call_args.args[1], provider.return_value)
        replay.assert_not_called()

    def test_removed_providers_rejected_before_any_call(self):
        path = self.directory / "old-config.json"
        for name in ("pi", "openai", "unknown"):
            path.write_text(json.dumps({**self.settings, "provider": name}))
            with self.subTest(provider=name), patch("rtlflow.cli.GLMProvider") as provider, \
                    patch("rtlflow.cli.run_batch") as batch, patch("builtins.print"):
                with self.assertRaisesRegex(ValueError, "provider 仅支持 glm"):
                    load_settings(path)
                self.assertEqual(main(["--config", str(path), "--task", "and2"]), 2)
                provider.assert_not_called()
                batch.assert_not_called()

    def test_default_config_selects_project_generation_catalog(self):
        self.assertTrue(self.settings["tasks"].endswith("/project-rtl/tasks.json"))
        from rtlflow.project import load_projects as load_tasks
        for language in ("verilog", "systemverilog"):
            self.assertEqual(len(load_tasks(self.settings["tasks"], language=language)),
                             {'verilog': 27, 'systemverilog': 30, 'chisel': 2}[language])

    def test_high_request_and_public_only_messages(self):
        provider = GLMProvider(self.settings)
        messages = initial_messages(TASKS["and2"], "Baseline", RULES)
        with patch("rtlflow.providers.urllib.request.urlopen", return_value=api_response()) as call:
            result = provider.generate("and2", messages)
        call.assert_called_once()
        request = call.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://open.bigmodel.cn/api/paas/v4/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + KEY)
        self.assertEqual(call.call_args.kwargs["timeout"], 120)
        self.assertEqual(body, {"model": "glm-5.3", "messages": messages,
                               "temperature": 1.0, "max_tokens": 32768,
                               "thinking": {"type": "enabled"}, "reasoning_effort": "high"})
        for hidden in (KEY, "testbenches/", "RTL_BENCH_PASS", "AND truth table mismatch"):
            self.assertNotIn(hidden, request.data.decode())
        self.assertEqual(result.text, fixture("and2.v"))
        self.assertEqual(result.usage["total_tokens"], 57)
        self.assertEqual(result.metadata["provider"], "glm")
        self.assertEqual(result.metadata["response_model"], "glm-5.3")
        self.assertEqual(result.metadata["reasoning_effort_requested"], "high")
        self.assertEqual(result.metadata["stop_reason"], "stop")
        self.assertEqual(result.metadata["model_calls"], 1)
        self.assertNotIn(REASONING, repr(result))
        self.assertNotIn(KEY, repr(result))

    def test_missing_key_names_correct_variable_without_fallback(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "other-key"}, clear=True), \
                patch("rtlflow.providers.urllib.request.urlopen") as call:
            with self.assertRaisesRegex(ValueError, "GLM_API_KEY"):
                GLMProvider(self.settings)
        call.assert_not_called()

    def test_unrelated_openai_environment_does_not_override_glm(self):
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://example.invalid/v1",
                                     "OPENAI_API_KEY": "other-key", "RTL_MODEL": "other-model"}):
            provider = GLMProvider({})
        self.assertEqual(provider.model, "glm-5.3")
        self.assertEqual(provider.api_key, KEY)
        self.assertEqual(provider.url, "https://open.bigmodel.cn/api/paas/v4/chat/completions")

    def test_explicit_endpoint_and_key_environment_overrides(self):
        with patch.dict(os.environ, {"CUSTOM_GLM_KEY": "custom-test-key",
                                     "GLM_BASE_URL": "https://example.invalid/v4/"}):
            provider = GLMProvider({**self.settings, "api_key_env": "CUSTOM_GLM_KEY"})
        self.assertEqual(provider.url, "https://example.invalid/v4/chat/completions")
        self.assertEqual(provider.api_key, "custom-test-key")

    def test_invalid_endpoint_is_rejected_without_echoing_secrets(self):
        for base in ("", "file:///tmp/api", "https://user:secret@example.invalid/v1",
                     "https://example.invalid/v1?api_key=secret", "https://example.invalid/v1#secret"):
            with self.subTest(base=base), patch.dict(os.environ, {"GLM_BASE_URL": base}):
                with self.assertRaisesRegex(ValueError, "GLM_BASE_URL") as caught:
                    GLMProvider(self.settings)
                self.assertNotIn("secret", str(caught.exception))

    def test_thinking_levels_and_invalid_settings(self):
        path = self.directory / "config.json"
        for level in ("low", "high", "max"):
            path.write_text(json.dumps({**self.settings, "thinking": level}))
            body = GLMProvider(load_settings(path)).request_body([])
            self.assertEqual(body["reasoning_effort"], level)
            self.assertEqual(body["thinking"], {"type": "enabled"})
        for extra in ({"thinking": "medium"}, {"thinking": "off"}, {"thinking": {"type": "disabled"}},
                      {"thinking": None}, {"api_key": KEY}):
            path.write_text(json.dumps({**self.settings, **extra}))
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                load_settings(path)

    def test_empty_or_reasoning_only_output_is_not_rtl(self):
        with patch("rtlflow.providers.urllib.request.urlopen", return_value=api_response(code="")):
            with self.assertRaises(GenerationError) as caught:
                GLMProvider(self.settings).generate("and2", [])
        self.assertNotIn(REASONING, str(caught.exception))

    def test_mismatched_model_and_incomplete_output_rejected(self):
        for model, stop in (("wrong-model", "stop"), (None, "stop"), ("glm-5.3", "length"),
                            ("glm-5.3", "tool_calls"), ("glm-5.3", None)):
            with self.subTest(model=model, stop=stop), patch(
                "rtlflow.providers.urllib.request.urlopen", return_value=api_response(model=model, stop=stop),
            ) as call:
                with self.assertRaises(GenerationError) as caught:
                    GLMProvider(self.settings).generate("and2", [])
                self.assertEqual(caught.exception.metadata["reasoning_effort_requested"], "high")
                self.assertEqual(caught.exception.metadata["model_calls"], 1)
                call.assert_called_once()

    def test_http_error_and_timeout_are_redacted_without_retry(self):
        for error in (urllib.error.HTTPError("https://example.invalid", 401, KEY, {}, io.BytesIO(KEY.encode())),
                      TimeoutError(KEY)):
            with self.subTest(error=type(error).__name__), patch(
                "rtlflow.providers.urllib.request.urlopen", side_effect=error,
            ) as call:
                with self.assertRaises(GenerationError) as caught:
                    GLMProvider(self.settings).generate("and2", [])
                self.assertNotIn(KEY, str(caught.exception))
                self.assertNotIn(KEY, json.dumps(caught.exception.metadata))
                call.assert_called_once()

    def test_malformed_responses_fail_without_echoing_payload(self):
        for payload in (None, [], {}, {"choices": []}, {"choices": [None]}, KEY):
            with self.subTest(payload=type(payload).__name__), patch(
                "rtlflow.providers.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode()),
            ) as call:
                with self.assertRaises(GenerationError) as caught:
                    GLMProvider(self.settings).generate("and2", [])
                self.assertNotIn(KEY, str(caught.exception))
                self.assertEqual(caught.exception.metadata["reasoning_effort_requested"], "high")
                call.assert_called_once()

    def test_keyboard_interrupt_propagates_without_retry(self):
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=KeyboardInterrupt) as call:
            with self.assertRaises(KeyboardInterrupt):
                GLMProvider(self.settings).generate("and2", [])
        call.assert_called_once()

    def test_api_error_stops_task_without_repairs_or_source(self):
        error = urllib.error.HTTPError("https://example.invalid", 401, KEY, {}, io.BytesIO(KEY.encode()))
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=error) as call:
            report = run_task(TASKS["and2"], GLMProvider(self.settings), self.settings, RULES, self.directory)
        call.assert_called_once()
        self.assertEqual(report["stop_reason"], "generation_error")
        self.assertEqual(report["repair_calls"], 0)
        self.assertIsNone(report["final_source"])
        self.assertNotIn(KEY, json.dumps(report))
        self.assertIn("HTTP 401", report["attempts"][0]["error"])

    @unittest.skipUnless(HAS_ICARUS, "requires Icarus/vvp")
    def test_offline_glm_repair_pipeline_and_secret_free_artifacts(self):
        output = self.directory / "run"
        replay = SkillHTTPReplay([fixture("add8.broken.v"), fixture("add8.v")])
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=replay) as call:
            summary = run_batch([TASKS["add8"]], GLMProvider(self.settings), self.settings, RULES, output)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["repairs_succeeded"], 1)
        self.assertEqual(call.call_count, 6)
        self.assertEqual(summary["model_calls"], 6)
        self.assertEqual(summary["tool_calls"], 6)
        repair = json.loads(call.call_args_list[3].args[0].data)
        self.assertEqual([m["role"] for m in repair["messages"]], ["system", "user", "assistant", "user"])
        self.assertEqual(repair["reasoning_effort"], "high")
        report = json.loads((output / "add8/report.json").read_text())
        self.assertEqual(report["provider"], "glm")
        self.assertEqual(report["model"], "glm-5.3")
        self.assertTrue(report["skill_loaded"])
        self.assertTrue(report["rules_applied"])
        self.assertEqual(report["attempts"][1]["generation_metadata"]["reasoning_effort_requested"], "high")
        for path in output.rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                self.assertNotIn(KEY.encode(), content, str(path))
                self.assertNotIn(REASONING.encode(), content, str(path))
