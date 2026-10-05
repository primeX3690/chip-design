"""
resynth_operator.py
---------------------
Stage-6 addition (2026-09): a fundamentally different KIND of mutation
operator from everything in verilog_mutator.py.

THE PROBLEM THIS SOLVES
Every existing operator (operator_swap, constant_tweak, shift_amount,
drop_redundant_default) works by randomly perturbing RTL *source text*.
Investigation of a real 40-generation picorv32_alu run (2026-09) confirmed
why that structurally can't find area improvements on a real, already-clean
block: operator_swap/constant_tweak/shift_amount change the ALU's actual
arithmetic/logic semantics on whichever line they touch, so they almost
always fail the simulation-based correctness check and get rejected;
drop_redundant_default is hard-coded to alu_basic's `carry_out` signal
name and is a pure no-op on any other module (picorv32_alu has no such
signal at all). Net effect: on picorv32_alu, ~0% of mutation attempts can
ever both (a) survive correctness checking AND (b) reduce area -- which is
exactly the 0%-improvement-after-40-generations result that run produced.

THE FIX: mutate the NETLIST via alternate synthesis strategies, not the
SOURCE via random text edits.
Instead of guessing at semantic-preserving text edits, this operator
re-synthesizes the CURRENT genome through a *different* Yosys/ABC
optimization recipe than the one used for scoring (`share`/`wreduce`
resource-sharing passes, alternate `abc` scripts that explore different
area/delay-tradeoff local optima, extra `opt -full` rounds, etc.), then
writes the result back out as structural Verilog and uses THAT as the
mutant genome.

Why this is safe by construction: the output is synthesized FROM the
current genome by Yosys/ABC (mature, widely-used EDA tools), not produced
by randomly editing source text -- so it is functionally equivalent to
whatever it started from by the same logic that makes any two synthesis
runs of one behavioral design equivalent, not by luck passing N test
vectors. (The existing simulation + Stage-4 formal-equivalence check still
run on top of this as usual defense in depth -- this operator does not
bypass them, it just gives them something with a much better chance of
actually being both correct AND smaller/faster.)

This is also module-agnostic: it works identically on alu_basic,
picorv32_alu, counter_4bit, or any future seed design, since it never
looks at signal names or case-statement structure at all.
"""

from __future__ import annotations

import random
import shutil
import tempfile
import logging
from dataclasses import dataclass
from pathlib import Path

import sys
from evohdl.sandbox.process_guard import run_guarded  # noqa: E402
from evohdl.paths import SEED_DIR

logger = logging.getLogger("EvoHDL.resynth_operator")

# Each strategy is a distinct Yosys/ABC recipe -- deliberately varied so
# different runs explore different points in the area/delay design space,
# the same way real synthesis-exploration flows try multiple ABC scripts
# and keep whichever result is best (that IS a legitimate, real EDA
# technique, not a shortcut).
RESYNTH_STRATEGIES: dict[str, str] = {
    "share_wreduce": "proc; opt; wreduce; share; opt -full; techmap; abc; opt_clean",
    "double_abc": "proc; opt; techmap; opt; abc; opt; abc; opt_clean",
    "fast_abc": "proc; opt; techmap; opt; abc -fast; opt_clean",
    "aggressive_full_opt": "proc; opt -full; wreduce; share; techmap; opt -full; abc; opt_clean",
}


@dataclass
class Mutation:
    kind: str
    description: str


# Module-level context, set once per run by EvolutionOrchestrator before any
# mutation happens (see evolution_orchestrator.py's bootstrap()). Defaults
# are safe no-op-friendly fallbacks so directly calling this operator (e.g.
# from a unit test) without configuring anything never crashes -- it will
# just report a no-op if yosys isn't reachable, same as every other
# operator's "nothing eligible found" no-op pattern.
_module_name = "alu_basic"
_yosys_bin = "yosys"
_timeout_sec = 30.0


def configure(module_name: str, yosys_bin: str = "yosys", timeout_sec: float = 30.0) -> None:
    global _module_name, _yosys_bin, _timeout_sec
    _module_name = module_name
    _yosys_bin = yosys_bin
    _timeout_sec = timeout_sec


