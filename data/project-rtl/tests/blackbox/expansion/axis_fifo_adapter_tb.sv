// Independent byte packing / ordering / backpressure scoreboard.
`timescale 1ns/1ps
module tb;
reg clk=0; always #5 clk=~clk;
reg rst=1,s_valid=0,m_ready=0;
reg [7:0] s_data=0;
reg s_last=0;
wire s_ready,m_valid,m_last;
wire [31:0] m_data;
wire [3:0] m_keep;
wire [7:0] m_id,m_dest;
wire m_user;
wire [6:0] depth, committed;
wire overflow,bad_frame,good_frame,pause_ack;
axis_fifo_adapter #(.DEPTH(64),.S_DATA_WIDTH(8),.M_DATA_WIDTH(32),.ID_ENABLE(1),.DEST_ENABLE(1)) dut(
 .clk(clk),.rst(rst),.s_axis_tdata(s_data),.s_axis_tkeep(1'b1),.s_axis_tvalid(s_valid),.s_axis_tready(s_ready),
 .s_axis_tlast(s_last),.s_axis_tid(8'h12),.s_axis_tdest(8'h34),.s_axis_tuser(1'b0),
 .m_axis_tdata(m_data),.m_axis_tkeep(m_keep),.m_axis_tvalid(m_valid),.m_axis_tready(m_ready),
 .m_axis_tlast(m_last),.m_axis_tid(m_id),.m_axis_tdest(m_dest),.m_axis_tuser(m_user),
 .pause_req(1'b0),.pause_ack(pause_ack),.status_depth(depth),.status_depth_commit(committed),
 .status_overflow(overflow),.status_bad_frame(bad_frame),.status_good_frame(good_frame));
integer sent=0,got=0,cycle=0;
reg [31:0] expected;
function [7:0] pattern(input integer n); pattern=(n*29)^8'h59; endfunction
initial begin
 repeat(5) @(negedge clk); rst=0;
 for(sent=0;sent<256;sent=sent+1) begin
  s_data=pattern(sent); s_last=(sent%16==15); s_valid=1;
  do @(posedge clk); while(!s_ready);
  @(negedge clk); s_valid=0;
  if(sent%3==0) @(negedge clk);
 end
 wait(got==64); repeat(8) @(negedge clk);
 if(m_valid !== 0 || overflow !== 0 || bad_frame !== 0) $fatal(1,"ERROR FIFO residual");
 $display("EXPANSION_PASS axis_fifo_adapter"); $finish;
end
always @(negedge clk) if(!rst) begin cycle=cycle+1; m_ready=(cycle%11>4); end
always @(posedge clk) if(!rst && m_valid && m_ready) begin
 expected={pattern(4*got+3),pattern(4*got+2),pattern(4*got+1),pattern(4*got)};
 if(m_data !== expected || m_keep !== 4'hf || m_last !== (got%4==3) || m_id !== 8'h12 || m_dest !== 8'h34 || m_user !== 0)
  $fatal(1,"ERROR FIFO pack/order/sideband");
 got=got+1;
end
initial begin #200000; $fatal(1,"ERROR timeout"); end
endmodule
