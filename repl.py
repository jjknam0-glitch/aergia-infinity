"""
aergia.repl
~~~~~~~~~~~
Æergia∞ interactive REPL (Read-Eval-Print Loop).

Commands:
  :help              — show help
  :quit / :q         — exit
  :load <file>       — load an .ae source file
  :type <expr>       — show approximate type of an expression
  :reset             — reset to fresh environment
  :env               — list all names in scope
  :stream <n> <expr> — force and show first n elements of a stream
  :compress <expr>   — auto-compress a list and show ratio
  :sources           — list available data sources
"""
from __future__ import annotations
import sys, os, traceback
from typing import Optional

from .thunk    import force
from .stream   import Stream, Empty, EMPTY, take, drop
from .evaluator import Env, eval_programme, IOAction, AegRuntimeError, BuiltinFn, Constructor
from .symbolic import auto_compress
from . import stdlib

BANNER = r"""
   Æergia∞  v0.1.0
   ─────────────────────────────────────────────────────────────────
   A lazy, symbolic, stream-oriented language for infinite data.

   primes ~> 10          →  [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
   fibs !! 50            →  12586269025
   openSDSS "GALAXY" ~> 3   →  first 3 SDSS galaxy records

   Type :help for commands.  Ctrl-D to quit.
"""

HELP = """
Æergia∞ REPL Commands
──────────────────────
:help                    Show this message
:quit  / :q              Exit
:load  <file.ae>         Load source file
:type  <expr>            Show inferred type
:reset                   Reset to fresh environment
:env                     List all names in scope
:stream <n> <expr>       Force n elements from a stream
:compress <expr>         Auto-compress a list, show ratio
:sources                 List available data sources

Examples
────────
primes ~> 10
fibs !! 30
let evens = sfilter (\\n -> n `mod` 2 == 0) (from 0)
evens ~> 8
:stream 20 (smap (\\n -> n * n) (from 0))
:load examples/02_galaxy_survey.ae
:compress [1.0, 1.1, 1.2, 1.1, 1.3, 1.2]
"""


def _show(val, max_stream: int = 20) -> str:
    val = force(val)
    if val is None:   return "()"
    if val is True:   return "True"
    if val is False:  return "False"
    if isinstance(val, str):   return repr(val)
    if isinstance(val, (int, float)): return repr(val)
    if isinstance(val, tuple): return "(" + ", ".join(_show(e) for e in val) + ")"
    if isinstance(val, list):
        if not val: return "[]"
        return "[" + ", ".join(_show(e) for e in val) + "]"
    if isinstance(val, dict):
        return "{" + ", ".join(f"{k}: {_show(v)}" for k, v in val.items()) + "}"
    if isinstance(val, (Stream, Empty)):
        items = take(max_stream, val)
        more  = not isinstance(force(drop(max_stream, val)), Empty)
        suffix = ", ∞]" if more else "]"
        return "[" + ", ".join(_show(e) for e in items) + suffix
    if isinstance(val, Constructor):
        if not val.args: return val.name
        return "(" + val.name + " " + " ".join(_show(a) for a in val.args) + ")"
    if isinstance(val, BuiltinFn): return f"<fn {val.name}>"
    if isinstance(val, IOAction):  return f"IO({val.desc})"
    return repr(val)


def _approx_type(val) -> str:
    val = force(val)
    if val is None:           return "Unit"
    if isinstance(val, bool): return "Bool"
    if isinstance(val, int):  return "Int"
    if isinstance(val, float):return "Float"
    if isinstance(val, str):  return "String"
    if isinstance(val, tuple): return "(" + ", ".join(_approx_type(e) for e in val) + ")"
    if isinstance(val, list):
        if not val: return "[a]"
        return f"[{_approx_type(val[0])}]"
    if isinstance(val, (Stream, Empty)):
        try:
            if isinstance(val, Empty): return "∞a"
            return f"∞{_approx_type(val.head)}"
        except Exception: return "∞a"
    if isinstance(val, Constructor):
        return val.name
    if isinstance(val, (BuiltinFn,)): return "a → b"
    if isinstance(val, IOAction):     return "IO a"
    return "?"


def _base_env() -> Env:
    env = Env()
    env.extend_mut(stdlib.PRELUDE)
    env.extend_mut(stdlib.STREAMS)
    env.extend_mut(stdlib.MATH)
    env.extend_mut(stdlib.SOURCES)
    env.extend_mut(stdlib.COMPRESS)
    return env