def _run_recipe(source: str, recipe_body: str, label: str, kind: str, ok_prefix: str) -> tuple[str, Mutation]:
    """Run one Yosys recipe over `source` and return its written-out Verilog as the new genome.

    Any failure (bad pass for this Yosys version, timeout, empty output) is a safe no-op that returns
    the original source -- so a recipe that is invalid on the user's Yosys just gets zero credit.
    Multi-module sources are flattened and SystemVerilog is read with `-sv` (auto-detected).
    """
    from evohdl.sandbox.design_bundle import count_modules, looks_like_systemverilog
    sv = looks_like_systemverilog(source)
    flatten = count_modules(source) > 1
    workdir = Path(tempfile.mkdtemp(prefix="evohdl_resynth_"))
    try:
        design_path = workdir / (f"{_module_name}.sv" if sv else f"{_module_name}.v")
        design_path.write_text(source)
        out_path = workdir / "resynth_out.v"

        script = f"""
{"read_verilog -sv" if sv else "read_verilog"} {design_path.as_posix()}
hierarchy -check -top {_module_name}
{"flatten" if flatten else ""}
{recipe_body}
write_verilog -noattr {out_path.as_posix()}
"""
        script_path = workdir / "resynth.ys"
        script_path.write_text(script)

        result = run_guarded(
            [_yosys_bin, "-Q", "-T", "-s", str(script_path)],
            timeout_sec=_timeout_sec, cwd=str(workdir),
        )

        if not result.ok:
            reason = "timeout" if result.timed_out else "yosys error"
            return source, Mutation(kind, f"no-op: {reason} running strategy '{label}'")

        if not out_path.exists() or not out_path.read_text().strip():
            return source, Mutation(kind, f"no-op: strategy '{label}' produced no output")

        return out_path.read_text(), Mutation(kind, f"{ok_prefix} '{label}'")
    except Exception as e:  # noqa: BLE001 -- never let a subprocess/IO hiccup crash the GA loop
        return source, Mutation(kind, f"no-op: unexpected error ({e})")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def mutate_resynth_alt_strategy(source: str, rng: random.Random) -> tuple[str, Mutation]:
    strategy_name, opt_script = rng.choice(list(RESYNTH_STRATEGIES.items()))
    return _run_recipe(source, opt_script, strategy_name, "resynth_alt_strategy",
                       "re-synthesized via")


# ---------------------------------------------------------------------------
# Yosys pass-guided mutation (gap B): the genome is changed by *running a composed Yosys pass
# pipeline* instead of editing text. Output is always valid Verilog and every step is a
# semantics-preserving netlist transformation (equivalence is still verified by the fitness gate).
# ---------------------------------------------------------------------------

# (name, yosys command) in canonical order; a random ORDER-PRESERVING subset is applied.
PRUNE_SHARE_PASSES: list[tuple[str, str]] = [
    ("wreduce", "wreduce"),
    ("opt_expr", "opt_expr -full"),
    ("opt_muxtree", "opt_muxtree"),
    ("opt_reduce", "opt_reduce -full"),
    ("peepopt", "peepopt"),
    ("share", "alumacc; share -aggressive"),
    ("opt_merge", "opt_merge -share_all"),
    ("opt_clean", "opt_clean -purge"),
]
# Optional extraction step before the final tech-map (adder / reduction recovery).
EXTRACT_PASSES: list[tuple[str, str]] = [
    ("none", ""),
    ("extract_fa", "extract_fa -fa; techmap; opt"),
    ("extract_reduce", "extract_reduce; techmap; opt"),
]
# `abc -g` gate-set swapping: each choice maps the logic onto a different primitive-gate library.
TECHMAP_GATE_SETS: list[tuple[str, str]] = [
    ("abc", "abc"),
    ("abc_fast", "abc -fast"),
    ("abc_g_simple", "abc -g simple"),
    ("abc_g_gates", "abc -g gates"),
    ("abc_g_aig", "abc -g AND,NAND,OR,NOR,ANDNOT,ORNOT"),
    ("abc_g_nand_nor", "abc -g NAND,NOR"),
    ("abc_g_aoi_mux", "abc -g AND,OR,XOR,MUX,AOI3,OAI3"),
]


def compose_pass_pipeline(rng: random.Random) -> tuple[str, str]:
    """Build (label, yosys_script_body) from a random prune/share subset, extraction and gate set."""
    k = rng.randint(1, min(4, len(PRUNE_SHARE_PASSES)))
    chosen_idx = sorted(rng.sample(range(len(PRUNE_SHARE_PASSES)), k))
    pre = [PRUNE_SHARE_PASSES[i] for i in chosen_idx]
    ext = rng.choice(EXTRACT_PASSES)
    gates = rng.choice(TECHMAP_GATE_SETS)

    steps = ["proc", "opt"] + [cmd for _, cmd in pre] + ["techmap", "opt"]
    if ext[1]:
        steps.append(ext[1])
    steps += [gates[1], "opt_clean"]
    label = "+".join([n for n, _ in pre] + ([ext[0]] if ext[1] else []) + [gates[0]])
    return label, "; ".join(steps)


def mutate_yosys_pass_pipeline(source: str, rng: random.Random) -> tuple[str, Mutation]:
    label, body = compose_pass_pipeline(rng)
    return _run_recipe(source, body, label, "yosys_pass_pipeline", "ran Yosys pass pipeline")


if __name__ == "__main__":
    from pathlib import Path as _P
    seed = SEED_DIR / "alu_basic.v"
    configure("alu_basic")
    src = seed.read_text()
    mutated, info = mutate_resynth_alt_strategy(src, random.Random(1))
    print(f"{info.kind}: {info.description}")
    print(f"Output length: {len(mutated)} chars (original: {len(src)})")
