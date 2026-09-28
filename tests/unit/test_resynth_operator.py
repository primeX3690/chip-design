"""
tests/unit/test_resynth_operator.py

Regression test for the Stage-6 addition (2026-09):
2_evolutionary_engine/resynth_operator.py -- a structural mutation operator
that re-synthesizes the current genome via an alternate Yosys/ABC
optimization strategy instead of randomly perturbing RTL source text (see
the module's own docstring for the full rationale -- this exists because
every prior operator turned out to be structurally incapable of improving
picorv32_alu's area: 3 of 4 change semantics and get rejected, the 4th is
hard-coded to a signal name alu_basic has and picorv32_alu doesn't).

Uses mocked run_guarded output so it runs without a real Yosys install.
"""
import random
import sys
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "2_evolutionary_engine"))
sys.path.append(str(Path(__file__).resolve().parents[2] / "3_sandbox_time"))

import resynth_operator as ro  # noqa: E402
from process_guard import GuardedResult  # noqa: E402


def test_configure_sets_module_context():
    ro.configure("picorv32_alu", yosys_bin="yosys", timeout_sec=45.0)
    assert ro._module_name == "picorv32_alu"
    assert ro._yosys_bin == "yosys"
    assert ro._timeout_sec == 45.0


def test_successful_resynth_returns_new_source(monkeypatch):
    ro.configure("alu_basic")
    fake_output = "module alu_basic(a,b); // resynthesized netlist\nendmodule\n"

    def fake_run_guarded(command, timeout_sec, cwd):
        # Simulate Yosys having written the -o file the script asked for.
        out_path = Path(cwd) / "resynth_out.v"
        out_path.write_text(fake_output)
        return GuardedResult(command=command, returncode=0, stdout="ok")

    monkeypatch.setattr(ro, "run_guarded", fake_run_guarded)

    original = "module alu_basic(a,b); assign b=a; endmodule"
    mutated, info = ro.mutate_resynth_alt_strategy(original, random.Random(1))

    assert mutated == fake_output
    assert info.kind == "resynth_alt_strategy"
    assert "re-synthesized via" in info.description
    assert any(name in info.description for name in ro.RESYNTH_STRATEGIES)


def test_yosys_failure_is_a_safe_noop(monkeypatch):
    def fake_run_guarded(command, timeout_sec, cwd):
        return GuardedResult(command=command, returncode=1, stderr="syntax error")

    monkeypatch.setattr(ro, "run_guarded", fake_run_guarded)

    original = "module alu_basic(a,b); assign b=a; endmodule"
    mutated, info = ro.mutate_resynth_alt_strategy(original, random.Random(2))

    assert mutated == original, "on failure, the operator must return the UNCHANGED source, never garbage"
    assert "no-op" in info.description


def test_timeout_is_a_safe_noop(monkeypatch):
    def fake_run_guarded(command, timeout_sec, cwd):
        return GuardedResult(command=command, returncode=1, timed_out=True)

    monkeypatch.setattr(ro, "run_guarded", fake_run_guarded)

    original = "module alu_basic(a,b); assign b=a; endmodule"
    mutated, info = ro.mutate_resynth_alt_strategy(original, random.Random(3))

    assert mutated == original
    assert "timeout" in info.description


def test_registered_in_operator_pool_and_kind_names_stay_aligned():
    import verilog_mutator as vm
    assert vm.mutate_resynth_alt_strategy in vm.MUTATION_OPERATORS
    assert "resynth_alt_strategy" in vm.MUTATION_KIND_NAMES
    assert len(vm.MUTATION_OPERATORS) == len(vm.MUTATION_KIND_NAMES), (
        "reward_backprop.py keys operator credit off positional alignment between "
        "these two lists -- they must never drift apart in length"
    )
