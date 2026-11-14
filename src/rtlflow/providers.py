"""Call the GLM API or explicitly replay offline fixtures for regression tests."""

from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from .skill_tools import SkillReader, agent_turn_limit


class GenerationError(RuntimeError):
    def __init__(self, message, metadata=None):
        super().__init__(message)
        self.metadata = metadata or {}


@dataclass
class Generation:
    text: str
    usage: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


def extract_rtl(text, language="verilog"):
    from .languages import language_of

    language_of({"language": language})
    tags = "scala|chisel" if language == "chisel" else "verilog|systemverilog|sv"
    blocks = re.findall(rf"```(?:{tags})?[ \t]*\n(.*?)```", text,
                        flags=re.DOTALL | re.IGNORECASE)
    if "```" in text:
        if len(blocks) != 1 or text.count("```") != 2:
            raise GenerationError("模型输出必须为纯源码或唯一的目标语言代码块")
        text = blocks[0]
    text = text.strip()
    if language == "chisel":
        if not text or not re.search(r"\bclass\s+Candidate\b", text):
            raise GenerationError("Chisel 响应必须包含无包声明、无参的 Candidate 类")
    elif not text or not re.search(r"\bmodule\b", text) or not re.search(r"\bendmodule\b", text):
        raise GenerationError("模型响应中缺少完整 module/endmodule")
    return text + "\n"


class MockProvider:
    name = "mock"
    model = "offline-fixture-replay"

    def __init__(self, manifest):
        self.manifest = Path(manifest).resolve()
        self.responses = json.loads(self.manifest.read_text())
        self.calls = {}

    def generate(self, task_id, messages, *, skill=None, trace_dir=None):
        # Offline fixtures do not simulate autonomous Skill loading.
        paths = self.responses.get(task_id)
        if not paths:
            raise GenerationError(f"无离线响应：{task_id}")
        index = self.calls.get(task_id, 0)
        self.calls[task_id] = index + 1
        path = self.manifest.parent / paths[min(index, len(paths) - 1)]
        try:
            return Generation(path.read_text())
        except OSError as exc:
            raise GenerationError(f"无法读取离线响应：{path.name}") from exc


