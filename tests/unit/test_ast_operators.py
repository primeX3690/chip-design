"""AST parser/printer round-trip + DIFFERENTIAL SIMULATION of every AST mutation operator (pure Python, no EDA tools).

For each operator and each corpus design we mutate, then simulate original and mutant on random stimulus with
hdl/pysim.py and require identical outputs. This is real behavioural evidence that the operators preserve semantics
(including Verilog's context-determined widths), independent of Yosys/Verilator."""
import random

from evohdl.evolutionary_engine import ast_operators as ao
from evohdl.evolutionary_engine.verilog_mutator import MUTATION_OPERATORS, MUTATION_KIND_NAMES
from evohdl.hdl.ast_nodes import PortDecl
from evohdl.hdl.parser import parse_source, parse_expr, ParseError
from evohdl.hdl.printer import print_source, pe
from evohdl.hdl.pysim import PySim, Widths
from evohdl.paths import SEED_DIR, DESIGNS_DIR

SEEDS = ["alu_basic", "comparator_4bit", "counter_4bit", "fsm_seqdet", "mult_seq8"]

# Hand-written corpus that exercises every rewrite (ternaries, subtraction, De Morgan, distributivity, CSE, if/else).
SYNTH = """
module synth_mix (
    input  wire [7:0] a, input wire [7:0] b, input wire [7:0] c, input wire sel, input wire [1:0] op,
    output wire [7:0] y1, output wire [8:0] y2, output reg [7:0] y3, output reg [7:0] y4, output wire [7:0] y5
);
    localparam [1:0] OP_A = 2'd0;
    localparam [1:0] OP_B = 2'd1;
    localparam [1:0] OP_C = 2'd2;
    localparam [1:0] OP_D = 2'd3;
    assign y1 = (a & b) | (a & c);
    assign y2 = {1'b0, a} - {1'b0, b};
    assign y5 = ~(a & b) ^ (a | ~b) ^ ~~c;
    always @(*) begin
        case (op)
            OP_A: y3 = a + b + c;
            OP_B: y3 = a ^ b;
            OP_C: y3 = (a & b) ^ (a & b);
            OP_D: y3 = sel ? a : b;
            default: y3 = 8'd0;
        endcase
        if (sel)
            y4 = (a & b) | c;
        else
            y4 = (a & b) | (a ^ b);
    end
endmodule
"""


def _ports(mod):
    W = Widths(mod)
    ins, outs = [], []
    for p in mod.ports:
        if isinstance(p, PortDecl):
            (ins if p.direction == "input" else outs).extend((n, W.sig[n]) for n in p.names)
    return ins, outs


def _behaviour_equal(src_a: str, src_b: str, cycles: int = 400, seed: int = 0) -> bool:
    ma, mb = parse_source(src_a).modules[0], parse_source(src_b).modules[0]
    ins, outs = _ports(ma)
    sa, sb = PySim(ma), PySim(mb)
    seq = any(n == "clk" for n, _ in ins)
    rng = random.Random(seed)
    for _ in range(cycles):
        vec = {}
        for n, w in ins:
            if n == "clk":
                continue
            if n == "rst_n":
                vec[n] = 0 if rng.random() < 0.05 else 1
            else:
                vec[n] = rng.randrange(1 << w)
        ra = sa.cycle(vec) if seq else sa.comb_eval(vec)
        rb = sb.cycle(vec) if seq else sb.comb_eval(vec)
        if any(ra[n] != rb[n] for n, _ in outs):
            return False
    return True


def _corpus():
    items = [(n, (SEED_DIR / f"{n}.v").read_text()) for n in SEEDS]
    items.append(("synth_mix", SYNTH))
    return items


def test_all_seeds_and_examples_parse_and_roundtrip():
    files = sorted(SEED_DIR.glob("*.v")) + sorted((DESIGNS_DIR / "examples").rglob("*.sv"))
    assert len(files) >= 8
    for f in files:
        a = parse_source(f.read_text())
        text = print_source(a)
        assert parse_source(text) == a, f.name
        assert print_source(parse_source(text)) == text, f.name  # printing is idempotent


def test_expression_printer_never_changes_precedence():
    for src in ["a + b * c", "(a + b) * c", "a & b | c ^ d", "~(a & b) | ~c", "x ? y : z ? p : q", "a << 2 + b",
                "{a, b[3:0], {2{c}}}", "a == b && c != d || e"]:
        e = parse_expr(src)
        assert parse_expr(pe(e)) == e, src


