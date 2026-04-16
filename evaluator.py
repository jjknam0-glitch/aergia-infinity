"""
aergia.evaluator
~~~~~~~~~~~~~~~~
The Æergia∞ runtime: a call-by-need graph-reduction interpreter.

The key insight: every binding is a Thunk. When the runtime needs a concrete
value (for arithmetic, comparison, or to satisfy a ~> demand), it forces
the thunk and memoises the result. Infinite streams are never fully evaluated;
only the portions demanded are ever computed.

The demand operator (~>) propagates backwards through the pipeline:
  - filter/map operations are fused into single-pass evaluation
  - source fetches are batched to minimise network round-trips
  - compressed values are decompressed only at the boundary of observation
"""
from __future__ import annotations
import operator as _op
from typing import Any, Dict, List, Optional

from .thunk  import Thunk, force, delay
from .stream import (
    Stream, Empty, EMPTY, cons,
    smap, sfilter, zip_with, szip, scan, take, drop,
    nth, take_while, drop_while, first_where, chunk,
    window, interleave, merge_sorted, flatten, primes, fibs, pi_digits,
    from_n, repeat, iterate, cycle, unfold, range_finite, from_list, from_iter,
)
from .symbolic import (
    FourierN, PolynomialN, BlackbodySpectrum, GaussianMixture,
    DeltaChain, WaveletModel, SymbolicExpr, SymbolicArchive, auto_compress,
)
from .sources import (
    SDSSSource, JWSTSource, LIGOSource, GAIASource,
    FileSource, CSVSource, MockSpectralSource, open_source,
)


# ── Runtime value types ──────────────────────────────────────────────────────

class Closure:
    __slots__ = ("params", "body", "env", "name")
    def __init__(self, params, body, env, name="<fn>"): self.params=params; self.body=body; self.env=env; self.name=name
    def __repr__(self): return f"<fn {self.name}/{len(self.params)}>"

class BuiltinFn:
    __slots__ = ("fn", "name", "arity", "_args")
    def __init__(self, fn, name, arity=1, _args=None): self.fn=fn; self.name=name; self.arity=arity; self._args=_args or []
    def apply(self, arg):
        args = self._args + [arg]
        if len(args) >= self.arity: return self.fn(*args)
        return BuiltinFn(self.fn, self.name, self.arity, args)
    def __repr__(self): return f"<builtin {self.name}>"

class Constructor:
    __slots__ = ("name", "arity", "args")
    def __init__(self, name, arity, args=None): self.name=name; self.arity=arity; self.args=args or []
    def apply(self, arg): return Constructor(self.name, self.arity, self.args+[force(arg)])
    @property
    def complete(self): return len(self.args) >= self.arity
    def __repr__(self): return f"({self.name} {' '.join(map(repr,self.args))})" if self.args else self.name
    def __eq__(self, o): return isinstance(o, Constructor) and self.name==o.name and self.args==o.args

class IOAction:
    __slots__ = ("fn", "desc")
    def __init__(self, fn, desc="<io>"): self.fn=fn; self.desc=desc
    def run(self): return self.fn()
    def __repr__(self): return f"IO({self.desc})"

class AegRuntimeError(Exception):
    def __init__(self, msg, node=None):
        loc = f" at {node.line}:{node.col}" if node and hasattr(node,"line") else ""
        super().__init__(f"Æergia∞ runtime error{loc}: {msg}")


# ── Environment ──────────────────────────────────────────────────────────────

class Env:
    def __init__(self, bindings: Dict[str,Any]=None, parent: "Env"=None):
        self._b = bindings or {}
        self._p = parent

    def lookup(self, name: str) -> Any:
        e = self
        while e:
            if name in e._b: return e._b[name]
            e = e._p
        raise AegRuntimeError(f"undefined name: {name!r}")

    def extend(self, bindings: Dict[str,Any]) -> "Env":
        return Env(bindings, self)

    def extend_mut(self, bindings: Dict[str,Any]) -> "Env":
        self._b.update(bindings); return self


