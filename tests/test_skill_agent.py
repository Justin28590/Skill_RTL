"""Actual GLM tool-loop control flow with fake HTTP and real allowlisted Skill reads."""

import hashlib
import io
import json
import os
from pathlib import Path
import unittest
import urllib.error
from unittest.mock import patch

from helpers import HAS_ICARUS, ROOT, RULES, TASKS, SkillHTTPReplay, TemporaryTestCase, fixture
from rtlflow.cli import load_settings, planned_calls
from rtlflow.pipeline import initial_messages, _run_implementation as run_task
from rtlflow.providers import GLMProvider, GenerationError
from rtlflow.skill_tools import MAX_DOCUMENT_BYTES, SkillReader, skill_capabilities

KEY = "fake-skill-agent-secret"


def reply(content=None, calls=None, stop=None, model="glm-5.3"):
    message = {"content": content, "reasoning_content": "PRIVATE_CHAIN_OF_THOUGHT"}
    if calls is not None:
        message["tool_calls"] = calls
    return io.BytesIO(json.dumps({
        "model": model, "choices": [{"message": message,
                                      "finish_reason": stop or ("tool_calls" if calls else "stop")}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }).encode())


def tool(path="SKILL.md", identifier="read_1", name="read_skill", arguments=None):
    return {"id": identifier, "type": "function", "function": {
        "name": name, "arguments": json.dumps({"path": path}) if arguments is None else arguments,
    }}


class SkillReaderTests(TemporaryTestCase):
    def test_evaluator_constraints_live_in_runtime_capabilities(self):
        for language in ('verilog', 'systemverilog', 'chisel'):
            capabilities = skill_capabilities(language)
            for required in ('read_skill', 'SKILL.md', 'rules.md', f'references/{language}.md',
                             '不重新设计', '不新建TB', '完整JSON', '外层控制器', '每次调用独立加载'):
                self.assertIn(required, capabilities)
            self.assertNotIn('rtl-readable', capabilities)

    def test_progressive_reads_hashes_and_language_isolation(self):
        for language in ("verilog", "systemverilog", "chisel"):
            reader = SkillReader(language)
            self.assertEqual(reader.available_paths, ["SKILL.md"])
            with self.assertRaises(ValueError):
                reader.read("rules.md")
            for path in reader.paths:
                result = reader.read(path)
                self.assertEqual(result["sha256"], hashlib.sha256(result["content"].encode()).hexdigest())
                self.assertEqual(result["source_sha256"], hashlib.sha256(
                    (ROOT / "skills/rtl-readable" / path).read_bytes()).hexdigest())
            self.assertTrue(reader.complete)
            rules = reader.read("rules.md")["content"]
            label = {"verilog": "Verilog", "systemverilog": "SystemVerilog", "chisel": "Chisel"}[language]
            self.assertIn(f"## {label} 分支", rules)
            for other in {"verilog", "systemverilog", "chisel"} - {language}:
                with self.assertRaises(ValueError):
                    reader.read(f"references/{other}.md")

    def test_no_arbitrary_paths_or_external_links(self):
        reader = SkillReader("verilog")
        reader.read("SKILL.md")
        for path in ("../README.md", "../../data/project-rtl/sources/secworks/aes/src/rtl/aes.v", "/etc/passwd",
                     "data/project-rtl/tests/adapted/aes/tb_aes.v", "results/run/report.json",
                     "references/../SKILL.md", "./SKILL.md", "SKILL.md\x00", "", None,
                     "https://example.invalid/SKILL.md"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                reader.read(path)

    def test_missing_symlinked_or_oversized_documents_are_rejected(self):
        root = self.directory / "skill"
        root.mkdir()
        entry = root / "SKILL.md"
        with patch("rtlflow.skill_tools.SKILL_ROOT", root):
            with self.assertRaises(ValueError):
                SkillReader("verilog").read("SKILL.md")
            target = self.directory / "private.txt"
            target.write_text("PRIVATE_FILE")
            entry.symlink_to(target)
            with self.assertRaises(ValueError):
                SkillReader("verilog").read("SKILL.md")
            entry.unlink()
            entry.write_bytes(b"x" * (MAX_DOCUMENT_BYTES + 1))
            with self.assertRaises(ValueError):
                SkillReader("verilog").read("SKILL.md")

    def test_budget_counts_http_separately_from_candidates(self):
        settings = load_settings(ROOT / "configs/glm.json")
        self.assertEqual(planned_calls(settings, ["Baseline", "Skill"], 3),
                         {"max_provider_calls": 72, "max_model_calls": 252})
        self.assertEqual(planned_calls({**settings, "max_agent_turns": 4}, ["Skill"], 2),
                         {"max_provider_calls": 24, "max_model_calls": 96})
        self.assertEqual(planned_calls({**settings, "provider": "mock"}, ["Baseline", "Skill"], 1),
                         {"max_provider_calls": 24, "max_model_calls": 0})

    def test_budget_is_bounded_and_validated_before_provider_calls(self):
        settings = load_settings(ROOT / "configs/glm.json")
        config = self.directory / "config.json"
        for budget in (0, -1, 13, True, 1.5, "6", None):
            config.write_text(json.dumps({**settings, "max_agent_turns": budget}))
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                load_settings(config)


class SkillAgentTests(TemporaryTestCase):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {"GLM_API_KEY": KEY}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        guard = patch("rtlflow.providers.urllib.request.urlopen", side_effect=AssertionError("no live HTTP"))
        guard.start()
        self.addCleanup(guard.stop)
        self.settings = {**load_settings(ROOT / "configs/glm.json"), "group": "Skill"}
        self.messages = initial_messages(TASKS["and2"], "Skill", RULES)

    def generate(self, **settings):
        return GLMProvider({**self.settings, **settings}).generate(
            "and2", self.messages, skill=SkillReader("verilog"), trace_dir=self.directory,
        )

    def trace(self):
        return json.loads((self.directory / "agent_trace.json").read_text())

    def test_real_tool_decisions_short_prompt_and_auditable_trace(self):
        replay = SkillHTTPReplay([fixture("and2.v")])
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=replay):
            result = self.generate()
        self.assertEqual(result.text, fixture("and2.v"))
        self.assertEqual(result.metadata["model_calls"], 3)
        self.assertEqual(result.metadata["tool_calls"], 3)
        self.assertTrue(result.metadata["skill_loaded"])
        self.assertEqual(result.usage["total_tokens"], 171)
        self.assertNotIn("## 通用规则", json.dumps(replay.requests[0], ensure_ascii=False))
        self.assertIn("read_skill", replay.requests[0]["messages"][0]["content"])
        self.assertNotIn("rtl-readable", replay.requests[0]["messages"][0]["content"])
        self.assertTrue(replay.requests[0]["messages"][1]["content"].startswith("请调用 rtl-readable Skill，"))
        self.assertEqual(replay.requests[0]["tools"][0]["function"]["parameters"]["properties"]["path"]["enum"],
                         ["SKILL.md"])
        self.assertEqual([m["role"] for m in replay.requests[-1]["messages"]],
                         ["system", "user", "assistant", "tool", "assistant", "tool", "tool"])
        trace = self.trace()
        self.assertEqual(trace["status"], "passed")
        self.assertEqual(len(trace["turns"]), 3)
        self.assertEqual(trace["turns"][0]["request"], replay.requests[0])
        self.assertEqual(len(trace["turns"][1]["tool_results"]), 2)
        for message in replay.requests[-1]["messages"]:
            if message["role"] == "tool":
                document = json.loads(message["content"])
                self.assertEqual(document["sha256"], hashlib.sha256(document["content"].encode()).hexdigest())
        evidence = json.dumps(trace, ensure_ascii=False)
        for hidden in (KEY, "PRIVATE_REASONING_NOT_FOR_REPORTS"):
            self.assertNotIn(hidden, evidence)

        def check_protocol_fields(value):
            if isinstance(value, dict):
                # Public Skill prose may name these fields; actual protocol fields
                # and private reasoning content must never be serialized.
                self.assertNotIn("reasoning_content", value)
                self.assertNotIn("Authorization", value)
                for child in value.values():
                    check_protocol_fields(child)
            elif isinstance(value, list):
                for child in value:
                    check_protocol_fields(child)

        check_protocol_fields(trace)
        # The Skill may describe test conventions, but no hidden TB/fixture is read.
        self.assertNotIn("AND truth table mismatch", evidence)

    def test_reused_reader_does_not_carry_load_state_to_a_new_generation(self):
        reader = SkillReader("verilog")
        for path in reader.paths:
            reader.read(path)
        replay = SkillHTTPReplay([fixture("and2.v")])
        provider = GLMProvider(self.settings)
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=replay):
            for _ in range(2):
                result = provider.generate("and2", self.messages, skill=reader)
                self.assertEqual(result.metadata["model_calls"], 3)
                self.assertEqual(result.metadata["tool_calls"], 3)
        self.assertEqual(len(replay.requests), 6)
        self.assertEqual([body['tool_choice'] for body in replay.requests],
                         ['required', 'required', 'none'] * 2)
        for index in (0, 3):
            self.assertEqual(replay.requests[index]["tools"][0]["function"]["parameters"]["properties"]["path"]["enum"],
                             ["SKILL.md"])

    def test_failed_loading_does_not_create_source_or_spend_repair_budget(self):
        with patch("rtlflow.providers.urllib.request.urlopen", return_value=reply(fixture("and2.v"))) as http:
            report = run_task(TASKS["and2"], GLMProvider(self.settings), self.settings, RULES,
                              self.directory / "failed")
        http.assert_called_once()
        self.assertEqual(report["functional_status"], "not_run")
        self.assertFalse(report["skill_loaded"])
        self.assertIsNone(report["final_source"])
        self.assertEqual(report["repair_calls"], 0)
        self.assertIn("未完成 Skill", report["attempts"][0]["error"])
        trace = json.loads(Path(report["attempts"][0]["agent_trace_path"]).read_text())
        self.assertEqual(trace["status"], "failed")

    def test_baseline_never_exposes_tools_and_rejects_tool_calls(self):
        provider = GLMProvider(self.settings)
        with patch("rtlflow.providers.urllib.request.urlopen", return_value=reply(calls=[tool()])) as http:
            with self.assertRaises(GenerationError):
                provider.generate("and2", initial_messages(TASKS["and2"], "Baseline", RULES), trace_dir=self.directory)
        self.assertNotIn("tools", json.loads(http.call_args.args[0].data))
        self.assertEqual(self.trace()["metadata"]["tool_calls"], 0)

    def test_malicious_or_malformed_tool_calls_never_execute(self):
        variants = [
            [tool(name="bash")], [tool(path="../../data/project-rtl/tests/adapted/aes/tb_aes.v")],
            [tool(path="/etc/passwd")], [tool(path="references/chisel.md")],
            [tool(path="rules.md")], [tool(arguments="invalid json")],
            [tool(arguments=json.dumps({"path": "SKILL.md", "command": "env"}))],
            [tool(arguments=json.dumps({"path": ["SKILL.md"]}))],
            [tool(), tool()], [tool(identifier="../escape")], [tool(arguments="x" * 4097)],
            [tool(identifier=f"read_{i}") for i in range(5)],
        ]
        for calls in variants:
            with self.subTest(calls=calls), patch("rtlflow.providers.urllib.request.urlopen",
                                                return_value=reply(calls=calls)) as http, \
                    patch.object(SkillReader, "read") as read:
                with self.assertRaises(GenerationError):
                    self.generate()
                self.assertEqual(http.call_count, 1)
                read.assert_not_called()
                self.assertFalse(self.trace()["metadata"]["skill_loaded"])

    def test_requests_require_missing_documents_then_disable_tools(self):
        responses = [reply(calls=[tool(path, f"read_{i}")]) for i, path in
                     enumerate(SkillReader("verilog").paths)] + [reply("candidate")]
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=responses) as http:
            result = self.generate()
        bodies = [json.loads(call.args[0].data) for call in http.call_args_list]
        self.assertEqual([body['tool_choice'] for body in bodies], ['required'] * 3 + ['none'])
        allowed = [body['tools'][0]['function']['parameters']['properties']['path']['enum']
                   for body in bodies[:3]]
        self.assertEqual(allowed, [['SKILL.md'], ['rules.md', 'references/verilog.md'],
                                   ['references/verilog.md']])
        self.assertTrue(result.metadata['skill_loaded'])
        self.assertEqual(result.metadata['tool_calls'], 3)
        self.assertEqual(result.metadata['model_calls'], 4)

    def test_repeated_reads_are_rejected_before_or_after_complete_loading(self):
        for loaded in (['SKILL.md'], list(SkillReader('verilog').paths)):
            responses = [reply(calls=[tool(path, f'read_{i}')]) for i, path in enumerate(loaded)]
            responses.append(reply(calls=[tool(identifier='unexpected_reread')]))
            with self.subTest(loaded=loaded), patch('rtlflow.providers.urllib.request.urlopen',
                                                  side_effect=responses) as http:
                with self.assertRaises(GenerationError) as error:
                    self.generate()
            self.assertEqual(http.call_count, len(loaded) + 1)
            self.assertEqual(error.exception.code, 'invalid_response')
            self.assertEqual(error.exception.metadata['tool_calls'], len(loaded))
            self.assertEqual(error.exception.metadata['skill_loaded'], len(loaded) == 3)

    def test_turn_budget_stops_after_reads_without_an_extra_request(self):
        responses = [reply(calls=[tool(path, f'read_{i}')]) for i, path in
                     enumerate(SkillReader('verilog').paths)]
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=responses) as http:
            with self.assertRaisesRegex(GenerationError, "max_agent_turns") as error:
                self.generate(max_agent_turns=3)
        self.assertEqual(http.call_count, 3)
        self.assertEqual(error.exception.metadata["model_calls"], 3)
        self.assertEqual(error.exception.metadata["tool_calls"], 3)
        self.assertEqual(error.exception.metadata["usage"]["total_tokens"], 90)
        self.assertTrue(error.exception.metadata["skill_loaded"])
        self.assertEqual(self.trace()["status"], "failed")

    def test_http_failure_keeps_prior_usage_and_skill_evidence_without_retry(self):
        failure = urllib.error.HTTPError("https://example.invalid", 401, KEY, {}, io.BytesIO(KEY.encode()))
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=[reply(calls=[tool()]), failure]) as http:
            with self.assertRaisesRegex(GenerationError, "HTTP 401") as error:
                self.generate()
        self.assertEqual(http.call_count, 2)
        self.assertEqual(error.exception.metadata["usage"]["total_tokens"], 30)
        self.assertIn("SKILL.md", error.exception.metadata["skill_documents"])
        self.assertNotIn(KEY, json.dumps(self.trace()))
        self.assertNotIn("PRIVATE_CHAIN_OF_THOUGHT", json.dumps(self.trace()))

    def test_arbitrary_protocol_metadata_is_not_persisted(self):
        for response in (reply("candidate", model=KEY), reply("candidate", stop=KEY)):
            with patch("rtlflow.providers.urllib.request.urlopen", return_value=response):
                with self.assertRaises(GenerationError) as error:
                    self.generate()
                self.assertNotIn(KEY, json.dumps(error.exception.metadata))
                self.assertNotIn(KEY, json.dumps(self.trace()))

    def test_interrupt_keeps_valid_partial_trace(self):
        with patch("rtlflow.providers.urllib.request.urlopen", side_effect=[reply(calls=[tool()]), KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                self.generate()
        trace = self.trace()
        self.assertEqual(trace["status"], "interrupted")
        self.assertEqual(trace["metadata"]["model_calls"], 2)
        self.assertIn("SKILL.md", trace["metadata"]["skill_documents"])
        self.assertEqual(len(trace["turns"]), 2)

    def test_incomplete_or_wrong_model_response_after_tool_load_is_not_accepted(self):
        for response in (reply("truncated", stop="length"), reply("wrong", model="other"),
                         reply(calls=[tool(identifier="read_1")])):
            with patch("rtlflow.providers.urllib.request.urlopen", side_effect=[reply(calls=[tool()]), response]) as http:
                with self.assertRaises(GenerationError):
                    self.generate()
                self.assertEqual(http.call_count, 2)
                self.assertEqual(self.trace()["status"], "failed")

    @unittest.skipUnless(HAS_ICARUS, "requires Icarus/vvp")
    def test_both_arms_share_pipeline_but_only_skill_loads_documents_each_attempt(self):
        reports, requests = {}, {}
        for group in ("Baseline", "Skill"):
            replay = SkillHTTPReplay([fixture("and2.broken.v"), fixture("and2.v"), fixture("and2.v")])
            settings = {**self.settings, "group": group, "max_repairs": 1, "max_refactors": 1}
            scores = [{'score': score, 'status': 'passed'} for score in (40, 40, 60)]
            with patch("rtlflow.providers.urllib.request.urlopen", side_effect=replay), \
                    patch("rtlflow.pipeline.score_readability", side_effect=scores):
                report = run_task(TASKS["and2"], GLMProvider(settings), settings, RULES, self.directory/group)
            reports[group] = report
            requests[group] = replay.requests
            self.assertEqual([a['phase'] for a in report['attempts']], ['initial', 'repair', 'refactor'])
            self.assertEqual(report['functional_status'], 'passed')
            self.assertEqual(report['stop_reason'], 'refactor_accepted')
            self.assertEqual(report['selected_attempt'], 2)
            self.assertEqual(report['provider_calls'], 3)
            self.assertEqual(report['model_calls'], 9 if group == 'Skill' else 3)
            self.assertEqual(report['schema_version'], 6)
            if group == 'Skill':
                self.assertEqual(report['rules_sha256'], report['skill_documents']['rules.md']['sha256'])
            for attempt in report['attempts']:
                metadata = attempt['generation_metadata']
                self.assertEqual(metadata['skill_loaded'], group == 'Skill')
                self.assertEqual(len(metadata['skill_documents']), 3 if group == 'Skill' else 0)
                trace = json.loads(Path(attempt['agent_trace_path']).read_text())
                first = trace['turns'][0]['request']
                self.assertEqual('tools' in first, group == 'Skill')
                self.assertFalse(any(m['role'] == 'tool' for m in first['messages']))
                prompt_text = Path(attempt['prompt_path']).read_text()
                self.assertNotIn('## 通用规则', prompt_text)
                prompt = json.loads(prompt_text)
                self.assertNotIn('rtl-readable', prompt[0]['content'])
                self.assertEqual('请调用 rtl-readable Skill' in prompt[1]['content'], group == 'Skill')
                self.assertEqual(first['messages'], prompt)
                self.assertEqual(trace['status'], 'passed')
            # Apart from Skill context and its read tool, all API parameters are identical.
            for body in replay.requests:
                parameters = {k: v for k, v in body.items() if k not in {'messages', 'tools', 'tool_choice'}}
                self.assertEqual(parameters, {k: v for k, v in requests['Baseline'][0].items()
                                              if k != 'messages'})
        for key in ('source_sha256', 'files_sha256', 'effective_max_repairs', 'effective_max_refactors',
                    'readability_score', 'repair_calls', 'refactor_calls'):
            self.assertEqual(reports['Baseline'][key], reports['Skill'][key])
        for body in requests['Baseline']:
            self.assertNotIn('read_skill', json.dumps(body))
            self.assertNotIn('请调用 rtl-readable Skill', json.dumps(body, ensure_ascii=False))
