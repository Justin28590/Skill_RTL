// Dataset-authored DMA test: independent AXI slave and separate byte scoreboard.
`timescale 1ns/1ps
module tb;
  reg clk=0, rst=1;
  always #5 clk=~clk;
  reg [15:0] rd_addr=0, rd_len=0, wr_addr=0, wr_len=0;
  reg [7:0] rd_tag=0, wr_tag=0;
  reg rd_valid=0, wr_valid=0;
  wire rd_ready, wr_ready;
  wire [7:0] rd_status_tag, wr_status_tag, wr_status_id, wr_status_dest;
  wire [3:0] rd_error, wr_error;
  wire rd_status, wr_status, wr_status_user;
  wire [15:0] wr_status_len;
  wire [31:0] out_data;
  wire [3:0] out_keep;
  wire out_valid, out_last, out_user;
  wire [7:0] out_id,out_dest;
  reg out_ready=0;
  reg [31:0] in_data=0;
  reg [3:0] in_keep=0;
  reg in_valid=0,in_last=0;
  wire in_ready;
  wire [7:0] awid, arid, awlen, arlen;
  wire [15:0] awaddr,araddr;
  wire [2:0] awsize,arsize,awprot,arprot;
  wire [1:0] awburst,arburst;
  wire awlock,arlock;
  wire [3:0] awcache,arcache;
  wire awvalid,arvalid,wvalid,wlast,bready,rready;
  reg awready=0,arready=0,wready=0,bvalid=0,rvalid=0,rlast=0;
  wire [31:0] wdata;
  wire [3:0] wstrb;
  reg [7:0] bid=0,rid=0;
  reg [1:0] bresp=0,rresp=0;
  reg [31:0] rdata=0;
  reg [1:0] inject_r=0,inject_w=0;
  axi_dma #(.AXI_MAX_BURST_LEN(4),.LEN_WIDTH(16),.ENABLE_UNALIGNED(1),
    .AXIS_ID_ENABLE(1),.AXIS_DEST_ENABLE(1)) dut (
    .clk(clk),.rst(rst),
    .s_axis_read_desc_addr(rd_addr),.s_axis_read_desc_len(rd_len),.s_axis_read_desc_tag(rd_tag),
    .s_axis_read_desc_id(rd_tag),.s_axis_read_desc_dest(rd_tag^8'h55),.s_axis_read_desc_user(rd_tag[0]),
    .s_axis_read_desc_valid(rd_valid),.s_axis_read_desc_ready(rd_ready),
    .m_axis_read_desc_status_tag(rd_status_tag),.m_axis_read_desc_status_error(rd_error),.m_axis_read_desc_status_valid(rd_status),
    .m_axis_read_data_tdata(out_data),.m_axis_read_data_tkeep(out_keep),.m_axis_read_data_tlast(out_last),
    .m_axis_read_data_tvalid(out_valid),.m_axis_read_data_tready(out_ready),
    .m_axis_read_data_tid(out_id),.m_axis_read_data_tdest(out_dest),.m_axis_read_data_tuser(out_user),
    .s_axis_write_desc_addr(wr_addr),.s_axis_write_desc_len(wr_len),.s_axis_write_desc_tag(wr_tag),
    .s_axis_write_desc_valid(wr_valid),.s_axis_write_desc_ready(wr_ready),
    .m_axis_write_desc_status_len(wr_status_len),.m_axis_write_desc_status_tag(wr_status_tag),
    .m_axis_write_desc_status_id(wr_status_id),.m_axis_write_desc_status_dest(wr_status_dest),
    .m_axis_write_desc_status_user(wr_status_user),.m_axis_write_desc_status_error(wr_error),.m_axis_write_desc_status_valid(wr_status),
    .s_axis_write_data_tdata(in_data),.s_axis_write_data_tkeep(in_keep),.s_axis_write_data_tlast(in_last),
    .s_axis_write_data_tvalid(in_valid),.s_axis_write_data_tready(in_ready),
    .s_axis_write_data_tid(wr_tag),.s_axis_write_data_tdest(wr_tag^8'haa),.s_axis_write_data_tuser(wr_tag[0]),
    .m_axi_awid(awid),.m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),
    .m_axi_awlock(awlock),.m_axi_awcache(awcache),.m_axi_awprot(awprot),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
    .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),
    .m_axi_bid(bid),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),
    .m_axi_arid(arid),.m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),
    .m_axi_arlock(arlock),.m_axi_arcache(arcache),.m_axi_arprot(arprot),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
    .m_axi_rid(rid),.m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
    .read_enable(1'b1),.write_enable(1'b1),.write_abort(1'b0)
  );
  reg [7:0] memory[0:65535], expected[0:65535];
  integer cycle=0,wbase=0,rbase=0,wleft=0,rleft=0,bdelay=0,lane;
  integer read_bursts=0,write_bursts=0,read_checks=0,write_checks=0,received=0;
  reg rd_done=0,wr_done=0,read_active=0,write_active=0;
  reg block_out=0,block_w=0,block_aw=0,block_ar=0;
  reg [53:0] held_out;
  reg [36:0] held_w;
  reg [44:0] held_aw,held_ar;
  reg [3:0] wanted_keep;
  function [7:0] stream_byte(input integer tag,offset);
    stream_byte=(tag*73+offset*29+193)%256;
  endfunction
  always @(negedge clk) begin
    cycle=cycle+1;
    awready=!rst && wleft==0 && bdelay==0 && !bvalid && cycle%4!=0;
    arready=!rst && rleft==0 && !rvalid && cycle%5>1;
    wready=!rst && wleft!=0 && cycle%3!=0;
    out_ready=!rst && cycle%7>2;
  end
  // Public AXI protocol slave. Only these received writes alter memory[].
  always @(posedge clk) if (!rst) begin
    if (awvalid && awready) begin
      if (awsize!==2 || awburst!==1 || awlen>3 || (awaddr&4092)+4*(awlen+1)>4096)
        $fatal(1,"ERROR DMA AW burst shape/4K boundary");
      wbase<=awaddr&16'hfffc; wleft<=awlen+1; bid<=awid; write_bursts=write_bursts+1;
    end
    if (wvalid && wready) begin
      if (wlast !== (wleft==1)) $fatal(1,"ERROR DMA WLAST");
      for (lane=0; lane<4; lane=lane+1)
        if (wstrb[lane]) memory[wbase+lane]=wdata[lane*8 +: 8];
      wbase<=wbase+4; wleft<=wleft-1;
      if (wleft==1) bdelay<=3;
    end
    if (bdelay>0) begin
      bdelay<=bdelay-1;
      if (bdelay==1) begin bvalid<=1; bresp<=inject_w; end
    end
    if (bvalid && bready) bvalid<=0;
    if (arvalid && arready) begin
      if (arsize!==2 || arburst!==1 || arlen>3 || (araddr&4092)+4*(arlen+1)>4096)
        $fatal(1,"ERROR DMA AR burst shape/4K boundary");
      rbase<=araddr&16'hfffc; rleft<=arlen+1; rid<=arid; read_bursts=read_bursts+1;
    end
    if (!rvalid && rleft>0 && cycle%4!=0) begin
      for (lane=0; lane<4; lane=lane+1) rdata[lane*8 +: 8]<=memory[rbase+lane];
      rlast<=rleft==1; rresp<=inject_r; rvalid<=1;
    end
    if (rvalid && rready) begin rvalid<=0; rleft<=rleft-1; rbase<=rbase+4; end
  end
  // Independent stream/status checking, including held-valid protocol rules.
  always @(posedge clk) if (!rst) begin
    if (block_out && (out_valid!==1 || {out_data,out_keep,out_last,out_id,out_dest,out_user}!==held_out))
      $fatal(1,"ERROR DMA output unstable under backpressure");
    if (block_w && (wvalid!==1 || {wdata,wstrb,wlast}!==held_w)) $fatal(1,"ERROR DMA W unstable");
    if (block_aw && (awvalid!==1 || {awid,awaddr,awlen,awsize,awburst,awlock,awcache,awprot}!==held_aw))
      $fatal(1,"ERROR DMA AW unstable");
    if (block_ar && (arvalid!==1 || {arid,araddr,arlen,arsize,arburst,arlock,arcache,arprot}!==held_ar))
      $fatal(1,"ERROR DMA AR unstable");
    block_out=out_valid && !out_ready; held_out={out_data,out_keep,out_last,out_id,out_dest,out_user};
    block_w=wvalid && !wready; held_w={wdata,wstrb,wlast};
    block_aw=awvalid && !awready; held_aw={awid,awaddr,awlen,awsize,awburst,awlock,awcache,awprot};
    block_ar=arvalid && !arready; held_ar={arid,araddr,arlen,arsize,arburst,arlock,arcache,arprot};
    if (out_valid && out_ready) begin
      if (!read_active || received>=rd_len) $fatal(1,"ERROR DMA extra read data");
      wanted_keep=0;
      for (integer j=0; j<4; j=j+1)
        if (received+j<rd_len) begin
          wanted_keep[j]=1;
          if (out_data[j*8 +: 8] !== expected[rd_addr+received+j]) $fatal(1,"ERROR DMA read byte");
        end
      if (out_keep!==wanted_keep || out_last!==(received+4>=rd_len) ||
          out_id!==rd_tag || out_dest!==(rd_tag^8'h55) || out_user!==rd_tag[0])
        $fatal(1,"ERROR DMA read framing/sideband");
      received=received+((rd_len-received<4)?rd_len-received:4);
    end
    if (rd_status) begin
      if (!read_active || rd_done || rd_status_tag!==rd_tag || rd_error!==4'(inject_r==2?4:inject_r==3?5:0))
        $fatal(1,"ERROR DMA read status");
      rd_done=1; read_checks=read_checks+1;
    end
    if (wr_status) begin
      if (!write_active || wr_done || wr_status_tag!==wr_tag || wr_status_len!==wr_len ||
          wr_status_id!==wr_tag || wr_status_dest!==(wr_tag^8'haa) || wr_status_user!==wr_tag[0] ||
          wr_error!==4'(inject_w==2?6:inject_w==3?7:0)) $fatal(1,"ERROR DMA write status");
      wr_done=1; write_checks=write_checks+1;
    end
  end
  task automatic read_transfer(input integer address,length,tag,error_response);
    begin
      @(negedge clk); rd_addr=address; rd_len=length; rd_tag=tag; inject_r=error_response;
      rd_done=0; received=0; read_active=1; rd_valid=1;
      @(posedge clk); while (!rd_ready) @(posedge clk);
      @(negedge clk); rd_valid=0;
      while (!(rd_done && received==length)) @(negedge clk);
      read_active=0;
    end
  endtask
  task automatic write_transfer(input integer address,length,tag,error_response);
    integer offset,j;
    begin
      @(negedge clk); wr_addr=address; wr_len=length; wr_tag=tag; inject_w=error_response;
      wr_done=0; write_active=1; wr_valid=1;
      @(posedge clk); while (!wr_ready) @(posedge clk);
      @(negedge clk); wr_valid=0;
      for (offset=0; offset<length; offset=offset+4) begin
        repeat ((offset+tag)%3) @(negedge clk);
        in_keep=0; in_data=0;
        for (j=0; j<4; j=j+1) if (offset+j<length) begin
          in_keep[j]=1; in_data[j*8 +: 8]=stream_byte(tag,offset+j);
        end
        in_last=offset+4>=length; in_valid=1;
        @(posedge clk); while (!in_ready) @(posedge clk);
        for (j=0; j<4; j=j+1) if (offset+j<length) expected[address+offset+j]=stream_byte(tag,offset+j);
        @(negedge clk); in_valid=0;
      end
      while (!wr_done) @(negedge clk);
      write_active=0;
    end
  endtask
  integer i,t,n,ra,wa;
  initial begin
    for (i=0; i<65536; i=i+1) begin memory[i]=(i*37+i/251+113)%256; expected[i]=memory[i]; end
    repeat (5) @(negedge clk); rst=0;
    for (t=0; t<24; t=t+1) begin
      case(t%12)
        0:n=1; 1:n=2; 2:n=3; 3:n=4; 4:n=7; 5:n=16;
        6:n=31; 7:n=32; 8:n=33; 9:n=65; 10:n=127; 11:n=129;
      endcase
      ra=t<12 ? 256+t*160+t%4 : 4093-t%4;
      wa=t<12 ? 8192+t*160+(t+1)%4 : 12285-t%4;
      fork
        read_transfer(ra,n,t+1,t==22?2:t==23?3:0);
        write_transfer(wa,n,t+33,t==22?2:t==23?3:0);
      join
      // Check the whole byte memory, including untouched bytes and disabled strobes.
      for (i=0; i<65536; i=i+1)
        if (memory[i]!==expected[i]) $fatal(1,"ERROR DMA write byte/strobe address=%h",i);
    end
    repeat (20) @(negedge clk);
    if (read_checks!=24 || write_checks!=24 || read_bursts<48 || write_bursts<48)
      $fatal(1,"ERROR DMA coverage counts");
    $display("MODERN_PASS axi_dma_engine read=24 write=24"); $finish;
  end
  initial begin #500000; $fatal(1,"ERROR DMA watchdog"); end
endmodule
