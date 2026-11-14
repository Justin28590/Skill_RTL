// Dataset-authored black-box CPU oracle, not upstream reference RTL/TB.
// Expected values remain in the testbench, never in the program's address space.
// UART/console strings and a software-written PASS flag cannot satisfy this oracle.
`timescale 1ns/1ps
module project_cpu_signature;
    reg clk = 0;
    reg resetn = 0;
    always #5 clk = ~clk;
    initial begin repeat (12) @(posedge clk); resetn <= 1; end

    wire trap, awvalid, wvalid, bready, arvalid, rready;
    wire [31:0] awaddr, wdata, araddr;
    wire [3:0] wstrb;
    reg aw_pending = 0, w_pending = 0, bvalid = 0, rvalid = 0;
    reg [31:0] saved_address, saved_data, rdata;
    reg [3:0] saved_strobe;
    wire awready = !aw_pending && !bvalid;
    wire wready = !w_pending && !bvalid;
    wire arready = !rvalid;
    reg [31:0] memory [0:2047];
    reg [31:0] expected [0:63];
    integer writes = 0;
    reg complete = 0;

    picorv32_axi #(.ENABLE_MUL(1), .ENABLE_DIV(1), .COMPRESSED_ISA(1),
                   .ENABLE_IRQ(1), .ENABLE_TRACE(1)) dut (
        .clk(clk), .resetn(resetn), .trap(trap),
        .mem_axi_awvalid(awvalid), .mem_axi_awready(awready), .mem_axi_awaddr(awaddr), .mem_axi_awprot(),
        .mem_axi_wvalid(wvalid), .mem_axi_wready(wready), .mem_axi_wdata(wdata), .mem_axi_wstrb(wstrb),
        .mem_axi_bvalid(bvalid), .mem_axi_bready(bready),
        .mem_axi_arvalid(arvalid), .mem_axi_arready(arready), .mem_axi_araddr(araddr), .mem_axi_arprot(),
        .mem_axi_rvalid(rvalid), .mem_axi_rready(rready), .mem_axi_rdata(rdata),
        .pcpi_valid(), .pcpi_insn(), .pcpi_rs1(), .pcpi_rs2(),
        .pcpi_wr(1'b0), .pcpi_rd(32'b0), .pcpi_wait(1'b0), .pcpi_ready(1'b0),
        .irq(32'b0), .eoi(), .trace_valid(), .trace_data()
    );

    integer i, pc;
    reg [31:0] random_state = 32'h48a79c31;
    reg [31:0] a, b, value, noise, offset;
    reg [63:0] product;
    reg [2:0] funct3;
    reg [6:0] funct7;
    function [31:0] next_random(input [31:0] state);
        reg [31:0] x;
        begin x = state ^ (state << 13); x = x ^ (x >> 17); next_random = x ^ (x << 5); end
    endfunction
    task load_constant(input [4:0] rd, input [31:0] value_to_load);
        reg [31:0] upper;
        begin
            upper = value_to_load + 32'h800;
            memory[pc] = {upper[31:12], rd, 7'h37}; pc = pc + 1; // LUI
            memory[pc] = {value_to_load[11:0], rd, 3'b000, rd, 7'h13}; pc = pc + 1; // ADDI
        end
    endtask
    task store_result(input [4:0] rs, input [11:0] displacement);
        begin
            memory[pc] = {displacement[11:5], rs, 5'd4, 3'b010, displacement[4:0], 7'h23};
            pc = pc + 1;
        end
    endtask

    initial begin
        for (i = 0; i < 2048; i = i + 1) memory[i] = 32'h00000013; // NOP
        pc = 0;
        load_constant(5'd4, 32'h1000);
        for (i = 0; i < 32; i = i + 1) begin
            random_state = next_random(random_state); a = random_state;
            random_state = next_random(random_state); b = random_state | 1;
            random_state = next_random(random_state); noise = random_state;
            load_constant(5'd1, a); load_constant(5'd2, b);
            funct7 = 0; funct3 = 0; value = 0;
            case (i % 14)
                0: begin funct3 = 0; value = a + b; end
                1: begin funct3 = 0; funct7 = 7'h20; value = a - b; end
                2: begin funct3 = 4; value = a ^ b; end
                3: begin funct3 = 6; value = a | b; end
                4: begin funct3 = 7; value = a & b; end
                5: begin funct3 = 1; value = a << b[4:0]; end
                6: begin funct3 = 5; value = a >> b[4:0]; end
                7: begin funct3 = 5; funct7 = 7'h20; value = $signed(a) >>> b[4:0]; end
                8: begin funct3 = 2; value = $signed(a) < $signed(b); end
                9: begin funct3 = 3; value = a < b; end
                10: begin funct3 = 0; funct7 = 1; value = a * b; end
                11: begin funct3 = 3; funct7 = 1; product = {32'b0,a} * {32'b0,b}; value = product[63:32]; end
                12: begin funct3 = 5; funct7 = 1; value = a / b; end
                13: begin funct3 = 7; funct7 = 1; value = a % b; end
            endcase
            memory[pc] = {funct7, 5'd2, 5'd1, funct3, 5'd3, 7'h33}; pc = pc + 1;
            offset = i * 8;
            store_result(5'd3, offset[11:0]);
            expected[2*i] = value;
            memory[pc] = {offset[11:0], 5'd4, 3'b010, 5'd5, 7'h03}; pc = pc + 1; // LW
            memory[pc] = {noise[11:0], 5'd5, 3'b100, 5'd6, 7'h13}; pc = pc + 1; // XORI
            offset = offset + 4;
            store_result(5'd6, offset[11:0]);
            expected[2*i+1] = value ^ {{20{noise[11]}}, noise[11:0]};
        end
        memory[pc] = 32'h0000006f; // JAL x0,0: do not finish simulation on behalf of the DUT.
    end

    always @(posedge clk) begin
        if (!resetn) begin
            aw_pending <= 0; w_pending <= 0; bvalid <= 0; rvalid <= 0;
            writes <= 0; complete <= 0;
        end else begin
            if (trap && !complete) $fatal(1, "ERROR: independent CPU signature trapped");
            if (arvalid && arready) begin
                if (araddr[31:13] !== 0 || araddr[1:0] !== 0)
                    $fatal(1, "ERROR: independent CPU read address");
                rdata <= memory[araddr[12:2]];
                rvalid <= 1;
            end
            if (rvalid && rready) rvalid <= 0;
            if (awvalid && awready) begin saved_address <= awaddr; aw_pending <= 1; end
            if (wvalid && wready) begin saved_data <= wdata; saved_strobe <= wstrb; w_pending <= 1; end
            if (bvalid && bready) bvalid <= 0;
            if (aw_pending && w_pending && !bvalid) begin
                if (writes >= 64 || saved_address !== (32'h1000 + 4*writes) || saved_strobe !== 4'hf)
                    $fatal(1, "ERROR: independent CPU store sequence");
                if (saved_data !== expected[writes]) $fatal(1, "ERROR: independent CPU arithmetic signature");
                memory[saved_address[12:2]] <= saved_data;
                writes <= writes + 1;
                aw_pending <= 0; w_pending <= 0; bvalid <= 1;
                if (writes == 63) begin
                    complete <= 1;
                    // Separate stream: do not split the ISA suite's character-at-a-time '..OK' lines.
                    $fdisplay(32'h80000002, "PROJECT_RTL_CPU_SIGNATURE_PASS writes=64");
                end
            end
        end
    end
    initial begin
        repeat (200000) @(posedge clk);
        if (!complete) $fatal(1, "ERROR: independent CPU signature timeout");
    end
endmodule
