// z/|z| with CORDIC (architecture B). One sample per clock, latency ITERS + 2.
// Bit-exact with normalize_b() in dsp2si/models.py.
//
//   S0      block-normalise (common left shift of I, Q) and pre-rotate into the right half plane
//   S1..SN  vectoring step on (x, y) and the opposite rotation on (u, v), sharing the sign d_j
//   SN+1    undo the pre-rotation, round, saturate
// No multipliers and no tables: every stage is four add/subtracts and fixed shifts.
`default_nettype none

module normalize_cordic (
    input  wire               clk,
    input  wire               in_valid,
    input  wire signed [15:0] i,
    input  wire signed [15:0] q,
    output reg                out_valid,
    output reg  signed [15:0] x,
    output reg  signed [15:0] y
);
`include "cordic_params.vh"
    localparam integer W = 16 + 1 + GUARD + 3;   // sample + sign growth + guard + CORDIC growth

    // ---- S0
    function [4:0] msb17(input [16:0] a);   // index of the highest set bit (a > 0)
        integer b;
        begin
            msb17 = 5'd0;
            for (b = 0; b < 17; b = b + 1)
                if (a[b]) msb17 = b[4:0];
        end
    endfunction

    wire signed [16:0] ie = {i[15], i}, qe = {q[15], q};
    wire [16:0] ai = ie[16] ? -ie : ie;
    wire [16:0] aq = qe[16] ? -qe : qe;
    wire [16:0] amax = (ai > aq) ? ai : aq;
    wire [4:0]  hb = msb17((amax == 17'd0) ? 17'd1 : amax);
    wire [4:0]  sh = (hb >= 5'd14) ? 5'd0 : 5'd14 - hb;
    wire signed [17:0] in_n = $signed({ie[16], ie}) <<< sh;
    wire signed [17:0] qn_n = $signed({qe[16], qe}) <<< sh;
    wire left = in_n[17];
    wire up   = ~qn_n[17];
    wire signed [17:0] x_pre = left ? (up ? qn_n : -qn_n) : in_n;
    wire signed [17:0] y_pre = left ? (up ? -in_n : in_n) : qn_n;
    wire signed [W-1:0] x_ext = {{(W-18){x_pre[17]}}, x_pre};
    wire signed [W-1:0] y_ext = {{(W-18){y_pre[17]}}, y_pre};

    // pipeline registers as packed buses: stage j occupies bits [j*W +: W]
    reg [W*(ITERS+1)-1:0] xs, ys, us, vs;
    reg [ITERS:0] vld, lft, upp, zro;

    always @(posedge clk) begin
        vld[0] <= in_valid;
        lft[0] <= left;
        upp[0] <= up;
        zro[0] <= (i == 16'sd0) && (q == 16'sd0);
        xs[0 +: W] <= x_ext <<< GUARD;
        ys[0 +: W] <= y_ext <<< GUARD;
        us[0 +: W] <= INV_GAIN[W-1:0];
        vs[0 +: W] <= {W{1'b0}};
    end

    // ---- S1..SN: d = +1 when y < 0 (rotate up towards the x axis)
    genvar j;
    generate
        for (j = 0; j < ITERS; j = j + 1) begin : stage
            wire signed [W-1:0] xj = xs[j*W +: W], yj = ys[j*W +: W];
            wire signed [W-1:0] uj = us[j*W +: W], vj = vs[j*W +: W];
            wire neg = yj[W-1];
            always @(posedge clk) begin
                vld[j+1] <= vld[j];
                lft[j+1] <= lft[j];
                upp[j+1] <= upp[j];
                zro[j+1] <= zro[j];
                xs[(j+1)*W +: W] <= neg ? xj - (yj >>> j) : xj + (yj >>> j);
                ys[(j+1)*W +: W] <= neg ? yj + (xj >>> j) : yj - (xj >>> j);
                us[(j+1)*W +: W] <= neg ? uj + (vj >>> j) : uj - (vj >>> j);
                vs[(j+1)*W +: W] <= neg ? vj - (uj >>> j) : vj + (uj >>> j);
            end
        end
    endgenerate

    // ---- SN+1: undo the pre-rotation, round, saturate
    wire signed [W-1:0] uN = us[ITERS*W +: W], vN = vs[ITERS*W +: W];
    wire signed [W-1:0] u2 = lft[ITERS] ? (upp[ITERS] ? -vN : vN) : uN;
    wire signed [W-1:0] v2 = lft[ITERS] ? (upp[ITERS] ? uN : -uN) : vN;

    function signed [15:0] round_sat(input signed [W-1:0] val);
        reg signed [W-1:0] r;
        begin
            r = (val + (1 <<< (GUARD - 1))) >>> GUARD;
            if (r > 32767)       round_sat = 16'sd32767;
            else if (r < -32768) round_sat = -16'sd32768;
            else                 round_sat = r[15:0];
        end
    endfunction

    always @(posedge clk) begin
        out_valid <= vld[ITERS];
        x <= zro[ITERS] ? 16'sd0 : round_sat(u2);
        y <= zro[ITERS] ? 16'sd0 : round_sat(v2);
    end
endmodule

`default_nettype wire
