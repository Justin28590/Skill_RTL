"""Skill routing/docs contracts and real-tool checks of the HDL examples.

Chisel build/integration coverage lives in test_chisel.py (explicit opt-in).
"""

from pathlib import Path
import re
import shutil
import tempfile
import unittest

from helpers import HAS_ICARUS, ROOT, TemporaryTestCase
from rtlflow.project_dataset import output_verdict
from rtlflow.verify import run_command

SKILL = ROOT / "skills/rtl-readable"


class SkillDocumentTests(unittest.TestCase):
    def test_frontmatter_routes_all_three_languages(self):
        text = (SKILL / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        fields = dict(line.split(": ", 1) for line in frontmatter.strip().splitlines())
        self.assertEqual(fields["name"], SKILL.name)
        self.assertLessEqual(len(fields["description"]), 1024)
        for language in ("Verilog", "SystemVerilog", "Chisel"):
            self.assertIn(language, fields["description"])

    def test_relative_document_links_exist(self):
        files = list(SKILL.rglob("*.md"))
        for language in ("verilog", "systemverilog", "chisel"):
            with self.subTest(language=language):
                self.assertTrue((SKILL / f"references/{language}.md").is_file())
        for path in files:
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text()):
                if "://" in target or target.startswith("#"):
                    continue
                with self.subTest(document=path.name, target=target):
                    self.assertTrue((path.parent / target.split("#", 1)[0]).exists())

    def test_skill_directory_is_portable_without_repository_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            installed = Path(temporary) / 'rtl-readable'
            shutil.copytree(SKILL, installed)
            self.assertTrue((installed / 'README.md').is_file())
            for document in installed.rglob('*.md'):
                for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', document.read_text()):
                    if '://' in target or target.startswith('#'):
                        continue
                    resolved = (document.parent / target.split('#', 1)[0]).resolve()
                    with self.subTest(document=document.name, target=target):
                        self.assertTrue(resolved.is_relative_to(installed.resolve()))
                        self.assertTrue(resolved.exists())

    def test_runtime_guidance_does_not_embed_evaluator_protocol(self):
        documents = [SKILL / 'SKILL.md', SKILL / 'rules.md', *sorted((SKILL / 'references').glob('*.md'))]
        for document in documents:
            content = document.read_text()
            for evaluator_detail in ('read_skill', 'Baseline', 'max_agent_turns', 'RTLFlowMain',
                                     'static-heuristic-v1', 'static-sv-heuristic-v1', 'static-chisel-heuristic-v1',
                                     'configs/glm.json', 'run.py', 'schema_version', '128文件', '2 MB'):
                with self.subTest(document=document.name, detail=evaluator_detail):
                    self.assertNotIn(evaluator_detail, content)

    def test_language_guidance_is_routed_to_references(self):
        text = (SKILL / "SKILL.md").read_text()
        for language, tag in (("verilog", "verilog"), ("systemverilog", "systemverilog"),
                              ("chisel", "scala")):
            with self.subTest(language=language):
                target = f"references/{language}.md"
                self.assertIn(f"]({target})", text)
                document = (SKILL / target).read_text()
                self.assertIn("](../SKILL.md)", document)
                self.assertIn("](../rules.md)", document)
                self.assertIn(f"```{tag}\n", document)
                self.assertNotIn(f"```{tag}\n", text)


