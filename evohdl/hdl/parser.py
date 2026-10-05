"""Recursive-descent parser for the Verilog subset described in ast_nodes.py."""
from __future__ import annotations

import copy
import functools
from typing import List, Optional, Tuple

from evohdl.hdl.ast_nodes import (
    Always, Assign, Binary, Block, Call, Case, CaseItem, Concat, ContAssign, EXPR_TYPES, Ident, If, Instance,
    Module, NetDecl, Nop, Num, ParamDecl, PortDecl, Repl, Select, SourceFile, Ternary, Unary,
)
from evohdl.hdl.lexer import Token, UnsupportedSyntax, UNSUPPORTED_KW, parse_number, tokenize

ParseError = UnsupportedSyntax   # one exception type for "can't handle this source"

# Binary operator precedence (higher binds tighter). Ternary handled separately.
_PREC = {
    "||": 1, "&&": 2, "|": 3, "^": 4, "~^": 4, "^~": 4, "&": 5,
    "==": 6, "!=": 6, "===": 6, "!==": 6,
    "<": 7, "<=": 7, ">": 7, ">=": 7,
    "<<": 8, ">>": 8, "<<<": 8, ">>>": 8,
    "+": 9, "-": 9, "*": 10, "/": 10, "%": 10, "**": 11,
}
_UNARY_OPS = {"~", "!", "-", "+", "&", "|", "^", "~&", "~|", "~^", "^~"}