def test_registry_includes_all_ast_operators_consistently():
    assert len(MUTATION_OPERATORS) == len(MUTATION_KIND_NAMES) and len(set(MUTATION_KIND_NAMES)) == len(MUTATION_KIND_NAMES)
    for k in ao.AST_KIND_NAMES:
        assert k in MUTATION_KIND_NAMES
    assert len(ao.AST_OPERATORS) == len(ao.AST_KIND_NAMES)


def test_every_ast_operator_preserves_behaviour_on_random_stimulus():
    acted = {op.__name__: 0 for op in ao.AST_OPERATORS}
    for name, src in _corpus():
        for op in ao.AST_OPERATORS:
            for s in range(12):
                out, info = op(src, random.Random(s))
                if info.description.startswith("no-op"):
                    assert out == src
                    continue
                acted[op.__name__] += 1
                assert out != src or "regex fallback" in info.description
                assert _behaviour_equal(src, out, cycles=150, seed=s), f"{op.__name__} broke {name}: {info.description}"
    never = [k for k, v in acted.items() if v == 0]
    assert not never, f"operators that never acted on the corpus: {never}"


def test_chained_mutations_stay_equivalent_and_parseable():
    """Apply 25 random AST operators in a row (what the GA does over generations) -> still the same behaviour."""
    for name, src in _corpus():
        rng = random.Random(7)
        cur = src
        for _ in range(25):
            cur, _info = rng.choice(ao.AST_OPERATORS)(cur, rng)
            parse_source(cur)  # must stay valid
        assert _behaviour_equal(src, cur, cycles=200, seed=1), name


def test_cse_extracts_wire_and_keeps_outputs():
    src = SYNTH
    out, info = ao.mutate_ast_cse(src, random.Random(0))
    assert not info.description.startswith("no-op") and "wire [7:0] _cse0" in out
    assert _behaviour_equal(src, out)


def test_cse_refuses_operands_assigned_inside_comb_blocks():
    src = ("module m(input wire a, input wire b, output reg y, output reg z);\n"
           "  reg t;\n  always @(*) begin\n    t = a;\n    y = t & b;\n    z = t & b;\n  end\nendmodule\n")
    out, info = ao.mutate_ast_cse(src, random.Random(0))
    assert info.description.startswith("no-op") and out == src


def test_case_reorder_requires_distinct_constant_labels():
    dup = ("module m(input wire [1:0] s, output reg y);\n always @(*) case (s)\n 2'd0: y = 1'b0;\n 2'd0: y = 1'b1;\n"
           " 2'd2: y = 1'b0;\n default: y = 1'b1;\n endcase\nendmodule\n")
    out, info = ao.mutate_ast_case_reorder(dup, random.Random(0))
    assert info.description.startswith("no-op")
    casez = dup.replace("case (s)", "casez (s)").replace("2'd0: y = 1'b1;", "2'd1: y = 1'b1;")
    assert ao.mutate_ast_case_reorder(casez, random.Random(0))[1].description.startswith("no-op")


def test_if_ternary_both_directions():
    s1 = "module m(input wire c, input wire a, input wire b, output reg y);\n always @(*) begin\n if (c) y = a; else y = b;\n end\nendmodule\n"
    out, _ = ao.mutate_ast_if_ternary(s1, random.Random(0))
    assert "y = c ? a : b;" in out or "y = (c ? a : b);" in out
    out2, _ = ao.mutate_ast_if_ternary(out, random.Random(0))
    assert "if (c)" in out2 and _behaviour_equal(s1, out2)


def test_unparseable_source_falls_back_or_noops_without_crashing():
    weird = "module m(input a, output y);\n generate genvar i; endgenerate\n assign y = a;\nendmodule\n"
    for op in ao.AST_OPERATORS:
        out, info = op(weird, random.Random(0))
        assert isinstance(out, str)
    out, info = ao.mutate_ast_commutative("// no parse\n  r = a + b;\n", random.Random(0))
    assert "regex fallback" in info.description and "r = b + a;" in out


def test_parser_rejects_unsupported_constructs_cleanly():
    for bad in ["module m; initial begin end endmodule", "module m; function f; endfunction endmodule",
                "module m(input a); always @(posedge a) for (;;) ; endmodule", "`define X 1\nmodule m; endmodule"]:
        try:
            parse_source(bad)
        except ParseError:
            continue
        raise AssertionError(f"expected ParseError for {bad!r}")
