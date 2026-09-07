// counter_4bit_tb.v
// Add to: rtl_modules/testbenches/counter_4bit_tb.v
//
// Correctness check for counter_4bit.v — wire this into your existing
// Wired into the Verilator fitness-eval flow, same as alu_basic.
// Every evolved variant must pass this bit-exact before area/timing counts.

module counter_4bit_tb;
    reg clk;
    reg rst_n;
    reg en;
    wire [3:0] count;

    integer errors = 0;
    integer i;
    reg [3:0] expected;

    counter_4bit dut (
        .clk(clk),
        .rst_n(rst_n),
        .en(en),
        .count(count)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0;
        rst_n = 0;
        en = 0;
        expected = 4'b0000;

        @(negedge clk);
        rst_n = 1;

        // Test 1: counting with en=1
        en = 1;
        for (i = 0; i < 20; i = i + 1) begin
            @(negedge clk);
            expected = expected + 1'b1;
            if (count !== expected) begin
                $display("MISMATCH at step %0d: expected=%b got=%b", i, expected, count);
                errors = errors + 1;
            end
        end

        // Test 2: enable held low should freeze the count
        en = 0;
        for (i = 0; i < 5; i = i + 1) begin
            @(negedge clk);
            if (count !== expected) begin
                $display("MISMATCH (en=0 hold) at step %0d: expected=%b got=%b", i, expected, count);
                errors = errors + 1;
            end
        end

        // Test 3: async reset mid-count
        en = 1;
        @(negedge clk);
        rst_n = 0;
        @(negedge clk);
        expected = 4'b0000;
        if (count !== expected) begin
            $display("MISMATCH (reset) got=%b", count);
            errors = errors + 1;
        end
        rst_n = 1;

        if (errors == 0)
            $display("PASS: counter_4bit_tb — all checks correct");
        else
            $display("FAIL: counter_4bit_tb — %0d mismatches", errors);

        $finish;
    end
endmodule