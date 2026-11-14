// Dataset-authored frame/byte scoreboard across unrelated digital clocks.
`timescale 1ns/1ps
module async_case #(parameter S_HALF=3, M_HALF=5)(output reg finished=0);
  reg s_clk=0, m_clk=0;
  always #(S_HALF) s_clk=~s_clk;
  initial begin #1; forever #(M_HALF) m_clk=~m_clk; end
  reg s_rst=1, m_rst=1, active=0;
  reg [7:0] s_data=0;
  reg s_valid=0, s_last=0, s_user=0;
  reg [3:0] s_id=0, s_dest=0;
  wire s_ready;
  wire [31:0] m_data;
  wire [3:0] m_keep, m_id, m_dest;
  wire m_valid, m_last, m_user, bad_frame;
  reg m_ready=0;
  axis_async_fifo_adapter #(.DEPTH(64), .S_DATA_WIDTH(8), .S_KEEP_ENABLE(1), .S_KEEP_WIDTH(1),
    .M_DATA_WIDTH(32), .M_KEEP_ENABLE(1), .M_KEEP_WIDTH(4), .ID_ENABLE(1), .ID_WIDTH(4),
    .DEST_ENABLE(1), .DEST_WIDTH(4), .FRAME_FIFO(1), .DROP_BAD_FRAME(1)) dut (
    .s_clk(s_clk), .s_rst(s_rst), .s_axis_tdata(s_data), .s_axis_tkeep(1'b1),
    .s_axis_tvalid(s_valid), .s_axis_tready(s_ready), .s_axis_tlast(s_last),
    .s_axis_tid(s_id), .s_axis_tdest(s_dest), .s_axis_tuser(s_user),
    .m_clk(m_clk), .m_rst(m_rst), .m_axis_tdata(m_data), .m_axis_tkeep(m_keep),
    .m_axis_tvalid(m_valid), .m_axis_tready(m_ready), .m_axis_tlast(m_last),
    .m_axis_tid(m_id), .m_axis_tdest(m_dest), .m_axis_tuser(m_user),
    .s_pause_req(1'b0), .m_pause_req(1'b0), .s_status_bad_frame(bad_frame)
  );
  function integer length_of(input integer frame);
    length_of=1+(frame*7)%17;
  endfunction
  function [7:0] payload(input integer frame, offset);
    payload=(frame*37+offset*19+129)%256;
  endfunction
  integer f,b,lane,recv_frame=0,recv_byte=0,cycles=0,frames=0,bad_count=0,stalls=0;
  reg source_done=0, blocked=0;
  reg [45:0] held;
  reg [3:0] wanted_keep;
  reg wanted_last;
  // Consumer checks data, framing, sidebands and stable blocked output.
  always @(negedge m_clk) begin
    if (active) begin
      cycles=cycles+1;
      m_ready=cycles>180 && cycles%7>1;
    end else m_ready=0;
  end
  always @(posedge s_clk) if (active) begin
    if (bad_frame) bad_count=bad_count+1;
    if (s_valid && !s_ready) stalls=stalls+1;
  end
  always @(posedge m_clk) if (active) begin
    if (blocked && (m_valid !== 1 || {m_data,m_keep,m_last,m_id,m_dest,m_user} !== held))
      $fatal(1,"ERROR async blocked output changed");
    if (m_valid && m_ready) begin
      if (recv_frame>=48) $fatal(1,"ERROR async duplicate output");
      wanted_keep=0;
      for (lane=0; lane<4; lane=lane+1) begin
        if (recv_byte+lane<length_of(recv_frame)) begin
          wanted_keep[lane]=1;
          if (m_data[lane*8 +: 8] !== payload(recv_frame,recv_byte+lane))
            $fatal(1,"ERROR async data frame=%0d byte=%0d",recv_frame,recv_byte+lane);
        end
      end
      wanted_last=recv_byte+4>=length_of(recv_frame);
      if (m_keep !== wanted_keep || m_last !== wanted_last || m_id !== 4'(recv_frame) ||
          m_dest !== 4'(15-recv_frame%16) || m_user !== 0)
        $fatal(1,"ERROR async framing or sideband");
      if (wanted_last) begin
        frames=frames+1; recv_byte=0; recv_frame=recv_frame+1;
        if (recv_frame%7==3) recv_frame=recv_frame+1;
      end else recv_byte=recv_byte+4;
    end
    blocked=m_valid && !m_ready;
    held={m_data,m_keep,m_last,m_id,m_dest,m_user};
  end
  initial begin
    #100; @(negedge s_clk); s_rst=0; @(negedge m_clk); m_rst=0;
    // Queue an incomplete frame before coordinated reset; it must not leak later.
    repeat (20) @(negedge s_clk);
    s_valid=1; s_data=8'hfe;
    repeat (5) @(negedge s_clk);
    s_valid=0; s_rst=1; m_rst=1;
    repeat (20) @(negedge s_clk);
    s_rst=0; @(negedge m_clk); m_rst=0;
    repeat (20) @(negedge s_clk);
    active=1;
    for (f=0; f<48; f=f+1) begin
      for (b=0; b<length_of(f); b=b+1) begin
        @(negedge s_clk);
        s_data=payload(f,b); s_id=f; s_dest=15-f%16;
        s_last=b==length_of(f)-1; s_user=s_last && f%7==3; s_valid=1;
        @(posedge s_clk); while (!s_ready) @(posedge s_clk);
        @(negedge s_clk); s_valid=0;
      end
    end
    source_done=1;
    wait (frames==41);
    repeat (30) @(negedge m_clk);
    if (bad_count!=7 || recv_frame!=48 || (S_HALF<M_HALF && stalls==0))
      $fatal(1,"ERROR async coverage bad=%0d frames=%0d stalls=%0d",bad_count,frames,stalls);
    $display("MODERN_PASS axis_async_bridge clocks=%0d/%0d good=41 bad=7",S_HALF,M_HALF);
    finished=1;
  end
endmodule
module tb;
  wire a,b;
  async_case #(.S_HALF(3),.M_HALF(5)) fast_in(a);
  async_case #(.S_HALF(7),.M_HALF(4)) fast_out(b);
  initial begin wait(a && b); $finish; end
  initial begin #200000; $fatal(1,"ERROR async watchdog"); end
endmodule