# ── Pattern matching ─────────────────────────────────────────────────────────

def match_pat(pat, val: Any) -> Optional[Dict[str,Any]]:
    from .ast_nodes import (PWild, PVar, PLit, PCons, PListCons,
                             PTuple, PList, PConstructor, PAs)
    val = force(val)
    if isinstance(pat, PWild):  return {}
    if isinstance(pat, PVar):   return {pat.name: val}
    if isinstance(pat, PLit):
        exp = pat.value
        if exp is None: return {} if val is None else None
        return {} if val == exp else None
    if isinstance(pat, PConstructor):
        if not isinstance(val, Constructor) or val.name != pat.name: return None
        if len(val.args) != len(pat.args): return None
        out = {}
        for sp, sv in zip(pat.args, val.args):
            r = match_pat(sp, sv)
            if r is None: return None
            out.update(r)
        return out
    if isinstance(pat, PTuple):
        if not isinstance(val, tuple) or len(val) != len(pat.elements): return None
        out = {}
        for sp, sv in zip(pat.elements, val):
            r = match_pat(sp, sv)
            if r is None: return None
            out.update(r)
        return out
    if isinstance(pat, PList):
        if not isinstance(val, list) or len(val) != len(pat.elements): return None
        out = {}
        for sp, sv in zip(pat.elements, val):
            r = match_pat(sp, sv)
            if r is None: return None
            out.update(r)
        return out
    if isinstance(pat, PCons):
        if isinstance(val, Empty): return None
        if isinstance(val, Stream):
            h = match_pat(pat.head, val.head)
            if h is None: return None
            t = match_pat(pat.tail, val.tail)
            if t is None: return None
            return {**h, **t}
        return None
    if isinstance(pat, PListCons):
        if not isinstance(val, list) or not val: return None
        h = match_pat(pat.head, val[0])
        if h is None: return None
        t = match_pat(pat.tail, val[1:])
        if t is None: return None
        return {**h, **t}
    if isinstance(pat, PAs):
        r = match_pat(pat.pattern, val)
        if r is None: return None
        return {**r, pat.name: val}
    raise AegRuntimeError(f"unknown pattern type: {type(pat).__name__}")


# ── Application ──────────────────────────────────────────────────────────────

def apply_fn(fn: Any, arg: Any) -> Any:
    fn = force(fn)
    if isinstance(fn, Closure):
        if not fn.params:
            raise AegRuntimeError(f"zero-param closure applied to argument")
        pat = fn.params[0]
        val = force(arg)
        bindings = match_pat(pat, val)
        if bindings is None:
            raise AegRuntimeError(
                f"pattern match failure in {fn.name!r}: {val!r} vs {pat!r}"
            )
        new_env = fn.env.extend(bindings)
        if len(fn.params) == 1:
            return eval_expr(new_env, fn.body)
        return Closure(fn.params[1:], fn.body, new_env, fn.name)
    if isinstance(fn, BuiltinFn):
        return fn.apply(arg)
    if isinstance(fn, Constructor):
        return fn.apply(force(arg))
    raise AegRuntimeError(f"applied non-function: {fn!r} ({type(fn).__name__})")


# ── Binary operators ─────────────────────────────────────────────────────────

def eval_binop(op: str, lv: Any, rv: Any) -> Any:
    lv, rv = force(lv), force(rv)
    ops = {
        "+": _op.add, "-": _op.sub, "*": _op.mul,
        "/": lambda a,b: a/b, "%": _op.mod, "^": _op.pow,
        "==": _op.eq, "/=": _op.ne, "<": _op.lt, ">": _op.gt,
        "<=": _op.le, ">=": _op.ge,
        "&&": lambda a,b: a and b, "||": lambda a,b: a or b,
        "++": lambda a,b: (a+b if isinstance(a,(list,str)) else take(10**9,a)+take(10**9,b)),
        "::": lambda a,b: [a]+(b if isinstance(b,list) else list(b)),
        "~>": lambda s,n: _demand_op(s, n),
    }
    if op not in ops: raise AegRuntimeError(f"unknown operator: {op!r}")
    return ops[op](lv, rv)


