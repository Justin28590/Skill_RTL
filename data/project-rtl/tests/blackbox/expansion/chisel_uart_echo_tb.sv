// Independent UART stimulus/decoder, no loopback oracle or internal names.
`timescale 1ns/1ps
module tb;
reg clock=0;always #5 clock=~clock;
reg reset=1,rxd=1;
wire txd;
Echo dut(.clock(clock),.reset(reset),.io_rxd(rxd),.io_txd(txd));
integer received_count=0;
reg [7:0] received;
function [7:0] pattern(input integer n);pattern=(n*43)^8'hb5;endfunction
initial begin
 repeat(5) @(negedge clock);reset=0;repeat(10) @(negedge clock);
 for(integer n=0;n<16;n=n+1) begin
  rxd=0;repeat(8) @(negedge clock);
  for(integer k=0;k<8;k=k+1) begin rxd=(pattern(n)>>k)&1;repeat(8) @(negedge clock);end
  rxd=1;repeat(80) @(negedge clock);
 end
 wait(received_count==16);$display("EXPANSION_PASS chisel_uart_echo");$finish;
end
initial forever begin
 @(negedge txd);repeat(12) @(posedge clock);#1;
 for(integer k=0;k<8;k=k+1) begin received[k]=txd;repeat(8) @(posedge clock);#1;end
 if(received !== pattern(received_count) || txd !== 1) $fatal(1,"ERROR echo byte");
 repeat(8) @(posedge clock);#1;
 if(txd !== 1) $fatal(1,"ERROR second stop bit");
 received_count=received_count+1;
end
initial begin #1000000;$fatal(1,"ERROR timeout");end
endmodule
