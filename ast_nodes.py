"""
aergia.ast_nodes
~~~~~~~~~~~~~~~~
All AST node types for Æergia∞.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


@dataclass
class Node:
    line: int = field(default=0, repr=False, compare=False)
    col:  int = field(default=0, repr=False, compare=False)

# ── Expressions ──────────────────────────────────────────────────────────────

@dataclass
class IntLit(Node):       value: int
@dataclass
class FloatLit(Node):     value: float
@dataclass
class StrLit(Node):       value: str
@dataclass
class CharLit(Node):      value: str
@dataclass
class BoolLit(Node):      value: bool
@dataclass
class UnitLit(Node):      pass
@dataclass
class Var(Node):          name: str
@dataclass
class ConstructorExpr(Node): name: str
@dataclass
class App(Node):          func: Any; arg: Any
@dataclass
class Lam(Node):          params: list; body: Any
@dataclass
class Let(Node):          bindings: list; body: Any
@dataclass
class Where(Node):        body: Any; bindings: list
@dataclass
class IfExpr(Node):       cond: Any; then_expr: Any; else_expr: Any
@dataclass
class MatchExpr(Node):    scrutinee: Any; arms: list  # [(pat, guard, body)]
@dataclass
class DoExpr(Node):       stmts: list
@dataclass
class BinOp(Node):        op: str; left: Any; right: Any
@dataclass
class UnOp(Node):         op: str; expr: Any
@dataclass
class Force(Node):        expr: Any   # !expr
@dataclass
class Suspend(Node):      expr: Any   # ~expr
@dataclass
class Pipe(Node):         left: Any; right: Any    # |>
@dataclass
class Dollar(Node):       func: Any; arg: Any
@dataclass
class ComposeExpr(Node):  left: Any; right: Any   # .
@dataclass
class StreamConsExpr(Node): head: Any; tail: Any  # :>
@dataclass
class DemandExpr(Node):   stream: Any; spec: Any  # ~>
@dataclass
class RangeLit(Node):
    start: Any
    stop:  Optional[Any] = None
    step:  Optional[Any] = None   # [start,step..stop] or [start..stop] or [start..]
@dataclass
class TupleLit(Node):     elements: list
@dataclass
class ListLit(Node):      elements: list
@dataclass
class RecordLit(Node):    fields: list   # [(name, expr)]
@dataclass
class RecordUpdate(Node): base: Any; fields: list
@dataclass
class FieldAccess(Node):  obj: Any; field: str
@dataclass
class TypeAnn(Node):      expr: Any; type_: Any
@dataclass
class IndexExpr(Node):    stream: Any; idx: Any   # !!
@dataclass
class InfixApp(Node):     op: Any; left: Any; right: Any   # backtick
@dataclass
class SourceExpr(Node):   source_name: str; kwargs: dict
@dataclass
class CompressExpr(Node): data: Any; model_name: str; model_kwargs: dict
@dataclass
class ArchiveExpr(Node):  name: str; source: Any; model_name: str; kwargs: dict


# ── Patterns ─────────────────────────────────────────────────────────────────

@dataclass
class PWild(Node):        pass
@dataclass
class PVar(Node):         name: str
@dataclass
class PLit(Node):         value: Any
@dataclass
class PConstructor(Node): name: str; args: list
@dataclass
class PTuple(Node):       elements: list
@dataclass
class PList(Node):        elements: list
@dataclass
class PCons(Node):        head: Any; tail: Any   # :>
@dataclass
class PListCons(Node):    head: Any; tail: Any   # ::
@dataclass
class PAs(Node):          name: str; pattern: Any


# ── Do-notation statements ────────────────────────────────────────────────────

@dataclass
class DoBind(Node):     name: str; expr: Any
@dataclass
class DoLet(Node):      bindings: list
@dataclass
class DoExprStmt(Node): expr: Any


# ── Top-level declarations ────────────────────────────────────────────────────

@dataclass
class Binding(Node):
    name:     str
    params:   list
    body:     Any
    where:    list = field(default_factory=list)
    type_sig: Any  = None

@dataclass
class GuardedBody(Node):
    guards: list   # [(guard_expr, body_expr)]

@dataclass
class TypeSig(Node):     name: str; type_: Any
@dataclass
class TypeDecl(Node):    name: str; params: list; rhs: Any
@dataclass
class DataDecl(Node):    name: str; params: list; constructors: list
@dataclass
class CodataDecl(Node):  name: str; params: list; observations: list
@dataclass
class ClassDecl(Node):   name: str; params: list; methods: list
@dataclass
class InstanceDecl(Node):class_name: str; type_: Any; methods: list
@dataclass
class ImportDecl(Node):
    module:    str
    items:     Optional[list] = None
    qualified: bool = False
    alias:     Optional[str] = None
@dataclass
class ModuleDecl(Node):  name: str; exposing: Optional[list] = None
@dataclass
class SourceDecl(Node):  name: str; source_type: str; kwargs: dict = field(default_factory=dict)
@dataclass
class ArchiveDecl(Node): name: str; source: Any; model_name: str; kwargs: dict = field(default_factory=dict)


# ── Type expressions ─────────────────────────────────────────────────────────

@dataclass
class TName(Node):      name: str
@dataclass
class TVar(Node):       name: str
@dataclass
class TInf(Node):       elem: Any    # ∞T
@dataclass
class TApp(Node):       func: Any; arg: Any
@dataclass
class TArrow(Node):     param: Any; result: Any
@dataclass
class TLinear(Node):    param: Any; result: Any   # -o
@dataclass
class TTuple(Node):     elements: list
@dataclass
class TList(Node):      elem: Any
@dataclass
class TRefinement(Node):var: str; type_: Any; pred: Any
@dataclass
class TForall(Node):    vars: list; body: Any


# ── Programme ─────────────────────────────────────────────────────────────────

@dataclass
class Programme(Node):
    decls: list
