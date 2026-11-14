// Dataset adaptation; upstream originals remain unchanged. See tasks.json.
// Dataset-authored integration test. The upstream RTL is not modified.
// Independently decode TX and drive RX; do not rely on a TX/RX loopback oracle.
`timescale 1ns/1ps
module project_wbuart32_tb;
  localparam BAUD = 16;
  reg clk = 0;
  always #5 clk = ~clk;
  reg reset = 1;
  reg cyc = 0, stb = 0, we = 0;
  reg [1:0] addr = 0;
  reg [31:0] wdata = 0;
  wire ack, stall;
  wire [31:0] rdata;
  reg rx = 1;
  wire tx, rx_int;
  integer base, j;
  reg [31:0] value;
  wbuart #(.INITIAL_SETUP(31'h40000010), .LGFLEN(4),
           .HARDWARE_FLOW_CONTROL_PRESENT(0)) dut (
    .i_clk(clk), .i_reset(reset), .i_wb_cyc(cyc), .i_wb_stb(stb),
    .i_wb_we(we), .i_wb_addr(addr), .i_wb_data(wdata), .i_wb_sel(4'hf),
    .o_wb_stall(stall), .o_wb_ack(ack), .o_wb_data(rdata),
    .i_uart_rx(rx), .o_uart_tx(tx), .i_cts_n(1'b0), .o_rts_n(),
    .o_uart_rx_int(rx_int), .o_uart_tx_int(),
    .o_uart_rxfifo_int(), .o_uart_txfifo_int()
  );

  task bus;
    input write;
    input [1:0] address;
    input [31:0] data;
    output [31:0] result;
    begin
      @(negedge clk);
      cyc = 1; stb = 1; we = write; addr = address; wdata = data;
      @(negedge clk);
      if (stall !== 0) $fatal(1, "unexpected Wishbone stall");
      stb = 0;
      while (ack !== 1) @(negedge clk);
      result = rdata;
      cyc = 0;
      @(negedge clk);
    end
  endtask

  task check_tx;
    input [7:0] expected;
    integer bitno;
    reg [7:0] observed;
    begin
      @(negedge tx);
      repeat (BAUD / 2) @(posedge clk);
      #1;
      if (tx !== 0) $fatal(1, "TX start bit");
      for (bitno = 0; bitno < 8; bitno = bitno + 1) begin
        repeat (BAUD) @(posedge clk);
        #1; observed[bitno] = tx;
      end
      repeat (BAUD) @(posedge clk);
      #1;
      if (tx !== 1 || observed !== expected)
        $fatal(1, "TX data/stop: expected %02x observed %02x", expected, observed);
    end
  endtask

  task send_rx;
    input [7:0] data;
    integer bitno;
    begin
      @(negedge clk); rx = 0;
      repeat (BAUD) @(negedge clk);
      for (bitno = 0; bitno < 8; bitno = bitno + 1) begin
        rx = data[bitno];
        repeat (BAUD) @(negedge clk);
      end
      rx = 1;
      repeat (BAUD) @(negedge clk);
    end
  endtask

  initial begin
    #2000000;
    $fatal(1, "integration watchdog");
  end

  initial begin
    repeat (5) @(negedge clk);
    reset = 0;
    repeat (500) @(negedge clk);
    bus(0, 0, 0, value);
    if (value !== 32'h40000010) $fatal(1, "setup readback");
    for (base = 0; base < 256; base = base + 8) begin
      fork
        begin : producer
          integer k;
          reg [31:0] ignored;
          for (k = 0; k < 8; k = k + 1) bus(1, 3, base + k, ignored);
        end
        begin : serial_monitor
          integer k;
          for (k = 0; k < 8; k = k + 1) check_tx(base + k);
        end
      join
      repeat (BAUD) @(negedge clk);
    end
    for (base = 0; base < 256; base = base + 8) begin
      for (j = 0; j < 8; j = j + 1) send_rx(base + j);
      repeat (BAUD * 2) @(negedge clk);
      if (rx_int !== 1) $fatal(1, "RX data interrupt missing");
      for (j = 0; j < 8; j = j + 1) begin
        bus(0, 2, 0, value);
        if (value[12:8] !== 0 || value[7:0] !== ((base + j) & 255))
          $fatal(1, "RX data/status: expected %02x observed %08x", base+j, value);
      end
      repeat (4) @(negedge clk);
      if (rx_int !== 0) $fatal(1, "RX interrupt did not clear");
    end
    $display("PROJECT_RTL_PASS wbuart32 tx=256 rx=256");
    $finish;
  end
endmodule
