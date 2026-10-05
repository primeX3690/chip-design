"""Tokenizer for the Verilog subset in ast_nodes.py."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


class UnsupportedSyntax(Exception):
    """Source uses a construct outside the supported subset (callers fall back to text-level logic)."""


@dataclass
class Token:
    kind: str      # id | num | op | kw | eof
    text: str
    pos: int


KEYWORDS = {
    "module", "endmodule", "input", "output", "inout", "wire", "reg", "logic", "integer", "signed",
    "unsigned", "parameter", "localparam", "assign", "always", "always_comb", "always_ff", "always_latch",
    "begin", "end", "if", "else", "case", "casez", "casex", "endcase", "default", "posedge", "negedge",
    "or", "initial", "generate", "endgenerate", "genvar", "function", "endfunction", "task", "endtask",
    "for", "while", "repeat", "forever", "interface", "endinterface", "package", "endpackage", "typedef",
    "struct", "enum", "import", "var", "tri", "supply0", "supply1", "wand", "wor",
}
UNSUPPORTED_KW = {
    "initial", "generate", "endgenerate", "genvar", "function", "endfunction", "task", "endtask", "for",
    "while", "repeat", "forever", "interface", "endinterface", "package", "endpackage", "typedef",
    "struct", "enum", "import", "tri", "supply0", "supply1", "wand", "wor",
}

_NUM = r"(?:\d[\d_]*)?'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ_?]+|'[01xXzZ]|\d[\d_]*"
_OPS = ["<<<", ">>>", "===", "!==", "~&", "~|", "~^", "^~", "**", "<<", ">>", "<=", ">=", "==", "!=",
        "&&", "||", "+:", "-:", "->"]
_TOKEN_RE = re.compile(
    r"\s+|//[^\n]*|/\*.*?\*/|\(\*.*?\*\)|`[^\n]*"          # whitespace, comments, attributes, directives
    r"|(?P<num>" + _NUM + r")"
    r"|(?P<id>\$?[A-Za-z_][A-Za-z0-9_$]*)"
    r"|(?P<op>" + "|".join(re.escape(o) for o in _OPS) + r"|[-+*/%&|^~!<>=?:;,.#@()\[\]{}])",
    re.DOTALL,
)


def tokenize(src: str) -> List[Token]:
    toks: List[Token] = []
    pos = 0
    n = len(src)
    while pos < n:
        m = _TOKEN_RE.match(src, pos)
        if not m:
            raise UnsupportedSyntax(f"unexpected character {src[pos]!r} at offset {pos}")
        text = m.group(0)
        if text.startswith("`") and not text.startswith("`timescale") and not text.startswith("`default_nettype"):
            raise UnsupportedSyntax(f"preprocessor directive not supported: {text.split()[0]}")
        if m.lastgroup == "num":
            toks.append(Token("num", text, pos))
        elif m.lastgroup == "id":
            toks.append(Token("kw" if text in KEYWORDS else "id", text, pos))
        elif m.lastgroup == "op":
            toks.append(Token("op", text, pos))
        pos = m.end()
    toks.append(Token("eof", "", n))
    return toks


def parse_number(text: str):
    """Return (width|None, value|None)."""
    if "'" not in text:
        return None, int(text.replace("_", ""))
    size, rest = text.split("'", 1)
    width = int(size.replace("_", "")) if size else None
    if rest and rest[0] in "01xXzZ" and len(rest) == 1:      # SV '0 / '1 / 'x
        return width, (int(rest) if rest in "01" else None)
    rest = rest.lstrip("sS")
    base, digits = rest[0].lower(), rest[1:].replace("_", "")
    if re.search(r"[xXzZ?]", digits):
        return width, None
    return width, int(digits, {"b": 2, "o": 8, "d": 10, "h": 16}[base])
