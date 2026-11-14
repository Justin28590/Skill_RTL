// Independent mode-0 pin oracle; write and command+read transactions.
`timescale 1ns/1ps
module tb;
reg clk=0; always #5 clk=~clk;
reg nrst=0,spi_clk=0,wr=0,rd=0,miso=0;
reg [7:0] data=0;
wire busy,sclk,ncs,mosi,oe;
wire [7:0] result;
spi_master dut(.clk(clk),.nrst(nrst),.spi_clk(spi_clk),.spi_wr_cmd(wr),.spi_rd_cmd(rd),.spi_busy(busy),
 .mosi_data(data),.miso_data(result),.clk_pin(sclk),.ncs_pin(ncs),.mosi_pin(mosi),.oe_pin(oe),.miso_pin(miso));
initial forever begin repeat(4) @(negedge clk); spi_clk=~spi_clk; end
integer bits=0;
reg [7:0] captured=0;
always @(negedge ncs) begin bits=0;captured=0;end
always @(posedge sclk) if(!ncs && oe) begin captured={captured[6:0],mosi};bits=bits+1;end
task transact(input [7:0] value,input read_cmd,input bit_value);
 begin
  @(negedge clk); data=value;miso=bit_value;wr=!read_cmd;rd=read_cmd;
  repeat(3) @(negedge clk);wr=0;rd=0;
  wait(busy);wait(!busy);repeat(4) @(negedge clk);
  if(bits!=8 || captured !== value || ncs !== 1 || oe !== 0) $fatal(1,"ERROR SPI write pins bits=%0d value=%h",bits,captured);
  if(read_cmd && result !== (bit_value ? 8'hff : 8'h00)) $fatal(1,"ERROR SPI read pins");
 end
endtask
initial begin
 repeat(6) @(negedge clk);nrst=1;
 transact(8'ha6,0,0);transact(8'h39,0,0);transact(8'h9f,1,1);transact(8'h05,1,0);
 $display("EXPANSION_PASS sv_spi");$finish;
end
initial begin #100000; $fatal(1,"ERROR timeout");end
endmodule
