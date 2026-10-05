"""
design_bundle.py
-----------------
Multi-file / hierarchical design support (gap H).

A "bundle" is one or more Verilog/SystemVerilog files plus a top module. The GA's
genome stays a single string, so the bundle is concatenated into ONE source text
(`` `include `` directives inlined, duplicate `timescale dropped). Yosys resolves the
hierarchy (`hierarchy -top`) and, for multi-module designs, the tools flatten it so
`stat` reports one module.

Honest limits (see README): SystemVerilog is read with Yosys' *built-in* frontend
(`read_verilog -sv`), which covers `logic`, `always_comb/ff`, simple packages/enums
but not interfaces, classes or most of the verification subset. List package files
before the files that use them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_MODULE_RE = re.compile(r"^\s*(?:macro)?module\s+(\w+)", re.MULTILINE)
_INCLUDE_RE = re.compile(r'^\s*`include\s+"([^"]+)"[^\n]*$', re.MULTILINE)
_TIMESCALE_RE = re.compile(r"^\s*`timescale[^\n]*$", re.MULTILINE)
# Strong SystemVerilog-only markers (no common Verilog-2001 identifiers).
_SV_STRONG_RE = re.compile(
    r"\b(logic|always_comb|always_ff|always_latch|typedef|package|endpackage|"
    r"interface|endinterface|struct|enum)\b"
)
SV_EXTENSIONS = {".sv", ".svh"}


def strip_comments(source: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", source))


def looks_like_systemverilog(source: str) -> bool:
    return bool(_SV_STRONG_RE.search(strip_comments(source)))


def list_modules(source: str) -> List[str]:
    return _MODULE_RE.findall(strip_comments(source))


def count_modules(source: str) -> int:
    return len(list_modules(source))


def find_top_candidates(source: str) -> List[str]:
    """Modules that no other module instantiates (heuristic, regex based)."""
    clean = strip_comments(source)
    modules = list_modules(clean)
    # Blank out `module NAME` headers so a declaration is never mistaken for an instantiation.
    body = re.sub(r"\b(?:macro)?module\s+\w+", "module", clean)
    instantiated: Set[str] = set()
    for name in modules:
        if re.search(rf"\b{re.escape(name)}\s*(?:#\s*\([^;]*?\))?\s*\w+\s*\(", body):
            instantiated.add(name)
    return [m for m in modules if m not in instantiated]


@dataclass
class DesignBundle:
    source: str
    top: Optional[str]
    files: List[str] = field(default_factory=list)
    modules: List[str] = field(default_factory=list)
    is_systemverilog: bool = False

    @property
    def n_modules(self) -> int:
        return len(self.modules)

    @property
    def suffix(self) -> str:
        return ".sv" if self.is_systemverilog else ".v"


def _inline_includes(text: str, base_dir: Path, include_dirs: Sequence[Path],
                     seen: Set[Path], depth: int = 0) -> str:
    if depth > 8:
        raise ValueError("`include nesting deeper than 8 levels (cycle?)")

    def repl(m: re.Match) -> str:
        name = m.group(1)
        for d in [base_dir, *include_dirs]:
            cand = (d / name).resolve()
            if cand.is_file():
                if cand in seen:
                    return f"// (already included: {name})"
                seen.add(cand)
                inner = cand.read_text()
                return _inline_includes(inner, cand.parent, include_dirs, seen, depth + 1)
        raise FileNotFoundError(f"`include \"{name}\" not found (searched {base_dir} and include_dirs)")

    return _INCLUDE_RE.sub(repl, text)


def load_design_bundle(
    paths: Sequence[str | Path],
    top: Optional[str] = None,
    root: Optional[Path] = None,
    include_dirs: Sequence[str | Path] = (),
) -> DesignBundle:
    """Read files in the given order and merge them into one source string.

    A single plain file is returned verbatim (no header, no rewriting) so existing
    single-module runs behave exactly as before.
    """
    root = Path(root) if root else Path.cwd()
    resolved: List[Path] = []
    for p in paths:
        pp = Path(p)
        pp = pp if pp.is_absolute() else root / pp
        if pp.is_dir():
            resolved.extend(sorted(x for x in pp.iterdir() if x.suffix in {".v", ".sv"}))
        else:
            resolved.append(pp)
    if not resolved:
        raise FileNotFoundError("design bundle has no files")
    for p in resolved:
        if not p.exists():
            raise FileNotFoundError(f"Design file not found: {p}")

    inc_dirs = [Path(d) if Path(d).is_absolute() else root / d for d in include_dirs]
    sv = any(p.suffix in SV_EXTENSIONS for p in resolved)

    if len(resolved) == 1 and not _INCLUDE_RE.search(resolved[0].read_text()):
        text = resolved[0].read_text()
    else:
        parts: List[str] = []
        seen_timescale = False
        for p in resolved:
            body = _inline_includes(p.read_text(), p.parent, inc_dirs, {p.resolve()})
            if seen_timescale:
                body = _TIMESCALE_RE.sub("", body)
            elif _TIMESCALE_RE.search(body):
                seen_timescale = True
            parts.append(f"// ---- file: {p.name} ----\n{body.rstrip()}\n")
        text = "\n".join(parts)

    sv = sv or looks_like_systemverilog(text)
    modules = list_modules(text)
    if top is None:
        cands = find_top_candidates(text)
        if len(cands) != 1:
            raise ValueError(
                f"Cannot infer the top module (candidates: {cands or modules}); "
                f"set `module_name` (or `top_module`) in the config."
            )
        top = cands[0]
    elif top not in modules:
        raise ValueError(f"Top module '{top}' not found in the design files (modules: {modules})")

    return DesignBundle(source=text, top=top, files=[str(p) for p in resolved],
                        modules=modules, is_systemverilog=sv)


def load_seed_from_config(config: Dict, root: Path) -> DesignBundle:
    """Config keys: `seed_files` (list, multi-file) OR `seed_design` (one path);
    optional `top_module` (defaults to `module_name`), `include_dirs`."""
    top = config.get("top_module") or config.get("module_name")
    include_dirs = config.get("include_dirs", [])
    if config.get("seed_files"):
        return load_design_bundle(config["seed_files"], top=top, root=root, include_dirs=include_dirs)
    seed = config.get("seed_design", "designs/seed/alu_basic.v")
    return load_design_bundle([seed], top=top, root=root, include_dirs=include_dirs)