class REPL:
    def __init__(self) -> None:
        self.env = _base_env()

    def reset(self) -> None:
        self.env = _base_env()
        print("  Environment reset.")

    def handle_command(self, line: str) -> bool:
        parts = line.strip().split(None, 1)
        cmd   = parts[0].lower()
        rest  = parts[1] if len(parts) > 1 else ""

        if cmd in (":quit", ":q", ":exit"):
            print("  Goodbye."); return False

        if cmd == ":help":    print(HELP); return True
        if cmd == ":reset":   self.reset(); return True

        if cmd == ":env":
            names = sorted(self.env._b.keys())
            for i in range(0, len(names), 4):
                print("  " + "  ".join(f"{n:<22}" for n in names[i:i+4]))
            return True

        if cmd == ":sources":
            from .sources import REGISTRY
            for name, cls in REGISTRY.items():
                print(f"  {name:<12} — {cls.__doc__.strip().splitlines()[0]}")
            return True

        if cmd == ":load":
            path = rest.strip()
            if not path:          print("  Usage: :load <file.ae>"); return True
            if not os.path.exists(path): print(f"  File not found: {path!r}"); return True
            try:
                from .repl import run_file
                self.env = run_file(path, self.env)
                print(f"  Loaded {path!r}")
            except Exception as e: print(f"  Error: {e}")
            return True

        if cmd == ":type":
            if not rest: print("  Usage: :type <expr>"); return True
            try:
                val = self._eval_expr(rest)
                print(f"  :: {_approx_type(force(val))}")
            except Exception as e: print(f"  Error: {e}")
            return True

        if cmd == ":stream":
            sub = rest.split(None, 1)
            if len(sub) < 2: print("  Usage: :stream <n> <expr>"); return True
            try:
                n   = int(sub[0])
                val = force(self._eval_expr(sub[1]))
                print(f"  {take(n, val)!r}")
            except Exception as e: print(f"  Error: {e}")
            return True

        if cmd == ":compress":
            if not rest: print("  Usage: :compress <list-expr>"); return True
            try:
                data = force(self._eval_expr(rest))
                if not isinstance(data, list):
                    data = take(1000, data)
                data = [float(force(x)) for x in data]
                model = auto_compress(data)
                ratio = model.compression_ratio(len(data))
                print(f"  Model:   {model!r}")
                print(f"  Points:  {len(data)}")
                print(f"  Raw:     {len(data)*8} bytes")
                print(f"  Stored:  {model.parameter_bytes()} bytes")
                print(f"  Ratio:   {ratio:.1f}:1")
            except Exception as e: print(f"  Error: {e}")
            return True

        print(f"  Unknown command: {cmd!r}  (try :help)")
        return True

    def _eval_expr(self, source: str):
        from .lexer  import tokenize
        from .parser import Parser
        tokens = tokenize(source)
        return __import__("aergia.evaluator", fromlist=["eval_expr"]).eval_expr(
            self.env, Parser(tokens).parse_expr()
        )

    def eval_line(self, line: str) -> None:
        from .lexer     import tokenize, LexError
        from .parser    import Parser, ParseError
        from .evaluator import eval_programme

        line = line.strip()
        if not line: return

        # Try top-level declaration first
        try:
            from .lexer import TK
            tokens = tokenize(line)
            if (len(tokens) >= 2 and tokens[0].kind == TK.IDENT and
                    tokens[1].kind in (TK.EQ, TK.DCOLON)):
                prog = Parser(tokens).parse_programme()
                if prog.decls:
                    self.env = eval_programme(prog, self.env)
                    for d in prog.decls:
                        name = getattr(d, "name", None)
                        if name:
                            try:
                                v = force(self.env.lookup(name))
                                print(f"  {name} :: {_approx_type(v)}")
                            except Exception: pass
                    return
        except Exception: pass

        # Expression
        try:
            from .evaluator import eval_expr
            from .lexer     import tokenize, LexError
            from .parser    import Parser, ParseError
            tokens = tokenize(line)
            ast    = Parser(tokens).parse_expr()
            val    = eval_expr(self.env, ast)

            if isinstance(force(val), IOAction):
                result = force(val).run()
                if result is not None:
                    print(f"  {_show(result)}  :: {_approx_type(result)}")
            else:
                v = force(val)
                if v is not None:
                    print(f"  {_show(v)}  :: {_approx_type(v)}")

        except (LexError, ParseError) as e:
            print(f"  Syntax: {e}")
        except AegRuntimeError as e:
            print(f"  Runtime: {e}")
        except Exception as e:
            print(f"  Error: {e}")

    def run(self) -> None:
        print(BANNER)
        try:
            import readline, atexit
            hist = os.path.expanduser("~/.aergia_history")
            try: readline.read_history_file(hist)
            except FileNotFoundError: pass
            atexit.register(readline.write_history_file, hist)
        except ImportError: pass

        while True:
            try:
                line = input("æ∞> ")
            except (EOFError, KeyboardInterrupt):
                print("\n  Goodbye."); break
            if not line.strip(): continue
            if line.strip().startswith(":"):
                if not self.handle_command(line.strip()): break
            else:
                self.eval_line(line)


def run_file(path: str, env: Env) -> Env:
    from .lexer     import tokenize
    from .parser    import Parser
    from .evaluator import eval_programme
    with open(path) as f: src = f.read()
    from .parser import parse
    prog = parse(src, path)
    return eval_programme(prog, env)


def run_script(path: str) -> None:
    env = _base_env()
    try:
        env = run_file(path, env)
        try:
            main_val = force(env.lookup("main"))
            if isinstance(main_val, IOAction): main_val.run()
        except AegRuntimeError: pass
    except FileNotFoundError:
        print(f"File not found: {path!r}", file=sys.stderr); sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if os.environ.get("AERGIA_DEBUG"): traceback.print_exc()
        sys.exit(1)
