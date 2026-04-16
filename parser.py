"""
aergia.parser
~~~~~~~~~~~~~
Recursive-descent Pratt parser for Æergia∞.

Unique syntax handled:
  ~>   demand operator   (primes ~> 10)
  ∞T   infinity type     (∞Int, ∞Spectrum)
  ~e   lazy thunk        (~heavyComputation)
  :>   stream cons       (x :> xs)
  !!   stream index      (fibs !! 50)
  |>   pipe              (xs |> map f |> filter p)
  ..   range             ([1..], [1..10], [2,4..])
  @lazy @now @source     annotations
"""
from __future__ import annotations
from typing import Any, List, Optional

from .lexer import Token, TK, tokenize, LexError
from .ast_nodes import *


class ParseError(Exception):
    def __init__(self, msg: str, tok: Token):
        super().__init__(f"Parse error at {tok.line}:{tok.col} — {msg} (got {tok.kind.name} {tok.lexeme!r})")
        self.tok = tok


# ── Operator precedence ───────────────────────────────────────────────────────
# Higher number = tighter binding

PREC: dict[str, int] = {
    "$":   1,
    "||":  2,
    "&&":  3,
    "==":  4, "/=": 4, "<": 4, ">": 4, "<=": 4, ">=": 4,
    "~>":  5,   # demand — right of comparisons
    "++":  6, ":": 6,
    ":>":  7,   # stream cons — right-associative
    "+":   8, "-": 8,
    "*":   9, "/": 9, "%": 9,
    "^":   10,
    "!!":  11,  # index — very tight
    ".":   12,  # composition / field access
    "|>":  1,   # pipe — loose left-associative
}

RIGHT_ASSOC = {"^", ":>", "$", "."}