class _Parser:
    def __init__(self, src: str):
        self.toks = tokenize(src)
        self.i = 0

    # -- token helpers
    @property
    def tok(self) -> Token:
        return self.toks[self.i]

    def peek(self, k: int = 1) -> Token:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def at(self, text: str) -> bool:
        return self.tok.text == text and self.tok.kind in ("op", "kw")

    def accept(self, text: str) -> bool:
        if self.at(text):
            self.i += 1
            return True
        return False

    def expect(self, text: str) -> Token:
        if not self.at(text):
            raise ParseError(f"expected {text!r} but found {self.tok.text!r} at offset {self.tok.pos}")
        t = self.tok
        self.i += 1
        return t

    def ident(self) -> str:
        if self.tok.kind != "id":
            raise ParseError(f"expected identifier but found {self.tok.text!r} at offset {self.tok.pos}")
        t = self.tok.text
        self.i += 1
        return t

    def check_supported(self):
        if self.tok.kind == "kw" and self.tok.text in UNSUPPORTED_KW:
            raise ParseError(f"unsupported construct '{self.tok.text}' at offset {self.tok.pos}")

    # -- expressions
    def expr(self):
        cond = self.binary(1)
        if self.accept("?"):
            then = self.expr()
            self.expect(":")
            other = self.expr()
            return Ternary(cond, then, other)
        return cond

    def binary(self, min_prec: int):
        left = self.unary()
        while self.tok.kind == "op" and self.tok.text in _PREC and _PREC[self.tok.text] >= min_prec:
            op = self.tok.text
            prec = _PREC[op]
            self.i += 1
            right = self.binary(prec + 1) if op != "**" else self.binary(prec)
            left = Binary(op, left, right)
        return left

    def unary(self):
        if self.tok.kind == "op" and self.tok.text in _UNARY_OPS:
            op = self.tok.text
            self.i += 1
            if op == "^~":
                op = "~^"
            return Unary(op, self.unary())
        return self.postfix(self.primary())

    def primary(self):
        t = self.tok
        if t.kind == "num":
            self.i += 1
            w, v = parse_number(t.text)
            return Num(t.text, w, v)
        if t.kind == "id":
            if t.text.startswith("$"):
                self.i += 1
                args = []
                if self.accept("("):
                    if not self.at(")"):
                        args.append(self.expr())
                        while self.accept(","):
                            args.append(self.expr())
                    self.expect(")")
                return Call(t.text, args)
            self.i += 1
            return Ident(t.text)
        if self.accept("("):
            e = self.expr()
            self.expect(")")
            return e
        if self.accept("{"):
            first = self.expr()
            if self.at("{"):                      # replication {N{...}}
                self.expect("{")
                parts = [self.expr()]
                while self.accept(","):
                    parts.append(self.expr())
                self.expect("}")
                self.expect("}")
                return Repl(first, parts)
            parts = [first]
            while self.accept(","):
                parts.append(self.expr())
            self.expect("}")
            return Concat(parts)
        raise ParseError(f"unexpected token {t.text!r} in expression at offset {t.pos}")

    def postfix(self, base):
        while self.at("["):
            self.i += 1
            hi = self.expr()
            if self.accept(":"):
                lo = self.expr()
                base = Select(base, hi, lo, "part")
            elif self.at("+:") or self.at("-:"):
                mode = self.tok.text
                self.i += 1
                lo = self.expr()
                base = Select(base, hi, lo, mode)
            else:
                base = Select(base, hi, None, "bit")
            self.expect("]")
        return base

    def lvalue(self):
        if self.at("{"):
            self.i += 1
            parts = [self.lvalue()]
            while self.accept(","):
                parts.append(self.lvalue())
            self.expect("}")
            return Concat(parts)
        return self.postfix(Ident(self.ident()))

    # -- statements
    def stmt(self):
        self.check_supported()
        if self.accept(";"):
            return Nop()
        if self.accept("begin"):
            if self.accept(":"):
                self.ident()
            stmts = []
            while not self.at("end"):
                stmts.append(self.stmt())
            self.expect("end")
            return Block(stmts)
        if self.accept("if"):
            self.expect("(")
            cond = self.expr()
            self.expect(")")
            then = self.stmt()
            other = self.stmt() if self.accept("else") else None
            return If(cond, then, other)
        if self.tok.text in ("case", "casez", "casex") and self.tok.kind == "kw":
            kind = self.tok.text
            self.i += 1
            self.expect("(")
            e = self.expr()
            self.expect(")")
            items = []
            while not self.at("endcase"):
                if self.accept("default"):
                    self.accept(":")
                    items.append(CaseItem(None, self.stmt()))
                else:
                    labels = [self.expr()]
                    while self.accept(","):
                        labels.append(self.expr())
                    self.expect(":")
                    items.append(CaseItem(labels, self.stmt()))
            self.expect("endcase")
            return Case(kind, e, items)
        if self.at("#") or self.at("@"):
            raise ParseError("delays/event controls inside statements are not supported")
        lhs = self.lvalue()
        if self.accept("<="):
            blocking = False
        else:
            self.expect("=")
            blocking = True
        rhs = self.expr()
        self.expect(";")
        return Assign(lhs, rhs, blocking)

    # -- declarations
    def opt_signed(self) -> bool:
        if self.accept("signed"):
            return True
        self.accept("unsigned")
        return False

    def opt_range(self) -> Optional[Tuple]:
        if self.accept("["):
            msb = self.expr()
            self.expect(":")
            lsb = self.expr()
            self.expect("]")
            return (msb, lsb)
        return None

    def port_decl(self, direction: str) -> PortDecl:
        kind = None
        if self.tok.text in ("wire", "reg", "logic") and self.tok.kind == "kw":
            kind = self.tok.text
            self.i += 1
        signed = self.opt_signed()
        width = self.opt_range()
        names = [self.ident()]
        return PortDecl(direction, kind, signed, width, names)

    def param_decl(self, local: bool) -> ParamDecl:
        if self.tok.text == "integer":
            self.i += 1
        self.opt_signed()
        width = self.opt_range()
        items = []
        while True:
            name = self.ident()
            self.expect("=")
            items.append((name, self.expr()))
            if self.at(",") and self.peek().kind == "id" and self.peek(2).text == "=":
                self.i += 1
                continue
            break
        return ParamDecl(local, width, items)

    def net_decl(self) -> NetDecl:
        kind = self.tok.text
        self.i += 1
        signed = self.opt_signed()
        width = self.opt_range()
        items = []
        while True:
            name = self.ident()
            init = None
            if self.accept("="):
                init = self.expr()
            items.append((name, init))
            if not self.accept(","):
                break
        self.expect(";")
        return NetDecl(kind, signed, width, items)

    def sens_list(self):
        self.expect("@")
        if self.accept("*"):
            return None
        self.expect("(")
        if self.accept("*"):
            self.expect(")")
            return None
        sens = []
        while True:
            edge = None
            if self.at("posedge") or self.at("negedge"):
                edge = self.tok.text
                self.i += 1
            sens.append((edge, self.postfix(Ident(self.ident()))))
            if self.accept("or") or self.accept(","):
                continue
            break
        self.expect(")")
        return sens

    def always(self) -> Always:
        kind = self.tok.text
        self.i += 1
        sens = None
        if kind == "always" or (kind == "always_ff") or (kind == "always_latch" and self.at("@")):
            if self.at("@"):
                sens = self.sens_list()
            elif kind == "always":
                raise ParseError("always without event control is not supported")
        elif kind == "always_comb" and self.at("@"):
            sens = self.sens_list()
        return Always(kind, sens, self.stmt())

    def instance(self) -> Instance:
        module = self.ident()
        params = []
        if self.accept("#"):
            self.expect("(")
            if not self.at(")"):
                while True:
                    if self.accept("."):
                        pname = self.ident()
                        self.expect("(")
                        params.append((pname, self.expr()))
                        self.expect(")")
                    else:
                        params.append((None, self.expr()))
                    if not self.accept(","):
                        break
            self.expect(")")
        name = self.ident()
        self.expect("(")
        conns = []
        if not self.at(")"):
            while True:
                if self.accept("."):
                    pname = self.ident()
                    self.expect("(")
                    e = None if self.at(")") else self.expr()
                    self.expect(")")
                    conns.append((pname, e))
                else:
                    conns.append((None, self.expr()))
                if not self.accept(","):
                    break
        self.expect(")")
        self.expect(";")
        return Instance(module, params, name, conns)

    def module(self) -> Module:
        self.expect("module")
        name = self.ident()
        mod = Module(name)
        if self.accept("#"):
            self.expect("(")
            while True:
                self.expect("parameter")
                mod.header_params.append(self.param_decl(False))
                if not self.accept(","):
                    break
            self.expect(")")
        if self.accept("("):
            if not self.at(")"):
                if self.tok.text in ("input", "output", "inout"):
                    cur_dir, cur = None, None
                    while True:
                        if self.tok.text in ("input", "output", "inout"):
                            cur_dir = self.tok.text
                            self.i += 1
                            cur = self.port_decl(cur_dir)
                            mod.ports.append(cur)
                        else:   # continuation: another name sharing the previous declaration's type
                            nm = self.ident()
                            cur.names.append(nm)
                        if not self.accept(","):
                            break
                else:
                    mod.ports.append(self.ident())
                    while self.accept(","):
                        mod.ports.append(self.ident())
            self.expect(")")
        self.expect(";")
        while not self.at("endmodule"):
            self.check_supported()
            t = self.tok
            if t.kind == "eof":
                raise ParseError("unexpected end of file inside module")
            if t.text in ("input", "output", "inout") and t.kind == "kw":
                d = t.text
                self.i += 1
                pd = self.port_decl(d)
                while self.accept(","):
                    pd.names.append(self.ident())
                self.expect(";")
                mod.items.append(pd)
            elif t.text in ("wire", "reg", "logic", "integer") and t.kind == "kw":
                mod.items.append(self.net_decl())
            elif t.text in ("parameter", "localparam") and t.kind == "kw":
                self.i += 1
                mod.items.append(self.param_decl(t.text == "localparam"))
                self.expect(";")
            elif self.accept("assign"):
                lhs = self.lvalue()
                self.expect("=")
                rhs = self.expr()
                self.expect(";")
                mod.items.append(ContAssign(lhs, rhs))
            elif t.text in ("always", "always_comb", "always_ff", "always_latch") and t.kind == "kw":
                mod.items.append(self.always())
            elif t.kind == "id" and (self.peek().kind == "id" or self.peek().text == "#"):
                mod.items.append(self.instance())
            else:
                raise ParseError(f"unsupported module item starting with {t.text!r} at offset {t.pos}")
        self.expect("endmodule")
        return mod

    def source(self) -> SourceFile:
        sf = SourceFile()
        while self.tok.kind != "eof":
            if self.tok.text == "module" and self.tok.kind == "kw":
                sf.modules.append(self.module())
            else:
                raise ParseError(f"expected 'module' at top level, found {self.tok.text!r} at offset {self.tok.pos}")
        return sf


@functools.lru_cache(maxsize=512)
def _parse_cached(src: str) -> SourceFile:
    return _Parser(src).source()


def parse_source(src: str) -> SourceFile:
    """Parse Verilog text -> SourceFile (a private deep copy, safe to mutate).
    Raises ParseError (== UnsupportedSyntax) for anything outside the supported subset."""
    return copy.deepcopy(_parse_cached(src))


def parse_expr(text: str):
    p = _Parser(text)
    e = p.expr()
    if p.tok.kind != "eof":
        raise ParseError(f"trailing tokens after expression: {p.tok.text!r}")
    return e
