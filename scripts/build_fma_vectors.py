#!/usr/bin/env python3
"""Independent binary32 fused multiply-add oracle, using exact rational arithmetic.

No host float arithmetic, reference HDL, SoftFloat or upstream vectors are used.
Regenerates only the dataset-authored black-box testbench, not reference RTL.
"""
from fractions import Fraction
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]


def pow2(e):
    return Fraction(1 << e) if e >= 0 else Fraction(1, 1 << -e)


def fields(bits):
    return bits >> 31, (bits >> 23) & 255, bits & 0x7fffff


def finite(bits):
    sign, exp, frac = fields(bits)
    return (-1 if sign else 1) * ((1 << 23) | frac if exp else frac) * pow2(exp - 150 if exp else -149)


def rounded(value, mode, zero_sign=0):
    """Round exact finite value. Flags are NV,DZ,OF,UF,NX, tininess AFTER rounding."""
    if not value:
        return zero_sign << 31, 0
    sign = int(value < 0)
    value = abs(value)
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if value < pow2(exponent):
        exponent -= 1
    scale = max(exponent, -126) - 23
    scaled = value / pow2(scale)
    def quantize(number):
        q, rem = divmod(number.numerator, number.denominator)
        twice = rem * 2
        if mode == 0:  # nearest, ties to even
            q += int(twice > number.denominator or (twice == number.denominator and q & 1))
        elif mode == 4:  # nearest, ties away
            q += int(twice >= number.denominator)
        elif mode in (2, 3):
            q += int(bool(rem) and sign == (mode == 2))
        elif mode == 6:  # round-to-odd (jamming)
            if rem:
                q |= 1
        elif mode != 1:
            raise ValueError('unsupported rounding mode')
        return q, bool(rem)
    q, inexact = quantize(scaled)
    # IEEE tininess-after uses precision rounding with UNBOUNDED exponent,
    # before the additional loss of precision needed to encode a subnormal.
    unbounded_scale = pow2(exponent - 23)
    tiny_after = quantize(value / unbounded_scale)[0] * unbounded_scale < pow2(-126)
    if q >= (1 << 24):
        q >>= 1
        scale += 1
    out_exp = scale + 23
    if out_exp > 127:
        inf = mode in (0, 4) or (mode == 2 and sign) or (mode == 3 and not sign)
        return (sign << 31) | (0x7f800000 if inf else 0x7f7fffff), 5
    encoded_exp = 0 if q < (1 << 23) else out_exp + 127
    bits = (sign << 31) | (encoded_exp << 23) | (q & 0x7fffff)
    return bits, int(inexact) | (2 if inexact and tiny_after else 0)


def fma(a, b, c, op=0, mode=0):
    fs = [fields(x) for x in (a, b, c)]
    nan = [e == 255 and f != 0 for s, e, f in fs]
    snan = any(e == 255 and f and not (f & (1 << 22)) for s, e, f in fs)
    inf = [e == 255 and f == 0 for s, e, f in fs]
    zero = [e == 0 and f == 0 for s, e, f in fs]
    prod_sign = fs[0][0] ^ fs[1][0] ^ ((op >> 1) & 1)
    c_sign = fs[2][0] ^ (op & 1)
    bad_product = (inf[0] and zero[1]) or (inf[1] and zero[0])
    prod_inf = (inf[0] or inf[1]) and not any(nan[:2]) and not bad_product
    invalid = snan or bad_product or (prod_inf and inf[2] and prod_sign != c_sign)
    if any(nan) or invalid:
        return 0x7fc00000, 16 if invalid else 0
    if prod_inf or inf[2]:
        return ((prod_sign if prod_inf else c_sign) << 31) | 0x7f800000, 0
    value = finite(a) * finite(b) * (-1 if op & 2 else 1) + finite(c) * (-1 if op & 1 else 1)
    zero_sign = prod_sign if (zero[0] or zero[1]) and zero[2] and prod_sign == c_sign else int(mode == 2)
    return rounded(value, mode, zero_sign)