class HDLExampleChecks:
    def check_example(self, module, testbench):
        document = (SKILL / f"references/{self.language}.md").read_text()
        blocks = re.findall(rf"```{self.language}\n(.*?)```", document, flags=re.DOTALL)
        matching = [code for code in blocks if re.search(rf"\bmodule\s+{module}\s*\(", code)]
        self.assertEqual(len(matching), 1)
        rtl_path = self.directory / f"{module}{self.extension}"
        rtl_path.write_text(matching[0])
        if self.language == "verilog":
            dialect = run_command([
                "iverilog", "-g2005", "-Wall", "-s", module,
                "-o", str(self.directory / "dialect.vvp"), str(rtl_path),
            ], self.directory, "dialect-compile", 10)
            self.assertEqual(dialect["status"], "passed", dialect)
        tb_path = self.directory / "independent_tb.sv"
        tb_path.write_text(testbench)
        # Trusted documentation snippets are not model candidates or dataset tasks.
        binary = self.directory / "example.vvp"
        compiled = run_command(["iverilog", "-g2012", "-Wall", "-s", "tb", "-o", binary,
                                rtl_path, tb_path], self.directory, "compile", 10)
        self.assertEqual(compiled["status"], "passed", compiled)
        simulation = run_command(["vvp", "-n", binary], self.directory, "simulation", 10)
        self.assertEqual(simulation["status"], "passed", simulation)
        logs = "\n".join(Path(simulation[key]).read_text() for key in ("stdout_log", "stderr_log"))
        verdict = output_verdict({"required_output": [{"regex": "(?m)^RTL_BENCH_PASS$", "min_count": 1}],
                                  "forbidden_output": ["(?i)error|fatal|failed"]}, logs)
        self.assertTrue(verdict["passed"], logs)

    def test_add_with_carry_exhaustive(self):
        self.check_example("add_with_carry", """
module tb;
    reg [7:0] operand_a, operand_b;
    wire [8:0] sum;
    integer a, b;
    add_with_carry dut (.operand_a(operand_a), .operand_b(operand_b), .sum(sum));
    initial begin
        for (a = 0; a < 256; a = a + 1) begin
            for (b = 0; b < 256; b = b + 1) begin
                operand_a = a;
                operand_b = b;
                #1;
                if (sum !== a + b) $fatal(1, "sum or carry mismatch");
            end
        end
        $display("RTL_BENCH_PASS");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1, "watchdog");
    end
endmodule
""")

    def test_register_reset_priority_hold_and_cycle(self):
        self.check_example("enabled_register", """
module tb;
    reg clk, rst, enable;
    reg [7:0] data_in;
    wire [7:0] data_out;
    integer value;
    enabled_register dut (
        .clk(clk), .rst(rst), .enable(enable), .data_in(data_in), .data_out(data_out)
    );
    initial begin
        clk = 0; rst = 1; enable = 1; data_in = 8'ha5;
        #1; clk = 1; #1;
        if (data_out !== 0) $fatal(1, "reset must override enable");
        clk = 0; rst = 0; data_in = 8'h5a;
        #1; clk = 1; #1;
        if (data_out !== 8'h5a) $fatal(1, "capture latency mismatch");
        clk = 0; rst = 1; data_in = 8'hff;
        #1;
        if (data_out !== 8'h5a) $fatal(1, "reset must be synchronous");
        clk = 1; #1;
        if (data_out !== 0) $fatal(1, "reset failed");
        clk = 0; rst = 0;
        for (value = 0; value < 256; value = value + 1) begin
            enable = 1; data_in = value;
            #1; clk = 1; #1;
            if (data_out !== value) $fatal(1, "capture failed");
            clk = 0; enable = 0; data_in = ~value;
            #1; clk = 1; #1;
            if (data_out !== value) $fatal(1, "hold failed");
            clk = 0;
        end
        rst = 1;
        #1; clk = 1; #1;
        if (data_out !== 0) $fatal(1, "disabled reset failed");
        $display("RTL_BENCH_PASS");
        $finish;
    end
    initial begin
        #5000;
        $fatal(1, "watchdog");
    end
endmodule
""")


@unittest.skipUnless(HAS_ICARUS, "Icarus Verilog/vvp required for Verilog example checks")
class VerilogExampleTests(HDLExampleChecks, TemporaryTestCase):
    language = "verilog"
    extension = ".v"


@unittest.skipUnless(HAS_ICARUS, "Icarus Verilog/vvp required for SV example checks")
class SystemVerilogExampleTests(HDLExampleChecks, TemporaryTestCase):
    language = "systemverilog"
    extension = ".sv"