class Parser:
    def __init__(self, tokens: List[Token]) -> None:
        self.toks = tokens
        self.pos  = 0

    # ── Token access ────────────────────────────────────────────

    def _cur(self) -> Token:
        return self.toks[min(self.pos, len(self.toks)-1)]

    def _peek(self, n: int = 1) -> Token:
        return self.toks[min(self.pos+n, len(self.toks)-1)]

    def _adv(self) -> Token:
        t = self._cur(); self.pos += 1; return t

    def _eat(self, kind: TK, msg: str = "") -> Token:
        t = self._cur()
        if t.kind != kind:
            raise ParseError(msg or f"expected {kind.name}", t)
        return self._adv()

    def _at(self, *kinds: TK) -> bool:
        return self._cur().kind in kinds

    def _match(self, *kinds: TK) -> Optional[Token]:
        if self._at(*kinds): return self._adv()
        return None

    # ── Top level ────────────────────────────────────────────────

    def parse_programme(self) -> Programme:
        decls = []
        while not self._at(TK.EOF):
            d = self._parse_decl()
            if d: decls.append(d)
        return Programme(decls)

    def _parse_decl(self):  # noqa: C901
        t = self._cur()

        if t.kind == TK.MODULE:
            return self._parse_module()
        if t.kind == TK.IMPORT:
            return self._parse_import()
        if t.kind == TK.TYPE:
            return self._parse_type_decl()
        if t.kind == TK.CODATA:
            return self._parse_codata()
        if t.kind == TK.SOURCE:
            return self._parse_source_decl()
        if t.kind == TK.ARCHIVE:
            return self._parse_archive_decl()

        # Type signature or binding
        if t.kind == TK.IDENT:
            if self._peek().kind == TK.DCOLON:
                return self._parse_type_sig()
            return self._parse_binding()

        # Skip semicolons / layout tokens
        if t.kind == TK.SEMI:
            self._adv(); return None

        raise ParseError("unexpected token in top-level", t)

    # ── Module / import ──────────────────────────────────────────

    def _parse_module(self) -> ModuleDecl:
        self._eat(TK.MODULE)
        name = self._parse_module_name()
        exposing = None
        if self._match(TK.EXPOSE):
            self._eat(TK.LPAREN)
            exposing = self._parse_comma_list(self._parse_name_or_op)
            self._eat(TK.RPAREN)
        return ModuleDecl(name, exposing)

    def _parse_import(self) -> ImportDecl:
        self._eat(TK.IMPORT)
        qualified = bool(self._match(TK.IDENT) and self.toks[self.pos-1].value == "qualified")
        name  = self._parse_module_name()
        alias = None
        items = None
        if self._match(TK.AS):
            alias = self._eat(TK.UPPER).value
        if self._match(TK.LPAREN):
            items = self._parse_comma_list(self._parse_name_or_op)
            self._eat(TK.RPAREN)
        return ImportDecl(name, items, qualified, alias)

    def _parse_module_name(self) -> str:
        parts = [self._eat(TK.UPPER).value]
        while self._at(TK.DOT) and self._peek().kind == TK.UPPER:
            self._adv(); parts.append(self._eat(TK.UPPER).value)
        return ".".join(parts)

    def _parse_name_or_op(self) -> str:
        t = self._cur()
        if t.kind in (TK.IDENT, TK.UPPER): return self._adv().value
        if t.kind == TK.LPAREN:
            self._adv()
            op = self._adv().lexeme
            self._eat(TK.RPAREN)
            return op
        raise ParseError("expected name or operator", t)

    # ── Type declarations ────────────────────────────────────────

    def _parse_type_decl(self):
        self._eat(TK.TYPE)
        name   = self._eat(TK.UPPER).value
        params = []
        while self._at(TK.IDENT):
            params.append(self._adv().value)
        self._eat(TK.EQ)
        # Simple type alias
        rhs = self._parse_type()
        return TypeDecl(name, params, rhs)

    def _parse_codata(self):
        self._eat(TK.CODATA)
        name   = self._eat(TK.UPPER).value
        params = []
        while self._at(TK.IDENT):
            params.append(self._adv().value)
        self._eat(TK.WHERE)
        obs = []
        while self._at(TK.IDENT):
            n = self._adv().value
            self._eat(TK.DCOLON)
            t = self._parse_type()
            obs.append((n, t))
        return CodataDecl(name, params, obs)

    def _parse_source_decl(self) -> SourceDecl:
        self._eat(TK.SOURCE)
        name = self._eat(TK.IDENT).value
        self._eat(TK.EQ)
        src_type = self._eat(TK.UPPER).value
        # optional keyword args
        kwargs = {}
        while self._at(TK.DOT) or (self._at(TK.IDENT) and self._peek().kind == TK.EQ):
            k = self._eat(TK.IDENT).value
            self._eat(TK.EQ)
            kwargs[k] = self.parse_expr()
        return SourceDecl(name, src_type, kwargs)

    def _parse_archive_decl(self) -> ArchiveDecl:
        self._eat(TK.ARCHIVE)
        name = self._eat(TK.IDENT).value
        self._eat(TK.DCOLON)
        self._eat(TK.UPPER)  # 'Archive'
        model_name = self._eat(TK.UPPER).value
        self._eat(TK.WHERE)
        kwargs = {}
        while self._at(TK.IDENT):
            k = self._eat(TK.IDENT).value
            self._eat(TK.EQ)
            kwargs[k] = self.parse_expr()
        return ArchiveDecl(name, None, model_name, kwargs)

    # ── Type signatures & bindings ────────────────────────────────

    def _parse_type_sig(self) -> TypeSig:
        name = self._eat(TK.IDENT).value
        self._eat(TK.DCOLON)
        t = self._parse_type()
        return TypeSig(name, t)

    def _parse_binding(self) -> Binding:
        line, col = self._cur().line, self._cur().col
        name   = self._eat(TK.IDENT).value
        params = []
        while not self._at(TK.EQ, TK.BAR, TK.WHERE, TK.SEMI, TK.EOF):
            params.append(self._parse_pattern_atom())
        self._eat(TK.EQ)
        body = self.parse_expr()
        where_binds = []
        if self._match(TK.WHERE):
            while self._at(TK.IDENT):
                where_binds.append(self._parse_binding())
        return Binding(name, params, body, where_binds, line=line, col=col)

    # ── Types ────────────────────────────────────────────────────

    def _parse_type(self) -> Any:
        # forall
        if self._at(TK.FORALL):
            self._adv()
            vs = []
            while self._at(TK.IDENT): vs.append(self._adv().value)
            self._eat(TK.DOT)
            return TForall(vs, self._parse_type())
        t = self._parse_type_app()
        if self._match(TK.ARROW):
            return TArrow(t, self._parse_type())
        if self._match(TK.LINARR):
            return TLinear(t, self._parse_type())
        return t

    def _parse_type_app(self) -> Any:
        t = self._parse_type_atom()
        args = []
        while self._at(TK.UPPER, TK.IDENT, TK.LPAREN, TK.LBRACK, TK.INF_TYPE):
            try:
                args.append(self._parse_type_atom())
            except ParseError:
                break
        for a in args:
            t = TApp(t, a)
        return t

    def _parse_type_atom(self) -> Any:
        t = self._cur()
        if t.kind == TK.INF_TYPE:
            self._adv(); return TInf(self._parse_type_atom())
        if t.kind == TK.UPPER: self._adv(); return TName(t.value)
        if t.kind == TK.IDENT: self._adv(); return TVar(t.value)
        if t.kind == TK.LPAREN:
            self._adv()
            if self._match(TK.RPAREN): return TName("Unit")
            ts = [self._parse_type()]
            while self._match(TK.COMMA): ts.append(self._parse_type())
            self._eat(TK.RPAREN)
            return ts[0] if len(ts) == 1 else TTuple(ts)
        if t.kind == TK.LBRACK:
            self._adv()
            elem = self._parse_type()
            self._eat(TK.RBRACK)
            return TList(elem)
        raise ParseError("expected type", t)

    # ── Expressions (Pratt) ────────────────────────────────────────

    def parse_expr(self, min_prec: int = 0) -> Any:
        lhs = self._parse_unary()
        while True:
            op = self._current_binop()
            if op is None: break
            prec = PREC.get(op, 0)
            if prec <= min_prec: break
            self._adv()  # consume operator token
            if op == "|>":
                rhs = self._parse_unary()
                lhs = Pipe(lhs, rhs)
            elif op == "~>":
                rhs = self.parse_expr(prec)
                lhs = DemandExpr(lhs, rhs)
            elif op == "!!":
                rhs = self.parse_expr(prec)
                lhs = IndexExpr(lhs, rhs)
            elif op == ":>":
                rhs = self.parse_expr(prec - 1)  # right-assoc
                lhs = StreamConsExpr(lhs, rhs)
            elif op == "$":
                rhs = self.parse_expr(prec - 1)
                lhs = Dollar(lhs, rhs)
            elif op == ".":
                # Could be field access or composition
                if self._at(TK.IDENT):
                    field = self._adv().value
                    lhs   = FieldAccess(lhs, field)
                else:
                    rhs = self.parse_expr(prec - 1)
                    lhs = ComposeExpr(lhs, rhs)
            else:
                next_prec = prec if op in RIGHT_ASSOC else prec
                rhs = self.parse_expr(next_prec)
                lhs = BinOp(op, lhs, rhs)
        # Type annotation
        if self._match(TK.DCOLON):
            t = self._parse_type()
            lhs = TypeAnn(lhs, t)
        return lhs

    def _current_binop(self) -> Optional[str]:
        t = self._cur()
        m = {
            TK.DEMAND: "~>", TK.PIPE: "|>", TK.BANGBANG: "!!",
            TK.CONS: ":>", TK.DOLLAR: "$",
            TK.PLUS: "+", TK.MINUS: "-", TK.STAR: "*", TK.SLASH: "/",
            TK.PCT: "%", TK.CARET: "^",
            TK.EQEQ: "==", TK.NEQ: "/=", TK.LT: "<", TK.GT: ">",
            TK.LTE: "<=", TK.GTE: ">=",
            TK.AND: "&&", TK.OR: "||",
            TK.CONCAT: "++", TK.COLON: ":",
            TK.DOT: ".",
        }
        return m.get(t.kind)

    def _parse_unary(self) -> Any:
        t = self._cur()
        if t.kind == TK.TILDE:
            self._adv(); return Suspend(self._parse_unary())
        if t.kind == TK.BANG:
            self._adv(); return Force(self._parse_unary())
        if t.kind == TK.MINUS:
            self._adv(); return UnOp("-", self._parse_unary())
        return self._parse_app()

    def _parse_app(self) -> Any:
        func = self._parse_atom()
        args = []
        while self._is_atom_start():
            args.append(self._parse_atom())
        for a in args:
            func = App(func, a)
        return func

    def _is_atom_start(self) -> bool:
        k = self._cur().kind
        return k in (
            TK.INT, TK.FLOAT, TK.STRING, TK.CHAR, TK.BOOL,
            TK.IDENT, TK.UPPER, TK.LPAREN, TK.LBRACK, TK.LBRACE,
            TK.INF_TYPE, TK.TILDE, TK.BANG, TK.UNDER,
        )

    def _parse_atom(self) -> Any:  # noqa: C901
        t = self._cur()

        if t.kind == TK.INT:   self._adv(); return IntLit(t.value)
        if t.kind == TK.FLOAT: self._adv(); return FloatLit(t.value)
        if t.kind == TK.STRING:self._adv(); return StrLit(t.value)
        if t.kind == TK.CHAR:  self._adv(); return CharLit(t.value)
        if t.kind == TK.BOOL:  self._adv(); return BoolLit(t.value)
        if t.kind == TK.UNDER: self._adv(); return Var("_")

        if t.kind == TK.IDENT:
            self._adv()
            return Var(t.value)

        if t.kind == TK.UPPER:
            self._adv()
            return ConstructorExpr(t.value)

        if t.kind == TK.TILDE:
            self._adv(); return Suspend(self._parse_atom())

        if t.kind == TK.BANG:
            self._adv(); return Force(self._parse_atom())

        if t.kind == TK.BSLASH:  # lambda
            return self._parse_lambda()

        if t.kind == TK.LET:
            return self._parse_let()

        if t.kind == TK.IF:
            return self._parse_if()

        if t.kind == TK.MATCH:
            return self._parse_match()

        if t.kind == TK.DO:
            return self._parse_do()

        if t.kind == TK.LBRACK:
            return self._parse_list_or_range()

        if t.kind == TK.LPAREN:
            return self._parse_paren()

        if t.kind == TK.LBRACE:
            return self._parse_record()

        if t.kind == TK.BTICK:   # infix via backtick
            self._adv()
            op = Var(self._eat(TK.IDENT).value)
            self._eat(TK.BTICK)
            return op

        if t.kind == TK.INF_TYPE:
            self._adv()
            return Var("∞")   # bare ∞ symbol as identifier

        raise ParseError("unexpected token in expression", t)

    # ── Specific expression forms ─────────────────────────────────

    def _parse_lambda(self) -> Lam:
        self._eat(TK.BSLASH)
        params = []
        while not self._at(TK.ARROW):
            params.append(self._parse_pattern_atom())
        self._eat(TK.ARROW)
        body = self.parse_expr()
        return Lam(params, body)

    def _parse_let(self) -> Let:
        self._eat(TK.LET)
        binds = []
        while self._at(TK.IDENT):
            b = self._parse_binding()
            binds.append(b)
        self._eat(TK.IN)
        body = self.parse_expr()
        return Let(binds, body)

    def _parse_if(self) -> IfExpr:
        self._eat(TK.IF)
        c = self.parse_expr()
        self._eat(TK.THEN)
        th = self.parse_expr()
        self._eat(TK.ELSE)
        el = self.parse_expr()
        return IfExpr(c, th, el)

    def _parse_match(self) -> MatchExpr:
        self._eat(TK.MATCH)
        scrutinee = self.parse_expr()
        self._eat(TK.WITH)
        arms = []
        while self._at(TK.BAR):
            self._adv()
            pat = self._parse_pattern()
            guard = None
            if self._at(TK.IDENT) and self._cur().value == "if":
                self._adv(); guard = self.parse_expr()
            self._eat(TK.ARROW)
            body = self.parse_expr()
            arms.append((pat, guard, body))
        return MatchExpr(scrutinee, arms)

    def _parse_do(self) -> DoExpr:
        self._eat(TK.DO)
        stmts = []
        while not self._at(TK.EOF, TK.SEMI, TK.IN, TK.WHERE):
            stmts.append(self._parse_do_stmt())
        return DoExpr(stmts)

    def _parse_do_stmt(self):
        if self._at(TK.LET):
            self._adv()
            binds = []
            while self._at(TK.IDENT):
                binds.append(self._parse_binding())
            return DoLet(binds)
        if (self._at(TK.IDENT) and self._peek().kind == TK.LARROW):
            name = self._adv().value
            self._adv()  # <-
            expr = self.parse_expr()
            return DoBind(name, expr)
        expr = self.parse_expr()
        return DoExprStmt(expr)

    def _parse_list_or_range(self) -> Any:
        self._eat(TK.LBRACK)
        if self._match(TK.RBRACK):
            return ListLit([])

        first = self.parse_expr()

        # [1..] or [1..10] or [1,3..] or [1,3..10]
        if self._match(TK.DOTDOT):
            if self._match(TK.RBRACK):
                return RangeLit(first)
            stop = self.parse_expr()
            self._eat(TK.RBRACK)
            return RangeLit(first, stop)

        if self._at(TK.COMMA):
            self._adv()
            second = self.parse_expr()
            if self._match(TK.DOTDOT):
                if self._match(TK.RBRACK):
                    return RangeLit(first, None, second)
                stop = self.parse_expr()
                self._eat(TK.RBRACK)
                return RangeLit(first, stop, second)
            # Normal list [a, b, c, ...]
            elems = [first, second]
            while self._match(TK.COMMA):
                elems.append(self.parse_expr())
            self._eat(TK.RBRACK)
            return ListLit(elems)

        self._eat(TK.RBRACK)
        return ListLit([first])

    def _parse_paren(self) -> Any:
        self._eat(TK.LPAREN)
        if self._match(TK.RPAREN):
            return UnitLit()
        # Operator section or tuple or grouped expr
        first = self.parse_expr()
        if self._match(TK.COMMA):
            elems = [first]
            while True:
                elems.append(self.parse_expr())
                if not self._match(TK.COMMA): break
            self._eat(TK.RPAREN)
            return TupleLit(elems)
        # Backtick infix in parens (ignore for now)
        self._eat(TK.RPAREN)
        return first

    def _parse_record(self) -> Any:
        self._eat(TK.LBRACE)
        fields = []
        while not self._at(TK.RBRACE, TK.EOF):
            k = self._eat(TK.IDENT).value
            self._eat(TK.EQ)
            v = self.parse_expr()
            fields.append((k, v))
            self._match(TK.COMMA)
        self._eat(TK.RBRACE)
        return RecordLit(fields)

    # ── Patterns ─────────────────────────────────────────────────

    def _parse_pattern(self) -> Any:
        pat = self._parse_pattern_con()
        if self._match(TK.COLON):
            tail = self._parse_pattern()
            return PListCons(pat, tail)
        if self._match(TK.CONS):
            tail = self._parse_pattern()
            return PCons(pat, tail)
        return pat

    def _parse_pattern_con(self) -> Any:
        if self._at(TK.UPPER):
            name = self._adv().value
            args = []
            while self._is_pat_atom_start():
                args.append(self._parse_pattern_atom())
            return PConstructor(name, args)
        return self._parse_pattern_atom()

    def _is_pat_atom_start(self) -> bool:
        return self._cur().kind in (
            TK.INT, TK.FLOAT, TK.STRING, TK.BOOL,
            TK.IDENT, TK.UNDER, TK.LPAREN, TK.LBRACK,
        )

    def _parse_pattern_atom(self) -> Any:
        t = self._cur()
        if t.kind == TK.UNDER:  self._adv(); return PWild()
        if t.kind == TK.IDENT:
            name = self._adv().value
            if self._at(TK.AT):
                self._adv(); return PAs(name, self._parse_pattern_atom())
            return PVar(name)
        if t.kind == TK.INT:    self._adv(); return PLit(t.value)
        if t.kind == TK.FLOAT:  self._adv(); return PLit(t.value)
        if t.kind == TK.STRING: self._adv(); return PLit(t.value)
        if t.kind == TK.BOOL:   self._adv(); return PLit(t.value)
        if t.kind == TK.MINUS:
            self._adv()
            n = self._eat(TK.INT)
            return PLit(-n.value)
        if t.kind == TK.UPPER:
            name = self._adv().value
            return PConstructor(name, [])
        if t.kind == TK.LPAREN:
            self._adv()
            if self._match(TK.RPAREN): return PLit(None)  # unit
            p = self._parse_pattern()
            if self._at(TK.COMMA):
                pats = [p]
                while self._match(TK.COMMA): pats.append(self._parse_pattern())
                self._eat(TK.RPAREN)
                return PTuple(pats)
            self._eat(TK.RPAREN)
            return p
        if t.kind == TK.LBRACK:
            self._adv()
            if self._match(TK.RBRACK): return PList([])
            pats = [self._parse_pattern()]
            while self._match(TK.COMMA): pats.append(self._parse_pattern())
            self._eat(TK.RBRACK)
            return PList(pats)
        raise ParseError("expected pattern", t)

    def _parse_comma_list(self, parse_fn) -> list:
        items = []
        if not self._at(TK.RPAREN):
            items.append(parse_fn())
            while self._match(TK.COMMA):
                items.append(parse_fn())
        return items


# ── Module-level entry points ─────────────────────────────────────────────────

def parse(source: str, filename: str = "<stdin>") -> Programme:
    """Lex and parse a full Æergia∞ programme."""
    tokens = tokenize(source, filename)
    return Parser(tokens).parse_programme()


def parse_expr(source: str) -> Any:
    """Parse a single Æergia∞ expression."""
    tokens = tokenize(source)
    return Parser(tokens).parse_expr()
