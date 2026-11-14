// Dataset-authored dual-port AXI memory scoreboard; no internal memory probes.
`timescale 1ns/1ps
`define RAM_PORT(P,I) \
 .s_axi_``P``_awid(awid[I]), .s_axi_``P``_awaddr(awaddr[I]), \
 .s_axi_``P``_awlen(awlen[I]), .s_axi_``P``_awsize(3'd2), .s_axi_``P``_awburst(2'd1), \
 .s_axi_``P``_awlock(1'b0), .s_axi_``P``_awcache(4'd0), .s_axi_``P``_awprot(3'd0), \
 .s_axi_``P``_awvalid(awvalid[I]), .s_axi_``P``_awready(awready[I]), \
 .s_axi_``P``_wdata(wdata[I]), .s_axi_``P``_wstrb(wstrb[I]), .s_axi_``P``_wlast(wlast[I]), \
 .s_axi_``P``_wvalid(wvalid[I]), .s_axi_``P``_wready(wready[I]), \
 .s_axi_``P``_bid(bid[I]), .s_axi_``P``_bresp(bresp[I]), .s_axi_``P``_bvalid(bvalid[I]), .s_axi_``P``_bready(bready[I]), \
 .s_axi_``P``_arid(arid[I]), .s_axi_``P``_araddr(araddr[I]), \
 .s_axi_``P``_arlen(arlen[I]), .s_axi_``P``_arsize(3'd2), .s_axi_``P``_arburst(2'd1), \
 .s_axi_``P``_arlock(1'b0), .s_axi_``P``_arcache(4'd0), .s_axi_``P``_arprot(3'd0), \
 .s_axi_``P``_arvalid(arvalid[I]), .s_axi_``P``_arready(arready[I]), \
 .s_axi_``P``_rid(rid[I]), .s_axi_``P``_rdata(rdata[I]), .s_axi_``P``_rresp(rresp[I]), \
 .s_axi_``P``_rlast(rlast[I]), .s_axi_``P``_rvalid(rvalid[I]), .s_axi_``P``_rready(rready[I])