class GLMProvider:
    """Bounded GLM Skill tool loop; no automatic retries or reasoning-text export."""

    name = "glm"

    def __init__(self, settings):
        self.model = settings.get("model", "glm-5.3")
        self.thinking = settings.get("thinking", "high")
        if self.thinking not in ("low", "high", "max"):
            raise ValueError("GLM thinking 必须为 low/high/max")
        key_env = settings.get("api_key_env", "GLM_API_KEY")
        base_env = settings.get("base_url_env", "GLM_BASE_URL")
        self.api_key = os.environ.get(key_env, "").strip()
        base = os.environ.get(base_env, "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        parsed = urllib.parse.urlparse(base)
        if (parsed.scheme not in {"https", "http"} or not parsed.netloc
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError(f"{base_env} 必须为不含凭据、查询参数的 HTTP(S) API 根地址")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("GLM model 必须为非空字符串")
        if not self.api_key:
            raise ValueError(f"请设置 API 密钥环境变量 {key_env}；不会自动降级为 mock")
        self.url = base + "/chat/completions"
        self.timeout = settings.get("api_timeout_seconds", 120)
        self.temperature = settings.get("temperature", 1.0)
        self.max_tokens = settings.get("max_tokens", 8192)
        self.max_agent_turns = agent_turn_limit(settings)

    def request_body(self, messages, skill=None):
        body = {
            "model": self.model, "messages": messages,
            "temperature": self.temperature, "max_tokens": self.max_tokens,
            "thinking": {"type": "enabled"}, "reasoning_effort": self.thinking,
        }
        if skill is not None:
            body["tools"] = [skill.definition()]
            body["tool_choice"] = "auto"
        return body

    @staticmethod
    def tool_calls(message, allowed_paths, used_ids):
        calls = message.get("tool_calls")
        if not isinstance(calls, list) or not 1 <= len(calls) <= 4:
            raise ValueError("invalid_tool_call_count")
        normalized = []
        ids = set(used_ids)
        for call in calls:
            identifier = call["id"]
            function = call["function"]
            if (call.get("type") != "function" or function.get("name") != "read_skill"
                    or not isinstance(identifier, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier) or identifier in ids):
                raise ValueError("invalid_tool_call")
            arguments = function["arguments"]
            if not isinstance(arguments, str) or len(arguments) > 4096:
                raise ValueError("invalid_tool_arguments")
            args = json.loads(arguments)
            if (not isinstance(args, dict) or set(args) != {"path"}
                    or not isinstance(args["path"], str) or args["path"] not in allowed_paths):
                raise ValueError("tool_path_not_allowed")
            ids.add(identifier)
            normalized.append({"id": identifier, "type": "function", "function": {
                "name": "read_skill", "arguments": json.dumps(args, ensure_ascii=False),
            }})
        return normalized

    def generate(self, task_id, messages, *, skill=None, trace_dir=None):
        # Never inherit a previous generation's loaded-document flags, even if a caller
        # accidentally reuses its reader. Each candidate must have its own tool evidence.
        skill = SkillReader(skill.language) if skill is not None else None
        conversation = deepcopy(messages)
        limit = self.max_agent_turns if skill is not None else 1
        usage = {}
        metadata = {
            "provider": self.name, "model": self.model, "model_calls": 0,
            "reasoning_effort_requested": self.thinking,
            "agent_mode": "skill_tools" if skill is not None else "direct",
            "max_agent_turns": limit, "tool_calls": 0,
            "skill_loaded": False, "skill_documents": {}, "usage": usage,
        }
        trace = {"schema_version": 1, "task_id": task_id, "status": "running", "turns": []}
        if trace_dir is not None:
            metadata["agent_trace_path"] = str(Path(trace_dir) / "agent_trace.json")

        def checkpoint():
            if skill is not None:
                metadata["skill_loaded"] = skill.complete
                metadata["skill_documents"] = deepcopy(skill.documents)
            trace["metadata"] = metadata
            if trace_dir is not None:
                # Only constructed public requests and sanitized replies; never HTTP headers
                # or reasoning_content. Replace atomically so interruption keeps valid JSON.
                path = Path(metadata["agent_trace_path"])
                temporary = path.with_suffix(".json.tmp")
                temporary.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n")
                temporary.replace(path)

        used_ids = set()
        try:
            for _ in range(limit):
                body = self.request_body(conversation, skill)
                turn = {"request": deepcopy(body)}
                trace["turns"].append(turn)
                checkpoint()
                request = urllib.request.Request(
                    self.url, data=json.dumps(body).encode(),
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    method="POST",
                )
                metadata["model_calls"] += 1
                checkpoint()
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                choice = payload["choices"][0]
                response_model = payload.get("model")
                stop = choice.get("finish_reason")
                # Do not persist arbitrary endpoint strings in protocol metadata.
                metadata.update(response_model=self.model if response_model == self.model else "<mismatch>",
                                stop_reason=stop if stop in ("stop", "length", "tool_calls") else "<invalid>")
                # Whitelist usage counters; arbitrary endpoint fields are not exported.
                turn_usage = {}
                raw_usage = payload.get("usage") or {}
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    value = raw_usage.get(key)
                    if type(value) is int and value >= 0:
                        turn_usage[key] = value
                        usage[key] = usage.get(key, 0) + value
                turn["usage"] = turn_usage
                if metadata["response_model"] != self.model:
                    raise GenerationError("GLM 返回的模型与请求不一致；不接受自动换模", metadata)
                stop = metadata["stop_reason"]
                if stop == "length":
                    raise GenerationError("模型输出被截断；请检查 max_tokens", metadata)
                message = choice["message"]
                text = message.get("content")
                if stop == "tool_calls" and skill is not None:
                    calls = self.tool_calls(message, skill.available_paths, used_ids)
                    assistant = {"role": "assistant", "content": text if isinstance(text, str) else None,
                                 "tool_calls": calls}
                    turn["response"] = assistant
                    conversation.append(assistant)
                    turn["tool_results"] = []
                    checkpoint()
                    for call in calls:
                        used_ids.add(call["id"])
                        metadata["tool_calls"] += 1
                        document = skill.read(json.loads(call["function"]["arguments"])["path"])
                        result = {"role": "tool", "tool_call_id": call["id"],
                                  "content": json.dumps(document, ensure_ascii=False)}
                        turn["tool_results"].append(result)
                        conversation.append(result)
                        checkpoint()
                    continue
                if stop != "stop" or message.get("tool_calls"):
                    raise GenerationError("GLM 未正常完成文本输出", metadata)
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("empty_content")
                turn["response"] = {"role": "assistant", "content": text}
                if skill is not None and not skill.complete:
                    raise GenerationError("模型未完成 Skill 必读文档加载；不接受未使用 Skill 的候选", metadata)
                trace["status"] = "passed"
                checkpoint()
                return Generation(text, usage, metadata)
            raise GenerationError("Skill 工具循环达到 max_agent_turns 上限", metadata)
        except KeyboardInterrupt:
            trace.update(status="interrupted", error="KeyboardInterrupt")
            raise
        except GenerationError as exc:
            trace.update(status="failed", error=str(exc))
            raise
        except urllib.error.HTTPError as exc:
            # Do not log bodies, headers or credentials returned by an endpoint.
            error = f"模型 API HTTP {exc.code}"
            trace.update(status="failed", error=error)
            raise GenerationError(error, metadata) from exc
        except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            error = f"模型请求、Skill 工具或响应格式无效：{type(exc).__name__}"
            trace.update(status="failed", error=error)
            raise GenerationError(error, metadata) from exc
        finally:
            checkpoint()
