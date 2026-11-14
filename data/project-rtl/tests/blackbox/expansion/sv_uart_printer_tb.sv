// Decode serial output independently; verify full read/write formatted records.
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg anrst=0,empty=1,rnw=1;
reg [31:0] addr=32'h1234abcd,data=32'h9876ef01;
wire req,txd;
uart_debug_printer dut(.clk(clk),.anrst(anrst),.empty(empty),.r_req(req),.r_rnw(rnw),.r_addr(addr),.r_data(data),.uart_txd(txd));
reg [7:0] received;
string expected={"R 1234_ABCD 9876_EF01",8'h0d,"W 0000_FFFF A5A5_5A5A",8'h0d};
integer count=0,records=0;
always @(posedge req) begin
 records=records+1;
 if(records==1) begin rnw=0;addr=32'h0000ffff;data=32'ha5a55a5a;end
 else empty=1;
end
initial begin
 repeat(8) @(negedge clk);anrst=1;empty=0;
end
initial begin
 forever begin
  @(negedge txd); repeat(15) @(posedge clk); #1;
  for(integer k=0;k<8;k=k+1) begin
   received[k]=txd;repeat(10) @(posedge clk);#1;
  end
  if(received !== expected[count] || txd !== 1) $fatal(1,"ERROR printer byte %0d got=%h expected=%h",count,received,expected[count]);
  count=count+1;
  if(count==44) begin
   if(records!=2) $fatal(1,"ERROR printer ack");
   $display("EXPANSION_PASS sv_uart_printer");$finish;
  end
 end
end
initial begin #1000000; $fatal(1,"ERROR timeout");end
endmodule
