"""Test-only tiny projects, created in temporary storage; never selectable experiment cases."""
import atexit
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rtlflow.project import bundle_text
from rtlflow.providers import Generation, GenerationError

RULES = (ROOT / "skills/rtl-readable/rules.md").read_text()
HAS_ICARUS = bool(shutil.which("iverilog") and shutil.which("vvp"))
TEMP = tempfile.TemporaryDirectory(prefix="rtlflow-unit-only-")
atexit.register(TEMP.cleanup)
UNIT_ROOT = Path(TEMP.name)
TASKS = {}
BUNDLES = {}

for name, width, expression in (("and2", 1, "a & b"), ("add8", 8, "{1'b0,a} + {1'b0,b}")):
    output_width = 1 if name == "and2" else 9
    leaf = name + "_leaf"
    ports = f"input wire [{width-1}:0] a, b, output wire [{output_width-1}:0] y"
    top = f"// Unit-only hierarchy fixture.\nmodule {name}({ports});\n    {leaf} child(.a(a), .b(b), .y(y));\nendmodule\n"
    child = f"// Unit-only combinational fixture.\nmodule {leaf}({ports});\n    assign y = {expression};\nendmodule\n"
    files = {"top.v": top, "child.v": child}
    BUNDLES[name + ".v"] = bundle_text(files)
    BUNDLES[name + ".broken.v"] = bundle_text({**files, "child.v": child.replace(expression, "1'b0")})
    tb = UNIT_ROOT / (name + "_tb.v")
    tb.write_text(f'''module tb;
reg [{width-1}:0] a=0,b=0;
wire [{output_width-1}:0] y;
integer i,j;
{name} dut(.a(a),.b(b),.y(y));
initial begin
  for(i=0;i<4;i=i+1) for(j=0;j<4;j=j+1) begin
    a=i; b=j; #1;
    if(y !== ({expression})) $fatal(1,"AND truth table mismatch");
  end
  $display("UNIT_PROJECT_PASS"); $finish;
end
endmodule
''')
    TASKS[name] = {"id": name, "project": True, "module": name, "design_tops": [name], "dialect": "2005",
                   "contract_text": f"Unit-only {name}. Input a,b: {width} bits; output y: {output_width} bits. {expression}.",
                   "dataset_root": str(UNIT_ROOT), "candidate_testbench_files": [tb.name],
                   "testbench_tops": ["tb"], "dut_roots": ["tb.dut"], "include_dirs": [], "defines": [],
                   "simulation_timeout_seconds": 2,
                   "required_output": [{"regex": "UNIT_PROJECT_PASS", "min_count": 1}],
                   "forbidden_output": ["FATAL", "ERROR"],
                   "expected_ports": {"tb.dut": {"module": name, "ports": {
                       "a": {"direction": "input", "width": width}, "b": {"direction": "input", "width": width},
                       "y": {"direction": "output", "width": output_width}}}},
                   "dataset_provenance": {"dataset": "unit-only", "split": "pilot", "manifest_sha256": "0"*64}}


def fixture(name):
    return BUNDLES[name]


class SequenceProvider:
    name = "mock"
    model = "test-sequence"

    def __init__(self, responses):
        self.responses = responses
        self.messages = []
        self.skills = []

    def generate(self, task_id, messages, *, skill=None, trace_dir=None):
        index = len(self.messages)
        self.messages.append(messages)
        self.skills.append(skill)
        response = self.responses[min(index, len(self.responses) - 1)]
        if isinstance(response, GenerationError):
            raise response
        return Generation(response)


class SkillHTTPReplay:
    """Real HTTP adapter/tool loop, mocked model replies, no network."""
    def __init__(self, responses):
        self.responses = responses
        self.finals = 0
        self.requests = []

    def __call__(self, request, **kwargs):
        body = json.loads(request.data)
        self.requests.append(body)
        loaded = {json.loads(m["content"])["path"] for m in body["messages"] if m["role"] == "tool"}
        calls = []
        if "tools" in body:
            allowed = body["tools"][0]["function"]["parameters"]["properties"]["path"]["enum"]
            missing = [path for path in allowed if path not in loaded]
            calls = [{"id": f"read_{len(self.requests)}_{index}", "type": "function", "function": {
                "name": "read_skill", "arguments": json.dumps({"path": path})}}
                for index, path in enumerate(missing)]
        if calls:
            message, stop = {"content": None, "tool_calls": calls}, "tool_calls"
        else:
            message = {"content": self.responses[min(self.finals, len(self.responses) - 1)]}
            self.finals += 1
            stop = "stop"
        message["reasoning_content"] = "PRIVATE_REASONING_NOT_FOR_REPORTS"
        return io.BytesIO(json.dumps({"model": "glm-5.3", "choices": [{"message": message, "finish_reason": stop}],
            "usage": {"prompt_tokens": 22, "completion_tokens": 35, "total_tokens": 57}}).encode())


class TemporaryTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)


class ImplementationTestCase(TemporaryTestCase):
    """Unit-test the implementation/transport layer, not requirements orchestration.

    These historical tiny fixtures already have a TB. The public workflow is
    exercised separately by test_design_flow; this seam is test-only.
    """
    def setUp(self):
        super().setUp()
        from unittest.mock import patch
        from rtlflow.pipeline import _run_implementation
        controller = patch('rtlflow.pipeline.run_task', _run_implementation)
        controller.start()
        self.addCleanup(controller.stop)
