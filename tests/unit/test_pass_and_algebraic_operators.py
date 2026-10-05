"""Gap B (Yosys pass-guided mutations) and F (structure-aware rewrites). Yosys is mocked."""
import random
from pathlib import Path

from evohdl.evolutionary_engine import resynth_operator as ro
from evohdl.evolutionary_engine import algebraic_rewrites as ar
from evohdl.evolutionary_engine.verilog_mutator import MUTATION_OPERATORS, MUTATION_KIND_NAMES
from evohdl.sandbox.process_guard import GuardedResult


def test_registry_is_consistent_and_includes_new_operators():
    assert len(MUTATION_OPERATORS) == len(MUTATION_KIND_NAMES)
    assert len(set(MUTATION_KIND_NAMES)) == len(MUTATION_KIND_NAMES)
    for k in ("yosys_pass_pipeline", "ast_commutative", "ast_demorgan", "ast_sub_as_add", "ast_ternary_invert", "ast_cse"):
        assert k in MUTATION_KIND_NAMES


def test_compose_pass_pipeline_is_valid_ordered_and_varied():
    seen = set()
    for s in range(60):
        label, body = ro.compose_pass_pipeline(random.Random(s))
        seen.add(label)
        assert body.startswith("proc; opt;") and body.endswith("opt_clean") and "abc" in body
        names = [n for n, _ in ro.PRUNE_SHARE_PASSES]
        used = [n for n in label.split("+") if n in names]
        assert used == sorted(used, key=names.index)  # canonical order preserved
    assert len(seen) > 20  # genuinely explores different pipelines


def test_pass_pipeline_operator_returns_yosys_output_and_runs_requested_passes(monkeypatch):
    ro.configure("m")
    captured = {}

    def fake(command, timeout_sec, cwd):
        captured["script"] = (Path(cwd) / "resynth.ys").read_text()
        (Path(cwd) / "resynth_out.v").write_text("module m(); endmodule\n")
        return GuardedResult(command=command, returncode=0, stdout="ok")

    monkeypatch.setattr(ro, "run_guarded", fake)
    out, info = ro.mutate_yosys_pass_pipeline("module m(); endmodule", random.Random(3))
    assert info.kind == "yosys_pass_pipeline" and "ran Yosys pass pipeline" in info.description
    assert out == "module m(); endmodule\n" and "abc" in captured["script"]
    assert "read_verilog -sv" not in captured["script"] and "flatten" not in captured["script"].split("hierarchy")[1].split("\n")[1]


def test_pass_pipeline_flattens_and_uses_sv_for_hierarchical_sv(monkeypatch):
    ro.configure("top")
    captured = {}

    def fake(command, timeout_sec, cwd):
        captured["script"] = (Path(cwd) / "resynth.ys").read_text()
        (Path(cwd) / "resynth_out.v").write_text("module top(); endmodule\n")
        return GuardedResult(command=command, returncode=0, stdout="ok")

    monkeypatch.setattr(ro, "run_guarded", fake)
    src = "module sub(input logic a); endmodule\nmodule top(input logic a); sub u(.a(a)); endmodule\n"
    ro.mutate_yosys_pass_pipeline(src, random.Random(1))
    assert "read_verilog -sv" in captured["script"] and "\nflatten\n" in captured["script"]


def test_pass_pipeline_failure_is_safe_noop(monkeypatch):
    monkeypatch.setattr(ro, "run_guarded", lambda c, timeout_sec, cwd: GuardedResult(command=c, returncode=1, stderr="bad pass"))
    src = "module m(); endmodule"
    out, info = ro.mutate_yosys_pass_pipeline(src, random.Random(0))
    assert out == src and info.description.startswith("no-op")


# ---- algebraic rewrites: check the identities hold by brute force over all 4-bit inputs ----
def _ev(expr, env):
    expr = expr.replace("~", "^MASK^").replace("1'b1", "1")  # not used for eval of ~; see below
    return expr


def test_commutative_swap_swaps_operands():
    src = "    result = a + b;\n    assign y = p & q;\n"
    outs = {ar.mutate_commutative_swap(src, random.Random(s))[0] for s in range(10)}
    assert "    result = b + a;\n    assign y = p & q;\n" in outs
    assert "    result = a + b;\n    assign y = q & p;\n" in outs


def test_commutative_swap_ignores_nonblocking_and_noncommutative():
    src = "    q <= a & b;\n    r = a - b;\n"
    out, info = ar.mutate_commutative_swap(src, random.Random(0))
    assert out == src and info.description.startswith("no-op")


def test_demorgan_both_directions_and_truth_table():
    out, _ = ar.mutate_demorgan("assign y = ~(a & b);", random.Random(0))
    assert out == "assign y = (~a | ~b);"
    out2, _ = ar.mutate_demorgan("assign y = (~a | ~b);", random.Random(0))
    assert out2 == "assign y = ~(a & b);"
    out3, _ = ar.mutate_demorgan("assign y = ~(a | b);", random.Random(0))
    assert out3 == "assign y = (~a & ~b);"
    for a in range(16):
        for b in range(16):
            assert (~(a & b)) & 15 == ((~a) | (~b)) & 15 and (~(a | b)) & 15 == ((~a) & (~b)) & 15


def test_sub_as_add_identity_and_rewrite():
    out, _ = ar.mutate_sub_as_add("    {carry, res} = a - b;", random.Random(0))
    assert out == "    {carry, res} = a + ~b + 1'b1;"
    for width in (4, 9):
        m = (1 << width) - 1
        for a in range(16):
            for b in range(16):
                assert (a - b) & m == (a + (~b & m) + 1) & m


def test_ternary_invert_rewrite_and_equivalence():
    out, _ = ar.mutate_ternary_invert("    y = sel ? x : z;", random.Random(0))
    assert out == "    y = (!sel) ? z : x;"
    for sel in range(4):
        for x, z in ((1, 2), (5, 7)):
            assert (x if sel else z) == (z if (not sel) else x)


def test_all_algebraic_operators_noop_cleanly_on_unrelated_text():
    for op in ar.ALGEBRAIC_OPERATORS:
        out, info = op("module m; endmodule", random.Random(0))
        assert out == "module m; endmodule" and info.description.startswith("no-op")