module tb;
  reg [1:0] clk = 0, rst = 3;
  always #5 clk[0] = ~clk[0];
  always #7 clk[1] = ~clk[1];
  reg [3:0] awid[0:1], arid[0:1], wstrb[0:1];
  reg [11:0] awaddr[0:1], araddr[0:1];
  reg [7:0] awlen[0:1], arlen[0:1];
  reg [31:0] wdata[0:1];
  reg [1:0] awvalid=0, wvalid=0, wlast=0, bready=0, arvalid=0, rready=0;
  wire [1:0] awready, wready, bvalid, arready, rlast, rvalid;
  wire [3:0] bid[0:1], rid[0:1];
  wire [1:0] bresp[0:1], rresp[0:1];
  wire [31:0] rdata[0:1];
  axi_dp_ram #(.ADDR_WIDTH(12), .ID_WIDTH(4), .A_PIPELINE_OUTPUT(1), .B_PIPELINE_OUTPUT(0),
               .A_INTERLEAVE(1), .B_INTERLEAVE(1)) dut (
    .a_clk(clk[0]), .a_rst(rst[0]), .b_clk(clk[1]), .b_rst(rst[1]),
    `RAM_PORT(a,0), `RAM_PORT(b,1)
  );
  reg [7:0] expected[0:4095];
  integer read_beats[0:1], writes[0:1];
  integer round;
  // Static event selects avoid simulator sensitivity quirks on clk[p].
  task automatic drive(input integer p);
    if (p==0) @(negedge clk[0]); else @(negedge clk[1]);
  endtask
  task automatic sample(input integer p);
    if (p==0) @(posedge clk[0]); else @(posedge clk[1]);
  endtask
  task automatic write_burst(input integer p, address, beats, tag, masked_write);
    integer beat, lane;
    reg [31:0] data;
    reg [3:0] mask;
    begin
      drive(p); awaddr[p]=address; awlen[p]=beats-1; awid[p]=tag; awvalid[p]=1;
      sample(p); while (!awready[p]) sample(p);
      drive(p); awvalid[p]=0;
      for (beat=0; beat<beats; beat=beat+1) begin
        repeat ((beat+tag)%3) drive(p);
        data=32'hc3a56987 ^ (address*17011) ^ (beat*32'h0103070b) ^ (tag*32'h10203041);
        mask=masked_write ? ((beat+tag)%16) : 15;
        wdata[p]=data; wstrb[p]=mask; wlast[p]=(beat==beats-1); wvalid[p]=1;
        sample(p); while (!wready[p]) sample(p);
        for (lane=0; lane<4; lane=lane+1)
          if (mask[lane]) expected[address+beat*4+lane]=data[lane*8 +: 8];
        drive(p); wvalid[p]=0;
      end
      while (!bvalid[p]) drive(p);
      repeat (3) begin
        if (bvalid[p] !== 1 || bid[p] !== 4'(tag) || bresp[p] !== 0)
          $fatal(1,"ERROR scratchpad write response/backpressure");
        drive(p);
      end
      bready[p]=1; sample(p); drive(p); bready[p]=0;
      writes[p]=writes[p]+1;
    end
  endtask
  task automatic read_burst(input integer p, address, beats, tag);
    integer beat, lane;
    reg [31:0] want;
    begin
      drive(p); araddr[p]=address; arlen[p]=beats-1; arid[p]=tag; arvalid[p]=1;
      sample(p); while (!arready[p]) sample(p);
      drive(p); arvalid[p]=0;
      for (beat=0; beat<beats; beat=beat+1) begin
        while (!rvalid[p]) drive(p);
        for (lane=0; lane<4; lane=lane+1) want[lane*8 +: 8]=expected[address+beat*4+lane];
        repeat (2) begin
          if (rvalid[p] !== 1 || rdata[p] !== want || rid[p] !== 4'(tag) ||
              rresp[p] !== 0 || rlast[p] !== (beat==beats-1))
            $fatal(1,"ERROR scratchpad read port=%0d address=%h got=%h expected=%h",p,address+beat*4,rdata[p],want);
          drive(p);
        end
        rready[p]=1; sample(p); drive(p); rready[p]=0;
        read_beats[p]=read_beats[p]+1;
      end
    end
  endtask
  initial begin
    read_beats[0]=0; read_beats[1]=0; writes[0]=0; writes[1]=0;
    #100; @(negedge clk[0]); rst[0]=0; @(negedge clk[1]); rst[1]=0;
    // Disjoint simultaneous writes; every byte initialized via public AXI.
    for (round=0; round<8; round=round+1) begin
      fork
        write_burst(0,round*64,16,round,0);
        write_burst(1,2048+round*64,16,round+8,0);
      join
    end
    // Cross-port reads establish actual sharing, not two private memories.
    for (round=0; round<8; round=round+1) begin
      fork
        read_burst(1,round*64,16,round);
        read_burst(0,2048+round*64,16,round+8);
      join
    end
    for (round=0; round<8; round=round+1) begin
      fork
        write_burst(1,round*64,16,round+3,1);
        write_burst(0,2048+round*64,16,round+7,1);
      join
      // Concurrent reads on both ports.
      fork
        read_burst(0,round*64,16,round+1);
        read_burst(1,2048+round*64,16,round+2);
      join
    end
    // Same-port simultaneous read/write exercises the internal arbiter.
    fork
      read_burst(0,0,16,9);
      write_burst(0,2048,16,10,1);
    join
    read_burst(1,2048,16,11);
    // Interface reset must not erase stored RAM contents.
    @(negedge clk[0]); rst[0]=1;
    @(negedge clk[1]); rst[1]=1;
    #100; @(negedge clk[0]); rst[0]=0; @(negedge clk[1]); rst[1]=0;
    fork
      read_burst(0,0,16,5);
      read_burst(1,2048,16,6);
    join
    if (read_beats[0]+read_beats[1]!=576 || writes[0]+writes[1]!=33)
      $fatal(1,"ERROR scratchpad coverage count");
    $display("MODERN_PASS axi_scratchpad reads=576 writes=33"); $finish;
  end
  initial begin #200000; $fatal(1,"ERROR scratchpad watchdog"); end
endmodule
`undef RAM_PORT