def _demand_op(s: Any, spec: Any) -> Any:
    """Runtime implementation of the ~> demand operator."""
    from .stream import demand
    s = force(s)
    spec = force(spec)
    return demand(s, spec)


# ── Core evaluator ────────────────────────────────────────────────────────────

def eval_expr(env: Env, node) -> Any:  # noqa: C901
    from .ast_nodes import (
        IntLit, FloatLit, StrLit, CharLit, BoolLit, UnitLit,
        Var, ConstructorExpr, App, Lam, Let, Where, IfExpr, MatchExpr,
        DoExpr, BinOp, UnOp, Force, Suspend, Pipe, StreamConsExpr,
        TupleLit, ListLit, RangeLit, DemandExpr, RecordLit,
        RecordUpdate, FieldAccess, TypeAnn, IndexExpr, ComposeExpr,
        Dollar, InfixApp, SourceExpr, CompressExpr, ArchiveExpr,
    )

    if isinstance(node, IntLit):   return node.value
    if isinstance(node, FloatLit): return node.value
    if isinstance(node, StrLit):   return node.value
    if isinstance(node, CharLit):  return node.value
    if isinstance(node, BoolLit):  return node.value
    if isinstance(node, UnitLit):  return None

    if isinstance(node, Var):
        return env.lookup(node.name)

    if isinstance(node, ConstructorExpr):
        try:
            return env.lookup(node.name)
        except AegRuntimeError:
            return Constructor(node.name, 99)

    if isinstance(node, App):
        fn  = eval_expr(env, node.func)
        arg = Thunk(lambda n=node.arg, e=env: eval_expr(e, n))
        return apply_fn(fn, arg)

    if isinstance(node, Lam):
        return Closure(node.params, node.body, env)

    if isinstance(node, Let):
        new_env = env.extend({})
        thunks = {b.name: Thunk(lambda b=b, e=new_env: _eval_binding(e, b))
                  for b in node.bindings}
        new_env.extend_mut(thunks)
        return eval_expr(new_env, node.body)

    if isinstance(node, Where):
        return eval_expr(env, Let(node.bindings, node.body, node.line, node.col))

    if isinstance(node, IfExpr):
        cond = force(eval_expr(env, node.cond))
        return eval_expr(env, node.then_expr if cond else node.else_expr)

    if isinstance(node, MatchExpr):
        scrutinee = force(eval_expr(env, node.scrutinee))
        for pat, guard, body in node.arms:
            bindings = match_pat(pat, scrutinee)
            if bindings is not None:
                arm_env = env.extend(bindings)
                if guard is not None:
                    if not force(eval_expr(arm_env, guard)):
                        continue
                return eval_expr(arm_env, body)
        raise AegRuntimeError(f"non-exhaustive match on: {scrutinee!r}", node)

    if isinstance(node, DoExpr):
        return eval_do(env, node.stmts)

    if isinstance(node, BinOp):
        lv = eval_expr(env, node.left)
        rv = eval_expr(env, node.right)
        return eval_binop(node.op, lv, rv)

    if isinstance(node, UnOp):
        v = force(eval_expr(env, node.expr))
        if node.op == "-":  return -v
        if node.op == "not": return not v
        raise AegRuntimeError(f"unknown unary op: {node.op!r}")

    if isinstance(node, Force):
        return force(eval_expr(env, node.expr))

    if isinstance(node, Suspend):
        return Thunk(lambda: eval_expr(env, node.expr))

    if isinstance(node, Pipe):
        lv = eval_expr(env, node.left)
        rv = eval_expr(env, node.right)
        return apply_fn(rv, lv)

    if isinstance(node, Dollar):
        fn  = eval_expr(env, node.func)
        arg = Thunk(lambda: eval_expr(env, node.arg))
        return apply_fn(fn, arg)

    if isinstance(node, ComposeExpr):
        f = eval_expr(env, node.left)
        g = eval_expr(env, node.right)
        return BuiltinFn(lambda x, f=f, g=g: apply_fn(f, apply_fn(g, x)), "<∘>", 1)

    if isinstance(node, StreamConsExpr):
        head = eval_expr(env, node.head)
        tail = Thunk(lambda: force(eval_expr(env, node.tail)))
        return cons(head, tail)

    if isinstance(node, DemandExpr):
        s    = force(eval_expr(env, node.stream))
        spec = force(eval_expr(env, node.spec))
        return _demand_op(s, spec)

    if isinstance(node, RangeLit):
        start = force(eval_expr(env, node.start))
        if node.stop is None and node.step is None:
            return from_n(start)
        if node.stop is None and node.step is not None:
            step_val = force(eval_expr(env, node.step)) - start
            return from_n(start, step_val)
        stop_val = force(eval_expr(env, node.stop))
        if node.step is not None:
            step_val = force(eval_expr(env, node.step)) - start
        else:
            step_val = 1
        return range_finite(start, stop_val, step_val)

    if isinstance(node, TupleLit):
        return tuple(eval_expr(env, e) for e in node.elements)

    if isinstance(node, ListLit):
        return [eval_expr(env, e) for e in node.elements]

    if isinstance(node, IndexExpr):
        s = force(eval_expr(env, node.stream))
        n = force(eval_expr(env, node.idx))
        return nth(s, n)

    if isinstance(node, RecordLit):
        return {name: eval_expr(env, val) for name, val in node.fields}

    if isinstance(node, RecordUpdate):
        base = force(eval_expr(env, node.base))
        if not isinstance(base, dict):
            raise AegRuntimeError("record update on non-record")
        return {**base, **{k: eval_expr(env, v) for k, v in node.fields}}

    if isinstance(node, FieldAccess):
        obj = force(eval_expr(env, node.obj))
        if isinstance(obj, dict):
            if node.field not in obj:
                raise AegRuntimeError(f"no field {node.field!r}")
            return obj[node.field]
        raise AegRuntimeError(f"field access on non-record: {type(obj).__name__}")

    if isinstance(node, TypeAnn):
        return eval_expr(env, node.expr)

    if isinstance(node, InfixApp):
        fn = force(eval_expr(env, node.op))
        lv = Thunk(lambda: eval_expr(env, node.left))
        rv = Thunk(lambda: eval_expr(env, node.right))
        return apply_fn(apply_fn(fn, lv), rv)

    if isinstance(node, SourceExpr):
        # source <name> <kwargs> — open a data source as a stream
        kwargs = {k: force(eval_expr(env, v)) for k, v in node.kwargs.items()}
        return open_source(node.source_name, **kwargs)

    if isinstance(node, CompressExpr):
        data  = force(eval_expr(env, node.data))
        model_cls = {
            "FourierN":         FourierN,
            "PolynomialN":      PolynomialN,
            "BlackbodySpectrum":BlackbodySpectrum,
            "GaussianMixture":  GaussianMixture,
            "DeltaChain":       DeltaChain,
            "WaveletModel":     WaveletModel,
            "Auto":             None,
        }.get(node.model_name)
        if model_cls is None:
            return auto_compress(data if isinstance(data, list) else list(data))
        model = model_cls(**{k: force(eval_expr(env, v)) for k, v in node.model_kwargs.items()})
        return model.fit(data if isinstance(data, list) else list(data))

    raise AegRuntimeError(f"cannot eval node: {type(node).__name__}", node)


