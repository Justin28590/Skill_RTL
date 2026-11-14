"""Call the GLM API or explicitly replay offline fixtures for regression tests."""

from copy import deepcopy
from dataclasses import dataclass, field
import http.client
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from .skill_tools import SkillReader, agent_turn_limit


class GenerationError(RuntimeError):
    def __init__(self, message, metadata=None, *, code="generation_error"):
        super().__init__(message)
        self.metadata = metadata or {}
        self.code = code


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


MAX_RESPONSE_BYTES = 32 * 1024 * 1024


def read_completion(response, *, model, started, timeout, on_chunk):
    """Assemble public SSE deltas only. Never retain reasoning_content or raw events.

    JSON responses remain supported for non-streaming endpoints. A stream must
    finish explicitly; EOF/timeout must never turn a partial project into a candidate.
    """
    maximum = MAX_RESPONSE_BYTES
    headers = getattr(response, "headers", {})
    if "text/event-stream" not in headers.get("Content-Type", "").lower():
        raw = response.read(maximum + 1)
        if len(raw) > maximum:
            raise GenerationError("模型响应超过大小上限", code="response_too_large")
        return json.loads(raw)
    content, calls, usage = [], {}, {}
    stop = None
    seen_model = None
    size = 0
    event = []
    # Bound wire input, including ignored reasoning and heartbeat events.
    while True:
        if time.monotonic() - started >= timeout:
            raise TimeoutError()
        line = response.readline(maximum - size + 1)
        size += len(line)
        if size > maximum:
            raise GenerationError("模型流式响应超过大小上限", code="response_too_large")
        if not line:
            raise GenerationError("模型流式响应中断：未收到 [DONE]；不接受部分源码", code="stream_incomplete")
        line = line.decode("utf-8").rstrip("\r\n")
        if line:
            if line.startswith("data:"):
                event.append(line[5:].lstrip(" "))
            continue
        if not event:  # SSE comments/heartbeats are not model output.
            continue
        data = "\n".join(event)
        event = []
        if data == "[DONE]":
            if stop is None or seen_model is None:
                raise GenerationError("模型流式响应缺少结束原因或模型标识", code="stream_incomplete")
            message = {"content": "".join(content)}
            if calls:
                message["tool_calls"] = [calls[index] for index in sorted(calls)]
            return {"model": seen_model, "choices": [{"message": message, "finish_reason": stop}], "usage": usage}
        payload = json.loads(data)
        if not isinstance(payload, dict) or "error" in payload:
            raise GenerationError("模型流式响应格式无效或返回错误", code="invalid_response")
        response_model = payload.get("model")
        if response_model is not None:
            if response_model != model:
                raise GenerationError("GLM 返回的模型与请求不一致；不接受自动换模", code="model_mismatch")
            seen_model = response_model
        if payload.get("usage"):
            usage = payload["usage"]
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise ValueError("invalid_stream_choices")
        for choice in choices:
            if choice.get("index", 0) != 0 or stop is not None:
                raise ValueError("invalid_stream_choice")
            delta = choice.get("delta", {})
            text = delta.get("content")
            if text is not None:
                if not isinstance(text, str):
                    raise ValueError("invalid_content_delta")
                content.append(text)
            for fragment in delta.get("tool_calls") or []:
                index = fragment["index"]
                if type(index) is not int or not 0 <= index < 4:
                    raise ValueError("invalid_tool_index")
                call = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                if fragment.get("type", "function") != "function":
                    raise ValueError("invalid_tool_type")
                if "id" in fragment:
                    call["id"] += fragment["id"]
                function = fragment.get("function", {})
                for key in ("name", "arguments"):
                    if key in function:
                        call["function"][key] += function[key]
            if choice.get("finish_reason") is not None:
                stop = choice["finish_reason"]
        on_chunk(usage)


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
        self.timeout = settings.get("api_timeout_seconds", 600)
        self.stream = settings.get("api_stream", True)
        if type(self.stream) is not bool:
            raise ValueError("api_stream 必须为布尔值")
        self.temperature = settings.get("temperature", 1.0)
        self.max_tokens = settings.get("max_tokens")
        if self.max_tokens is not None and (type(self.max_tokens) is not int or self.max_tokens <= 0):
            raise ValueError("max_tokens 必须为正整数或 null；省略/null 表示使用服务端默认值")
        self.max_agent_turns = agent_turn_limit(settings)

    def request_body(self, messages, skill=None):
        body = {
            "model": self.model, "messages": messages,
            "temperature": self.temperature,
            "thinking": {"type": "enabled"}, "reasoning_effort": self.thinking,
        }
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        if self.stream:
            body.update(stream=True, stream_options={"include_usage": True})
        if skill is not None:
            definition = skill.definition()
            if not skill.complete:
                definition["function"]["parameters"]["properties"]["path"]["enum"] = [
                    path for path in skill.available_paths if path not in skill.documents]
            body["tools"] = [definition]
            # Each stage must load its own documents before answering. Once loaded,
            # disable further reads instead of spending the budget re-reading them.
            body["tool_choice"] = "none" if skill.complete else "required"
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
            "usage_complete": False, "usage_observed_calls": 0,
            "api_stream": self.stream, "api_timeout_seconds": self.timeout,
            "max_tokens_requested": self.max_tokens,
            "token_limit_mode": "server_default" if self.max_tokens is None else "explicit",
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
        turn = None
        try:
            for index in range(limit):
                # A failed request must not inherit the previous tool turn's finish reason.
                metadata.pop("stop_reason", None)
                metadata.pop("response_model", None)
                metadata["usage_complete"] = False
                body = self.request_body(conversation, skill)
                turn = {"request": deepcopy(body), "status": "running", "stream_chunks": 0,
                        "usage": {}, "usage_complete": False}
                request_started = time.monotonic()
                last_checkpoint = last_progress = request_started

                def record_usage(raw_usage):
                    # Streaming usage is cumulative within a request, not additive
                    # per chunk. Preserve observed counters even if [DONE] is lost.
                    if raw_usage is None:
                        return
                    if not isinstance(raw_usage, dict):
                        raise ValueError("invalid_usage")
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                        value = raw_usage.get(key)
                        if type(value) is int and value >= 0:
                            usage[key] = usage.get(key, 0) + value - turn["usage"].get(key, 0)
                            turn["usage"][key] = value
                    if len(turn["usage"]) == 3 and not turn["usage_complete"]:
                        turn["usage_complete"] = True
                        metadata["usage_observed_calls"] += 1
                    metadata["usage_complete"] = metadata["usage_observed_calls"] == metadata["model_calls"]

                def on_chunk(raw_usage):
                    nonlocal last_checkpoint, last_progress
                    record_usage(raw_usage)
                    now = time.monotonic()
                    turn["stream_chunks"] += 1
                    turn.setdefault("first_chunk_seconds", round(now - request_started, 4))
                    turn["elapsed_seconds"] = round(now - request_started, 4)
                    if now - last_checkpoint >= 1 or turn["stream_chunks"] == 1:
                        checkpoint()
                        last_checkpoint = now
                    if now - last_progress >= 30:
                        print(f"[{task_id}] 已接收 {turn['stream_chunks']} 段，"
                              f"等待完整响应（{now - request_started:.0f}s）", file=sys.stderr, flush=True)
                        last_progress = now

                trace["turns"].append(turn)
                checkpoint()
                request = urllib.request.Request(
                    self.url, data=json.dumps(body).encode(),
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    method="POST",
                )
                metadata["model_calls"] += 1
                checkpoint()
                print(f"[{task_id}] {metadata['agent_mode']} HTTP {index + 1}/{limit} "
                      f"等待模型（超时 {self.timeout}s）", file=sys.stderr, flush=True)
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = read_completion(response, model=self.model, started=request_started,
                                              timeout=self.timeout, on_chunk=on_chunk)
                turn["elapsed_seconds"] = round(time.monotonic() - request_started, 4)
                choice = payload["choices"][0]
                response_model = payload.get("model")
                stop = choice.get("finish_reason")
                # Do not persist arbitrary endpoint strings in protocol metadata.
                metadata.update(response_model=self.model if response_model == self.model else "<mismatch>",
                                stop_reason=stop if stop in ("stop", "length", "tool_calls") else "<invalid>")
                record_usage(payload.get("usage"))
                turn["stop_reason"] = metadata["stop_reason"]
                if metadata["response_model"] != self.model:
                    raise GenerationError("GLM 返回的模型与请求不一致；不接受自动换模", code="model_mismatch")
                stop = metadata["stop_reason"]
                message = choice["message"]
                text = message.get("content")
                if isinstance(text, str):
                    turn["response"] = {"role": "assistant", "content": text}
                if stop == "length":
                    limit = ("未显式设置 max_tokens，使用服务端默认值" if self.max_tokens is None
                             else f"请求 max_tokens={self.max_tokens}")
                    raise GenerationError(
                        f"模型输出被截断（{limit}）；请核对端点默认值、模型输出/上下文上限及推理预算。"
                        "省略 max_tokens 不代表无限输出；不接受部分源码。", code="output_truncated")
                if stop == "tool_calls" and skill is not None and not skill.complete:
                    allowed = body["tools"][0]["function"]["parameters"]["properties"]["path"]["enum"]
                    calls = self.tool_calls(message, allowed, used_ids)
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
                    turn["status"] = "passed"
                    continue
                if stop != "stop" or message.get("tool_calls"):
                    raise GenerationError("GLM 未正常完成文本输出", code="invalid_response")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("empty_content")
                turn["response"] = {"role": "assistant", "content": text}
                if skill is not None and not skill.complete:
                    raise GenerationError("模型未完成 Skill 必读文档加载；不接受本阶段结果", code="skill_not_loaded")
                turn["status"] = "passed"
                trace["status"] = "passed"
                checkpoint()
                return Generation(text, usage, metadata)
            raise GenerationError("Skill 工具循环达到 max_agent_turns 上限", code="agent_turn_limit")
        except KeyboardInterrupt:
            trace.update(status="interrupted", error="KeyboardInterrupt")
            raise
        except GenerationError as exc:
            metadata["error_code"] = exc.code
            exc.metadata = metadata
            trace.update(status="failed", error=str(exc), error_code=exc.code)
            raise
        except urllib.error.HTTPError as exc:
            # Do not log bodies, headers or credentials returned by an endpoint.
            error = f"模型 API HTTP {exc.code}"
            metadata.update(error_code="http_error", http_status=exc.code)
            trace.update(status="failed", error=error, error_code="http_error")
            raise GenerationError(error, metadata, code="http_error") from exc
        except (OSError, http.client.HTTPException, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            timed_out = isinstance(exc, TimeoutError) or (
                isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError))
            code = ("api_timeout" if timed_out else "transport_error"
                    if isinstance(exc, (OSError, http.client.HTTPException)) else "invalid_response")
            error = (f"模型 API 超时（api_timeout_seconds={self.timeout}）；未收到完整响应，用量可能未知。"
                     "请检查网络/服务状态或调整请求超时；未自动重试。" if timed_out else
                     f"模型请求、Skill 工具或响应格式无效：{type(exc).__name__}")
            metadata["error_code"] = code
            trace.update(status="failed", error=error, error_code=code)
            raise GenerationError(error, metadata, code=code) from exc
        finally:
            if turn is not None:
                turn["elapsed_seconds"] = round(time.monotonic() - request_started, 4)
                if turn["status"] == "running":
                    turn["status"] = trace["status"]
                    if "error_code" in trace:
                        turn["error_code"] = trace["error_code"]
            checkpoint()