PREAMBLE = '''// Dataset-authored exact-rational vectors. Rebuild with scripts/build_fma_vectors.py.
`timescale 1ns/1ps
module tb;
  reg [32:0] a, b, c;
  reg [1:0] op;
  reg [2:0] mode;
  wire [32:0] result;
  wire [4:0] flags;
  mulAddRecFN #(.expWidth(8), .sigWidth(24)) dut (
    .control(1'b1), .op(op), .a(a), .b(b), .c(c), .roundingMode(mode),
    .out(result), .exceptionFlags(flags)
  );
  // Public recFN encoding/decoding, independently implemented in the testbench.
  function [32:0] recode;
    input [31:0] x;
    integer e, f, n;
    begin
      e = x[30:23]; f = x[22:0];
      if (e == 255) e = f ? 448 : 384;
      else if (e) e = e + 129;
      else if (f) begin
        n = 0;
        while (!(f & 32'h800000)) begin f = f << 1; n = n+1; end
        e = 130-n;
      end
      recode = {x[31],9'(e),23'(f)};
    end
  endfunction
  function [31:0] ieee;
    input [32:0] x;
    integer e;
    reg [23:0] f;
    begin
      e = x[31:23]; f = {1'b1,x[22:0]};
      if (x[31:29] == 0) ieee = {x[32],31'b0};
      else if (x[31:29] == 6) ieee = {x[32],8'hff,23'b0};
      else if (x[31:29] == 7) ieee = {x[32],8'hff,x[22:0]};
      else if (e < 130) ieee = {x[32],8'b0,23'(f >> (130-e))};
      else ieee = {x[32],8'(e-129),x[22:0]};
    end
  endfunction
  integer count = 0;
  task check;
    input [31:0] aa, bb, cc;
    input [1:0] operation;
    input [2:0] rounding;
    input [31:0] expected;
    input [4:0] expected_flags;
    begin
      a = recode(aa); b = recode(bb); c = recode(cc); op = operation; mode = rounding;
      #10;
      if (ieee(result) !== expected || flags !== expected_flags)
        $fatal(1, "ERROR FMA vector=%0d got=%h/%h expected=%h/%h", count,ieee(result),flags,expected,expected_flags);
      count = count+1;
    end
  endtask
  initial begin
'''


def vectors():
    directed = [
        (0x3f800001, 0x3f7ffffe, 0xbf800000),  # fused cancellation, -2^-46 not zero
        (0x3f800000, 0x3f800000, 0x33800000),  # halfway
        (0x3f800001, 0x3f800000, 0x33800000),
        (0x7f7fffff, 0x40000000, 0),
        (1, 0x3f000000, 0), (0x00800000, 0x3f7fffff, 0),
        (0x007fffff, 0x3f800000, 1),
        (0x80000000, 0x3f800000, 0x80000000), (0, 0xbf800000, 0),
        (0x7f800000, 0, 0), (0x7f800000, 0x3f800000, 0xff800000),
        (0x7fc12345, 0x3f800000, 0), (0x7f812345, 0x3f800000, 0),
        (0xff800000, 0xbf800000, 0x7f800000), (0, 0, 0x80000001),
    ]
    rng = random.Random(0xF32F4A)
    triples = directed + [tuple(rng.getrandbits(32) for _ in range(3)) for _ in range(128)]
    for a, b, c in triples:
        for op in range(4):
            for mode in (0, 1, 2, 3, 4, 6):
                yield a, b, c, op, mode, *fma(a, b, c, op, mode)


def build():
    rows = list(vectors())
    checks = ''.join(f"    check(32'h{a:08x},32'h{b:08x},32'h{c:08x},2'd{op},3'd{mode},32'h{out:08x},5'h{flags:02x});\n"
                     for a,b,c,op,mode,out,flags in rows)
    return PREAMBLE + checks + f'''    if (count != {len(rows)}) $fatal(1, "ERROR FMA check count");
    $display("MODERN_PASS fp32_fma vectors=%0d", count);
    $finish;
  end
endmodule
'''


if __name__ == '__main__':
    output = ROOT / 'data/project-rtl/tests/blackbox/modern/fp32_fma_tb.sv'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build())
    print(output)
