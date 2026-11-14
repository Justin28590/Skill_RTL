// Independent ready/valid queue scoreboard, filling, draining, stalls and reset.
`timescale 1ns/1ps
module tb;
reg clock=0;always #5 clock=~clock;
reg reset=1,enq_valid=0,deq_ready=0;
reg [7:0] enq_bits=0;
wire enq_ready,deq_valid;
wire [7:0] deq_bits;
DoubleBufferFifo dut(.clock(clock),.reset(reset),.io_enq_ready(enq_ready),.io_enq_valid(enq_valid),.io_enq_bits(enq_bits),
 .io_deq_ready(deq_ready),.io_deq_valid(deq_valid),.io_deq_bits(deq_bits));
reg [7:0] queue[0:2047];
integer head=0,tail=0,cycle=0,total=0;
reg stalled=0;
reg [7:0] held;
always @(posedge clock) if(!reset) begin
 if(stalled && (deq_valid !== 1 || deq_bits !== held)) $fatal(1,"ERROR unstable stalled output");
 if(deq_valid && deq_ready) begin
  if(head==tail || deq_bits !== queue[head]) $fatal(1,"ERROR FIFO order");
  head=head+1;total=total+1;
 end
 if(enq_valid && enq_ready) begin queue[tail]=enq_bits;tail=tail+1;end
 stalled=deq_valid && !deq_ready;held=deq_bits;
 if(tail-head>8) $fatal(1,"ERROR FIFO capacity");
end
initial begin
 repeat(5) @(negedge clock);reset=0;
 for(cycle=0;cycle<1000;cycle=cycle+1) begin
  enq_valid=(cycle%7!=0);enq_bits=(cycle*17)^8'hb6;
  deq_ready=(cycle>30 && cycle%13>4);
  @(negedge clock);
  if(cycle==29 && (tail-head!=8 || enq_ready !== 0)) $fatal(1,"ERROR full FIFO");
 end
 enq_valid=0;deq_ready=1;repeat(20) @(negedge clock);
 if(head!=tail || deq_valid !== 0 || total<200) $fatal(1,"ERROR FIFO drain");
 reset=1;repeat(3) @(negedge clock);reset=0;
 repeat(5) @(negedge clock);
 if(deq_valid !== 0 || enq_ready !== 1) $fatal(1,"ERROR FIFO reset");
 $display("EXPANSION_PASS chisel_double_buffer_fifo");$finish;
end
initial begin #1000000;$fatal(1,"ERROR timeout");end
endmodule
