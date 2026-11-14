// Dataset-authored independent pin/AXI oracle; no DUT internals.
`timescale 1ns/1ps
module tb;
reg clk=0; always #5 clk=~clk;
reg rst=1, rxd=1, s_valid=0, m_ready=1;
reg [7:0] s_data=0;
wire [7:0] m_data;
wire s_ready,m_valid,txd,tx_busy,rx_busy,overrun,frame_error;
uart dut(.clk(clk),.rst(rst),.s_axis_tdata(s_data),.s_axis_tvalid(s_valid),.s_axis_tready(s_ready),
 .m_axis_tdata(m_data),.m_axis_tvalid(m_valid),.m_axis_tready(m_ready),.rxd(rxd),.txd(txd),
 .tx_busy(tx_busy),.rx_busy(rx_busy),.rx_overrun_error(overrun),.rx_frame_error(frame_error),.prescale(16'd2));
integer tx_count=0,rx_count=0,i,b;
reg [7:0] received;
function [7:0] pattern(input integer n); pattern=(n*37)^8'ha6; endfunction
initial begin
 repeat(5) @(negedge clk); rst=0;
 for(i=0;i<16;i=i+1) begin
  @(negedge clk); s_data=pattern(i); s_valid=1;
  do @(posedge clk); while(!s_ready);
  @(negedge clk); s_valid=0;
  wait(!tx_busy); repeat(20) @(negedge clk);
 end
 wait(rx_count==16 && tx_count==16);
 if(overrun !== 0 || frame_error !== 0) $fatal(1,"ERROR uart flags");
 $display("EXPANSION_PASS uart_axis"); $finish;
end
initial begin
 wait(!rst);
 forever begin
  @(negedge txd); repeat(24) @(posedge clk); #1;
  for(integer k=0;k<8;k=k+1) begin
   received[k]=txd;
   repeat(16) @(posedge clk); #1;
  end
  if(received !== pattern(tx_count) || txd !== 1) $fatal(1,"ERROR UART transmit");
  tx_count=tx_count+1;
 end
end
initial begin
 wait(!rst); repeat(30) @(negedge clk);
 for(integer n=0;n<16;n=n+1) begin
  rxd=0; repeat(16) @(negedge clk);
  for(integer k=0;k<8;k=k+1) begin rxd=(pattern(n)>>k)&1; repeat(16) @(negedge clk); end
  rxd=1; repeat(40) @(negedge clk);
 end
end
always @(posedge clk) if(!rst && m_valid && m_ready) begin
 if(m_data !== pattern(rx_count)) $fatal(1,"ERROR UART receive");
 rx_count=rx_count+1;
end
initial begin #2000000; $fatal(1,"ERROR timeout"); end
endmodule
