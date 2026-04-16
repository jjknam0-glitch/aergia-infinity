"""
aergia.lexer
~~~~~~~~~~~~
Tokeniser for the Æergia∞ language.

Unique Æergia∞ tokens:
  ~>   demand operator    (stream ~> 10  pulls 10 elements)
  ∞    infinity type      (∞Int, ∞Spectrum — infinite stream types)
  ~    lazy prefix        (~expr creates a thunk)
  :>   stream cons
  |>   pipe
  -o   linear function type
  !!   stream index
  ..   range dots         ([1..10], [2,4..])
  @    annotation prefix  (@lazy, @now, @source, @compress)
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional


class TK(Enum):
    # Literals
    INT    = auto(); FLOAT  = auto(); STRING = auto()
    CHAR   = auto(); BOOL   = auto()

    # Identifiers
    IDENT  = auto()   # lowercase-start
    UPPER  = auto()   # uppercase-start (types / constructors)

    # Keywords
    LET    = auto(); IN     = auto(); WHERE  = auto()
    MATCH  = auto(); WITH   = auto(); IF     = auto()
    THEN   = auto(); ELSE   = auto(); DO     = auto()
    TYPE   = auto(); CODATA = auto(); CLASS  = auto()
    INST   = auto(); IMPORT = auto(); MODULE = auto()
    EXPOSE = auto(); FORALL = auto(); OF     = auto()
    AS     = auto(); SOURCE = auto(); ARCHIVE= auto()
    COMPRESS = auto(); DEMAND_KW = auto()

    # Annotations
    ANN_LAZY    = auto()   # @lazy
    ANN_NOW     = auto()   # @now
    ANN_SOURCE  = auto()   # @source
    ANN_COMPRESS= auto()   # @compress

    # Æergia∞ unique operators
    DEMAND   = auto()   # ~>
    INF_TYPE = auto()   # ∞
    TILDE    = auto()   # ~   (lazy prefix / thunk)
    CONS     = auto()   # :>
    DOTDOT   = auto()   # ..  (range)

    # Standard operators & punctuation
    DCOLON = auto()   # ::
    ARROW  = auto()   # ->
    LARROW = auto()   # <-
    LINARR = auto()   # -o  (linear type)
    PIPE   = auto()   # |>
    BAR    = auto()   # |
    EQ     = auto()   # =
    BSLASH = auto()   # \
    BANG   = auto()   # !  (force)
    DOT    = auto()   # .  (field access / composition)
    DOLLAR = auto()   # $
    PCT    = auto()   # %
    PLUS   = auto();  MINUS  = auto()
    STAR   = auto();  SLASH  = auto()
    CARET  = auto()   # ^  (exponentiation)
    EQEQ   = auto()   # ==
    NEQ    = auto()   # /=
    LT     = auto();  GT     = auto()
    LTE    = auto();  GTE    = auto()
    AND    = auto()   # &&
    OR     = auto()   # ||
    CONCAT = auto()   # ++
    BANGBANG = auto() # !!
    UNDER  = auto()   # _

    LPAREN = auto(); RPAREN  = auto()
    LBRACK = auto(); RBRACK  = auto()
    LBRACE = auto(); RBRACE  = auto()
    COMMA  = auto(); SEMI    = auto()
    COLON  = auto(); BTICK   = auto()
    AT     = auto(); HASH    = auto()

    EOF = auto()


@dataclass
class Token:
    kind:   TK
    value:  object
    line:   int
    col:    int
    lexeme: str = ""

    def __repr__(self) -> str:
        v = f" {self.value!r}" if self.value is not None else ""
        return f"[{self.kind.name}{v} {self.line}:{self.col}]"


_KEYWORDS: dict[str, TK] = {
    "let": TK.LET, "in": TK.IN, "where": TK.WHERE,
    "match": TK.MATCH, "with": TK.WITH,
    "if": TK.IF, "then": TK.THEN, "else": TK.ELSE,
    "do": TK.DO, "type": TK.TYPE, "codata": TK.CODATA,
    "class": TK.CLASS, "instance": TK.INST,
    "import": TK.IMPORT, "module": TK.MODULE,
    "exposing": TK.EXPOSE, "forall": TK.FORALL,
    "of": TK.OF, "as": TK.AS,
    "source": TK.SOURCE, "archive": TK.ARCHIVE,
    "compress": TK.COMPRESS,
    "True": TK.BOOL, "False": TK.BOOL,
    "_": TK.UNDER,
    "otherwise": TK.IDENT,
}


class LexError(Exception):
    def __init__(self, msg: str, line: int, col: int) -> None:
        super().__init__(f"Æergia∞ lex error at {line}:{col} — {msg}")
        self.line = line; self.col = col


class Lexer:
    def __init__(self, source: str, filename: str = "<stdin>") -> None:
        self.src  = source
        self.file = filename
        self.pos  = 0
        self.line = 1
        self.col  = 1
        self.toks: List[Token] = []

    def tokenize(self) -> List[Token]:
        while self.pos < len(self.src):
            self._skip_ws_comments()
            if self.pos >= len(self.src):
                break
            self._next()
        self.toks.append(Token(TK.EOF, None, self.line, self.col, ""))
        return self.toks

    def _peek(self, n: int = 0) -> str:
        i = self.pos + n
        return self.src[i] if i < len(self.src) else "\0"

    def _adv(self) -> str:
        ch = self.src[self.pos]; self.pos += 1
        if ch == "\n": self.line += 1; self.col = 1
        else:          self.col  += 1
        return ch

    def _emit(self, kind: TK, value: object = None, lex: str = "") -> None:
        self.toks.append(Token(kind, value, self.line, self.col, lex))

    def _skip_ws_comments(self) -> None:
        while self.pos < len(self.src):
            ch = self._peek()
            if ch in " \t\r\n":
                self._adv()
            elif ch == "-" and self._peek(1) == "-":
                while self.pos < len(self.src) and self._peek() != "\n":
                    self._adv()
            elif ch == "{" and self._peek(1) == "-":
                self._adv(); self._adv()
                while self.pos < len(self.src):
                    if self._peek() == "-" and self._peek(1) == "}":
                        self._adv(); self._adv(); break
                    self._adv()
            else:
                break

    def _next(self) -> None:  # noqa: C901
        ch = self._peek()

        # ∞ type symbol
        if ch == "∞":
            self._adv(); self._emit(TK.INF_TYPE, None, "∞"); return

        # Numbers
        if ch.isdigit() or (ch == "-" and self._peek(1).isdigit() and
                self.toks and self.toks[-1].kind in (
                    TK.EQ, TK.LPAREN, TK.COMMA, TK.LBRACK,
                    TK.ARROW, TK.BAR, TK.PIPE, TK.IN, TK.THEN, TK.ELSE)):
            self._lex_number(); return

        if ch == '"': self._lex_string(); return
        if ch == "'": self._lex_char();   return

        # Identifiers / keywords
        if ch.isalpha() or ch == "_":
            self._lex_ident(); return

        # Annotation: @lazy @now @source @compress
        if ch == "@":
            self._adv()
            if self._peek().isalpha():
                start = self.pos
                while self._peek().isalnum() or self._peek() == "_":
                    self._adv()
                word = self.src[start:self.pos]
                ann_map = {
                    "lazy": TK.ANN_LAZY, "now": TK.ANN_NOW,
                    "source": TK.ANN_SOURCE, "compress": TK.ANN_COMPRESS,
                }
                kind = ann_map.get(word, TK.AT)
                self._emit(kind, word, "@" + word)
            else:
                self._emit(TK.AT, None, "@")
            return

        self._lex_symbol()

    def _lex_number(self) -> None:
        start = self.pos
        if self._peek() == "-": self._adv()
        while self._peek().isdigit() or self._peek() == "_":
            self._adv()
        is_float = False
        if self._peek() == "." and self._peek(1).isdigit():
            is_float = True; self._adv()
            while self._peek().isdigit(): self._adv()
        if self._peek() in "eE":
            is_float = True; self._adv()
            if self._peek() in "+-": self._adv()
            while self._peek().isdigit(): self._adv()
        lex = self.src[start:self.pos].replace("_", "")
        if is_float: self._emit(TK.FLOAT, float(lex), lex)
        else:        self._emit(TK.INT,   int(lex),   lex)

    def _lex_string(self) -> None:
        self._adv()   # "
        parts: list[str] = []
        while self.pos < len(self.src) and self._peek() != '"':
            if self._peek() == "\\":
                self._adv()
                parts.append({"n":"\n","t":"\t","r":"\r","\\":"\\",'"':'"',"0":"\0"}.get(
                    self._adv(), "?"))
            else:
                parts.append(self._adv())
        if self.pos >= len(self.src):
            raise LexError("unterminated string", self.line, self.col)
        self._adv()   # "
        val = "".join(parts)
        self._emit(TK.STRING, val, f'"{val}"')

    def _lex_char(self) -> None:
        self._adv()   # '
        ch = self._adv()
        if ch == "\\":
            ch = {"n":"\n","t":"\t","r":"\r","\\":"\\","'":"'"}.get(self._adv(), "?")
        if self._peek() != "'":
            raise LexError("unterminated char literal", self.line, self.col)
        self._adv()   # '
        self._emit(TK.CHAR, ch, f"'{ch}'")

    def _lex_ident(self) -> None:
        start = self.pos
        while self._peek().isalnum() or self._peek() in "_'":
            self._adv()
        name = self.src[start:self.pos]
        kind = _KEYWORDS.get(name)
        if kind is not None:
            val = True if name == "True" else (False if name == "False" else None)
            self._emit(kind, val, name)
        elif name[0].isupper():
            self._emit(TK.UPPER, name, name)
        elif name == "_":
            self._emit(TK.UNDER, None, "_")
        else:
            self._emit(TK.IDENT, name, name)

    def _lex_symbol(self) -> None:  # noqa: C901
        ch  = self._peek()
        two = ch + self._peek(1)
        thr = two + self._peek(2)

        # Three-char
        if thr == ">>_": [self._adv() for _ in range(3)]; self._emit(TK.PIPE, None, ">>_"); return

        # Two-char
        two_map = {
            "~>": TK.DEMAND,  ":>": TK.CONS,  "::": TK.DCOLON,
            "->": TK.ARROW,   "<-": TK.LARROW, "-o": TK.LINARR,
            "|>": TK.PIPE,    "==": TK.EQEQ,   "/=": TK.NEQ,
            "<=": TK.LTE,     ">=": TK.GTE,    "&&": TK.AND,
            "||": TK.OR,      "++": TK.CONCAT,  "!!": TK.BANGBANG,
            "..": TK.DOTDOT,
        }
        if two in two_map:
            self._adv(); self._adv()
            self._emit(two_map[two], None, two); return

        # One-char
        one_map = {
            "(": TK.LPAREN, ")": TK.RPAREN, "[": TK.LBRACK, "]": TK.RBRACK,
            "{": TK.LBRACE, "}": TK.RBRACE, ",": TK.COMMA,  ";": TK.SEMI,
            "|": TK.BAR,    "=": TK.EQ,     "\\": TK.BSLASH,"!": TK.BANG,
            ".": TK.DOT,    "$": TK.DOLLAR,  "%": TK.PCT,   "+": TK.PLUS,
            "-": TK.MINUS,  "*": TK.STAR,   "/": TK.SLASH,  "<": TK.LT,
            ">": TK.GT,     "`": TK.BTICK,  "#": TK.HASH,   ":": TK.COLON,
            "~": TK.TILDE,  "^": TK.CARET,  "@": TK.AT,
        }
        if ch in one_map:
            self._adv(); self._emit(one_map[ch], None, ch); return

        raise LexError(f"unexpected character {ch!r}", self.line, self.col)


def tokenize(source: str, filename: str = "<stdin>") -> List[Token]:
    """Lex Æergia∞ source text and return the token list."""
    return Lexer(source, filename).tokenize()
