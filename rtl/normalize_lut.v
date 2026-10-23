// z/|z| with a table-based 1/sqrt (architecture A). One sample per clock, latency 6.
// Bit-accurate with normalize_a() in dsp2si/models.py.
//
//   S1  P = I^2 + Q^2 (<= 2^31)              2 multipliers
//   S2  s = clz(P) & ~1, m = P << s          priority encoder + barrel shifter
//   S3  T[k], D[k] read, k = m[31:23]        384-entry ROMs
//   S4  r = T - ((D * f + 2048) >> 12)       1 small multiplier
//   S5  I * r, Q * r                         2 multipliers
//   S6  round, shift by 18 - s/2, saturate
`default_nettype none

module normalize_lut #(
    parameter BASE_HEX  = "rsqrt_base.hex",
    parameter SLOPE_HEX = "rsqrt_slope.hex"
) (
    input  wire               clk,
    input  wire               in_valid,
    input  wire signed [15:0] i,
    input  wire signed [15:0] q,
    output reg                out_valid,
    output reg  signed [15:0] x,
    output reg  signed [15:0] y
);
    reg [18:0] rom_base [0:383];
    reg [9:0]  rom_slope[0:383];
    initial begin
        $readmemh(BASE_HEX, rom_base);
        $readmemh(SLOPE_HEX, rom_slope);
    end

    // valid and sample pipeline
    reg [5:0] v;
    reg signed [15:0] i1, q1, i2, q2, i3, q3, i4, q4;

    // S1: power
    reg [31:0] p1;
    always @(posedge clk) begin
        v[0] <= in_valid;
        i1 <= i;
        q1 <= q;
        p1 <= i * i + q * q;
    end

    // S2: even normalisation shift
    function [4:0] clz32(input [31:0] w);
        integer b;
        begin
            clz32 = 5'd31;  // w == 0 is handled separately
            for (b = 0; b < 32; b = b + 1)
                if (w[b]) clz32 = 5'd31 - b[4:0];
        end
    endfunction

    reg [4:0]  s2;
    reg [31:0] m2;
    reg        z2;
    always @(posedge clk) begin
        v[1] <= v[0];
        i2 <= i1;
        q2 <= q1;
        z2 <= (p1 == 32'd0);
        s2 <= clz32(p1) & 5'b11110;
        m2 <= p1 << (clz32(p1) & 5'b11110);
    end

    // S3: table read
    reg [18:0] t3;
    reg [9:0]  d3;
    reg [11:0] f3;
    reg [4:0]  s3;
    reg        z3;
    wire [8:0] k2 = m2[31:23];
    always @(posedge clk) begin
        v[2] <= v[1];
        i3 <= i2;
        q3 <= q2;
        s3 <= s2;
        z3 <= z2;
        t3 <= rom_base[k2 - 9'd128];
        d3 <= rom_slope[k2 - 9'd128];
        f3 <= m2[22:11];
    end

    // S4: linear interpolation
    reg [18:0] r4;
    reg [4:0]  s4;
    reg        z4;
    wire [21:0] df = d3 * f3;
    wire [21:0] corr = (df + 22'd2048) >> 12;  // < 2^10
    always @(posedge clk) begin
        v[3] <= v[2];
        i4 <= i3;
        q4 <= q3;
        s4 <= s3;
        z4 <= z3;
        r4 <= t3 - corr[18:0];
    end

    // S5: scale the sample
    reg signed [35:0] px5, py5;
    reg [4:0] sh5;
    reg       z5;
    wire signed [19:0] r4s = {1'b0, r4};
    always @(posedge clk) begin
        v[4] <= v[3];
        px5 <= i4 * r4s;
        py5 <= q4 * r4s;
        sh5 <= 5'd18 - (s4 >> 1);
        z5 <= z4;
    end

    // S6: round half up, shift, saturate
    function signed [15:0] round_sat(input signed [35:0] val, input [4:0] sh);
        reg signed [35:0] r;
        begin
            r = (val + (36'sd1 <<< (sh - 5'd1))) >>> sh;
            if (r > 36'sd32767)       round_sat = 16'sd32767;
            else if (r < -36'sd32768) round_sat = -16'sd32768;
            else                      round_sat = r[15:0];
        end
    endfunction

    always @(posedge clk) begin
        v[5] <= v[4];
        out_valid <= v[4];
        x <= z5 ? 16'sd0 : round_sat(px5, sh5);
        y <= z5 ? 16'sd0 : round_sat(py5, sh5);
    end
endmodule

`default_nettype wire
