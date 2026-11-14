// Dataset-authored black-box scoreboard; no implementation-state probes.
`timescale 1ns/1ps
module systolic_case #(parameter N = 4)(output reg finished = 0);
  reg clk = 0;
  always #5 clk = ~clk;
  reg rst = 1, valid = 0;
  reg [N*N*8-1:0] a_bus = 0, b_bus = 0;
  wire [N*N*32-1:0] c_bus;
  wire result_valid;
  topSystolicArray #(.N(N)) dut (
    .i_clk(clk), .i_arst(rst), .i_a(a_bus), .i_b(b_bus),
    .i_validInput(valid), .o_c(c_bus), .o_validResult(result_valid)
  );
  integer a[0:N*N-1], b[0:N*N-1], expected[0:N*N-1];
  integer trial, i, j, k, cycle, checks = 0;
  reg [31:0] rng = 32'h92653589 + N;
  function [7:0] next_byte;
    input unused;
    begin
      rng = (rng ^ (rng << 13));
      rng = (rng ^ (rng >> 17));
      rng = (rng ^ (rng << 5));
      next_byte = rng[7:0];
    end
  endfunction
  task reset_array;
    begin
      @(negedge clk); rst = 1; valid = 0;
      #1;
      if (result_valid !== 0 || c_bus !== 0) $fatal(1, "ERROR asynchronous reset N=%0d", N);
      repeat (2) @(negedge clk);
      rst = 0;
    end
  endtask
  initial begin
    reset_array();
    // Cancel an in-flight transaction, then verify no stale completion survives.
    @(negedge clk); a_bus = '1; b_bus = '1; valid = 1;
    @(negedge clk); valid = 0;
    reset_array();
    repeat (3*N+3) begin
      @(negedge clk);
      if (result_valid !== 0) $fatal(1, "ERROR stale result after reset");
    end
    for (trial = 0; trial < 40; trial = trial + 1) begin
      for (i = 0; i < N; i = i + 1)
        for (j = 0; j < N; j = j + 1) begin
          a[i*N+j] = next_byte(0);
          b[i*N+j] = next_byte(0);
          case (trial)
            0: a[i*N+j] = 0;
            1: a[i*N+j] = (i == j);
            2: begin a[i*N+j] = 255; b[i*N+j] = 255; end
            3: begin a[i*N+j] = (j == (i+1)%N); b[i*N+j] = i*N+j; end
            4: begin a[i*N+j] = (i*37+j*19+128)%256; b[i*N+j] = (i*11+j*43+129)%256; end
          endcase
        end
      for (i = 0; i < N; i = i + 1)
        for (j = 0; j < N; j = j + 1) begin
          expected[i*N+j] = 0;
          for (k = 0; k < N; k = k + 1)
            expected[i*N+j] = expected[i*N+j] + a[i*N+k]*b[k*N+j];
        end
      @(negedge clk);
      for (i = 0; i < N*N; i = i + 1) begin
        a_bus[i*8 +: 8] = a[i]; b_bus[i*8 +: 8] = b[i];
      end
      valid = 1;
      @(posedge clk); #1;
      if (result_valid !== 0) $fatal(1, "ERROR early result at acceptance");
      @(negedge clk); valid = 0; a_bus = '1; b_bus = 0;
      for (cycle = 1; cycle <= 3*N-2; cycle = cycle + 1) begin
        @(posedge clk); #1;
        if (result_valid !== (cycle == 3*N-2))
          $fatal(1, "ERROR completion timing N=%0d cycle=%0d", N, cycle);
      end
      for (i = 0; i < N*N; i = i + 1)
        if (c_bus[i*32 +: 32] !== expected[i])
          $fatal(1, "ERROR matrix product N=%0d trial=%0d element=%0d got=%0d expected=%0d", N, trial, i, c_bus[i*32 +: 32], expected[i]);
      checks = checks + 1;
      repeat (4) begin
        @(posedge clk); #1;
        if (result_valid !== 0) $fatal(1, "ERROR repeated completion");
      end
    end
    $display("COMPUTE_PASS systolic_matmul N=%0d matrices=%0d", N, checks);
    finished = 1;
  end
endmodule

module tb;
  wire done3, done4, done8;
  systolic_case #(.N(3)) case3(done3);
  systolic_case #(.N(4)) case4(done4);
  systolic_case #(.N(8)) case8(done8);
  initial begin
    wait (done3 && done4 && done8);
    $finish;
  end
  initial begin #100000; $fatal(1, "ERROR systolic watchdog"); end
endmodule
