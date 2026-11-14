// Dataset-authored public-port scoreboard, not an upstream testbench.
`timescale 1ns/1ps
module tb;
  localparam FRAMES = 24;
  reg clk = 0;
  always #5 clk = ~clk;
  reg rst = 1;
  reg [127:0] s_data = 0;
  reg [15:0] s_keep = 0, s_id = 0;
  reg [7:0] s_dest = 0;
  reg [3:0] s_valid = 0, s_last = 0, s_user = 0;
  wire [3:0] s_ready;
  wire [63:0] m_data;
  wire [7:0] m_keep;
  wire [11:0] m_id;
  wire [3:0] m_dest;
  wire [1:0] m_valid, m_last, m_user;
  reg [1:0] m_ready = 0;
  axis_switch #(
    .S_COUNT(4), .M_COUNT(2), .DATA_WIDTH(32), .KEEP_ENABLE(1), .KEEP_WIDTH(4),
    .ID_ENABLE(1), .S_ID_WIDTH(4), .M_ID_WIDTH(6), .S_DEST_WIDTH(2), .M_DEST_WIDTH(2),
    .USER_ENABLE(1), .USER_WIDTH(1), .UPDATE_TID(1), .S_REG_TYPE(2), .M_REG_TYPE(2),
    .ARB_TYPE_ROUND_ROBIN(1), .ARB_LSB_HIGH_PRIORITY(1)
  ) dut (
    .clk(clk), .rst(rst), .s_axis_tdata(s_data), .s_axis_tkeep(s_keep),
    .s_axis_tvalid(s_valid), .s_axis_tready(s_ready), .s_axis_tlast(s_last),
    .s_axis_tid(s_id), .s_axis_tdest(s_dest), .s_axis_tuser(s_user),
    .m_axis_tdata(m_data), .m_axis_tkeep(m_keep), .m_axis_tvalid(m_valid),
    .m_axis_tready(m_ready), .m_axis_tlast(m_last), .m_axis_tid(m_id),
    .m_axis_tdest(m_dest), .m_axis_tuser(m_user)
  );
  integer send_f[0:3], send_b[0:3];
  integer recv_f[0:3][0:1], recv_b[0:3][0:1];
  integer accepted[0:3][0:FRAMES-1][0:6];
  integer owner[0:1];
  reg [45:0] held[0:1];
  reg [1:0] stalled = 0;
  integer epoch, cycle, s, m, f, b, src, dest, length, total, expected_total, completed = 0;
  function integer route;
    input integer source, frame;
    begin route = frame < 4 ? 0 : (source+frame)%2; end
  endfunction
  function integer frame_length;
    input integer source, frame;
    begin frame_length = 1+(frame*3+source)%7; end
  endfunction
  function integer next_frame;
    input integer source, output_port, start;
    integer n;
    begin
      next_frame = FRAMES;
      for (n = FRAMES-1; n >= start; n = n-1)
        if (route(source,n) == output_port) next_frame = n;
    end
  endfunction
  function [31:0] payload;
    input integer ep, source, frame, beat;
    begin payload = (ep << 28) | (source << 24) | (frame << 8) | beat | 32'h00800080; end
  endfunction
  function [3:0] keep_mask;
    input integer source, frame, beat;
    begin keep_mask = beat == frame_length(source,frame)-1 ? (15 >> (frame%4)) : 15; end
  endfunction
  task reset_switch;
    begin
      @(negedge clk); rst = 1; s_valid = 0; m_ready = 0;
      repeat (3) @(negedge clk);
      if (m_valid !== 0) $fatal(1, "ERROR switch reset valid");
      rst = 0;
    end
  endtask
  initial begin
    reset_switch();
    // Fill skid buffers under full output stall, then discard via reset.
    s_valid = 15; s_data = '1; s_keep = '1; s_last = 15;
    repeat (16) @(negedge clk);
    reset_switch();
    repeat (10) begin
      @(negedge clk); m_ready = 3;
      if (m_valid !== 0) $fatal(1, "ERROR stale packet after reset");
    end
    for (epoch = 0; epoch < 2; epoch = epoch+1) begin
      reset_switch();
      total = 0; expected_total = 0; stalled = 0;
      for (s = 0; s < 4; s = s+1) begin
        send_f[s] = 0; send_b[s] = 0;
        for (m = 0; m < 2; m = m+1) begin
          recv_f[s][m] = next_frame(s,m,0); recv_b[s][m] = 0;
        end
        for (f = 0; f < FRAMES; f = f+1) begin
          expected_total = expected_total + frame_length(s,f);
          for (b = 0; b < 7; b = b+1) accepted[s][f][b] = 0;
        end
      end
      for (m = 0; m < 2; m = m+1) owner[m] = -1;
      for (cycle = 0; cycle < 5000 && total < expected_total; cycle = cycle+1) begin
        @(negedge clk);
        // Long stalls, independent ready patterns, then drain without stalls.
        m_ready[0] = cycle > 70 && (cycle > 2000 || cycle%5 != 0);
        m_ready[1] = cycle > 35 && (cycle > 2000 || cycle%7 > 1);
        for (s = 0; s < 4; s = s+1) begin
          // If valid was blocked, retain ALL input fields until handshake.
          if (!s_valid[s] && send_f[s] < FRAMES && (cycle+s)%4 != 0) begin
            f = send_f[s]; b = send_b[s]; dest = route(s,f);
            s_data[s*32 +: 32] = payload(epoch,s,f,b);
            s_keep[s*4 +: 4] = keep_mask(s,f,b);
            s_id[s*4 +: 4] = s;
            s_dest[s*2 +: 2] = 2*dest+(f%2);
            s_last[s] = b == frame_length(s,f)-1;
            s_user[s] = (f+b)%2;
            s_valid[s] = 1;
          end
        end
        @(posedge clk);
        for (s = 0; s < 4; s = s+1)
          if (s_valid[s] && s_ready[s]) begin
            accepted[s][send_f[s]][send_b[s]] = 1;
            if (s_last[s]) begin send_f[s] = send_f[s]+1; send_b[s] = 0; end
            else send_b[s] = send_b[s]+1;
          end
        for (m = 0; m < 2; m = m+1) begin
          if (stalled[m] && (m_valid[m] !== 1 ||
              {m_data[m*32 +: 32],m_keep[m*4 +: 4],m_id[m*6 +: 6],m_dest[m*2 +: 2],m_last[m],m_user[m]} !== held[m]))
            $fatal(1, "ERROR unstable blocked output");
          if (m_valid[m] && m_ready[m]) begin
            if (^m_id[m*6 +: 6] === 1'bx) $fatal(1, "ERROR unknown source ID");
            src = m_id[m*6 + 4 +: 2];
            f = recv_f[src][m]; b = recv_b[src][m];
            if (f >= FRAMES) $fatal(1, "ERROR duplicate or misrouted frame");
            if (owner[m] != -1 && owner[m] != src) $fatal(1, "ERROR interleaved packet");
            owner[m] = src;
            length = frame_length(src,f);
            if (accepted[src][f][b] != 1 ||
                m_data[m*32 +: 32] !== payload(epoch,src,f,b) ||
                m_keep[m*4 +: 4] !== keep_mask(src,f,b) ||
                m_id[m*6 +: 6] !== 6'(src*16+src) ||
                m_dest[m*2 +: 2] !== 2'(2*m+f%2) ||
                m_last[m] !== (b == length-1) || m_user[m] !== 1'((f+b)%2))
              $fatal(1, "ERROR packet scoreboard port=%0d source=%0d frame=%0d beat=%0d", m,src,f,b);
            accepted[src][f][b] = 0;
            total = total+1;
            if (b == length-1) begin
              recv_f[src][m] = next_frame(src,m,f+1); recv_b[src][m] = 0; owner[m] = -1;
            end else recv_b[src][m] = b+1;
          end
          stalled[m] = m_valid[m] && !m_ready[m];
          held[m] = {m_data[m*32 +: 32],m_keep[m*4 +: 4],m_id[m*6 +: 6],m_dest[m*2 +: 2],m_last[m],m_user[m]};
        end
        // Nonblocking updates avoid a race with DUT sampling at this edge.
        for (s = 0; s < 4; s = s+1)
          if (s_valid[s] && s_ready[s]) s_valid[s] <= 0;
      end
      if (total != expected_total) $fatal(1, "ERROR missing packets/starvation");
      for (s = 0; s < 4; s = s+1) begin
        if (send_f[s] != FRAMES) $fatal(1, "ERROR unaccepted input");
        for (m = 0; m < 2; m = m+1)
          if (recv_f[s][m] != FRAMES) $fatal(1, "ERROR incomplete output");
      end
      repeat (20) begin
        @(negedge clk); m_ready = 3;
        if (m_valid !== 0) $fatal(1, "ERROR extra output after drain");
      end
      completed = completed+4*FRAMES;
    end
    $display("COMPUTE_PASS axis_packet_switch packets=%0d", completed);
    $finish;
  end
  initial begin #200000; $fatal(1, "ERROR switch watchdog"); end
endmodule