def _eval_binding(env: Env, binding) -> Any:
    from .ast_nodes import GuardedBody, Let
    body = binding.body
    if binding.where:
        body = Let(binding.where, body)
    if binding.params:
        return Closure(binding.params, body, env, binding.name)
    if isinstance(body, GuardedBody):
        for guard_expr, guard_body in body.guards:
            g = force(eval_expr(env, guard_expr))
            if g is True or g == "otherwise":
                return eval_expr(env, guard_body)
        raise AegRuntimeError(f"no guard matched in {binding.name!r}")
    return eval_expr(env, body)


def eval_do(env: Env, stmts: list) -> IOAction:
    from .ast_nodes import DoExprStmt, DoBind, DoLet
    if not stmts:
        return IOAction(lambda: None, "return ()")
    stmt, rest = stmts[0], stmts[1:]

    if isinstance(stmt, DoExprStmt):
        action = force(eval_expr(env, stmt.expr))
        if not rest:
            return action if isinstance(action, IOAction) else IOAction(lambda a=action: a, "pure")
        def run(a=action, r=rest, e=env):
            if isinstance(a, IOAction): a.run()
            return eval_do(e, r).run()
        return IOAction(run, ">>")

    if isinstance(stmt, DoBind):
        action = force(eval_expr(env, stmt.expr))
        def run(name=stmt.name, a=action, r=rest, e=env):
            val = a.run() if isinstance(a, IOAction) else a
            return eval_do(e.extend({name: val}), r).run()
        return IOAction(run, f">>= {stmt.name}")

    if isinstance(stmt, DoLet):
        new_env = env.extend({})
        for b in stmt.bindings:
            new_env.extend_mut({b.name: Thunk(lambda b=b, e=new_env: _eval_binding(e, b))})
        return eval_do(new_env, rest)

    raise AegRuntimeError(f"unknown do-stmt: {type(stmt).__name__}")


def eval_programme(prog, env: Env) -> Env:
    """Evaluate all top-level declarations, return updated env."""
    from .ast_nodes import (ImportDecl, TypeSig, TypeDecl, CodataDecl,
                             ClassDecl, InstanceDecl, ModuleDecl,
                             DataDecl, Binding, SourceDecl, ArchiveDecl)
    from . import stdlib
    MODULE_MAP = {
        "Streams":    stdlib.STREAMS,
        "Math":       stdlib.MATH,
        "IO":         stdlib.IO,
        "Crypto":     stdlib.CRYPTO,
        "Concurrent": stdlib.CONCURRENT,
        "Sources":    stdlib.SOURCES,
        "Compress":   stdlib.COMPRESS,
        "Prelude":    stdlib.PRELUDE,
    }

    new_env = env.extend({})
    pending = []

    for decl in prog.decls:
        if isinstance(decl, ImportDecl):
            mod = decl.module.split(".")[0]
            if mod in MODULE_MAP:
                m = MODULE_MAP[mod]
                if decl.items:
                    for item in decl.items:
                        if item in m: new_env.extend_mut({item: m[item]})
                elif decl.alias:
                    for k, v in m.items(): new_env.extend_mut({f"{decl.alias}.{k}": v})
                else:
                    new_env.extend_mut(m)
        elif isinstance(decl, DataDecl):
            for ctor_name, ctor_args in decl.constructors:
                arity = len(ctor_args)
                new_env.extend_mut({ctor_name: Constructor(ctor_name, arity)})
        elif isinstance(decl, Binding):
            pending.append(decl)
        elif isinstance(decl, SourceDecl):
            # source name = SourceType kwargs
            src = open_source(decl.source_type, **decl.kwargs)
            new_env.extend_mut({decl.name: src})

    # Create forward-reference thunks for all bindings (enables mutual recursion)
    thunks = {b.name: Thunk(lambda b=b, e=new_env: _eval_binding(e, b))
              for b in pending}
    new_env.extend_mut(thunks)
    return new_env
