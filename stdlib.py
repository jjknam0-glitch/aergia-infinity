"""
aergia.stdlib
~~~~~~~~~~~~~
Æergia∞ standard library — Python implementations exposed to the runtime.

Organised into modules that match the import system:
  Prelude    — auto-imported core functions
  Streams    — infinite stream operations + demand
  Math       — exact arithmetic, number streams, signal processing
  IO         — file, network, terminal I/O
  Crypto     — cryptographic streams and hash chains
  Concurrent — parallel evaluation and channels
  Sources    — data source adapters (SDSS, JWST, LIGO, GAIA, …)
  Compress   — symbolic compression models
"""
from __future__ import annotations
import math, os, sys, time, hashlib, secrets, threading
import queue as _queue
from fractions import Fraction
from typing import Any

from .thunk  import Thunk, force, delay
from .stream import (
    Stream, Empty, EMPTY, cons, from_n, repeat, iterate, cycle, unfold,
    smap, sfilter, zip_with, szip, scan, take, drop, nth, take_while,
    drop_while, first_where, chunk, window, interleave, merge_sorted,
    flatten, primes as _primes, fibs as _fibs, pi_digits, from_list, from_iter,
    range_finite, demand,
)
from .symbolic import (
    FourierN, PolynomialN, BlackbodySpectrum, GaussianMixture,
    DeltaChain, WaveletModel, SymbolicExpr, SymbolicArchive, auto_compress,
)
from .sources import (
    SDSSSource, JWSTSource, LIGOSource, GAIASource,
    FileSource, CSVSource, MockSpectralSource, open_source,
)
from .evaluator import (
    BuiltinFn, Constructor, IOAction, apply_fn, AegRuntimeError,
)


# ── Helper ───────────────────────────────────────────────────────────────────

def _b(fn, name: str, arity: int = 1) -> BuiltinFn:
    return BuiltinFn(fn, name, arity)

def _just(x):  v = Constructor("Just",1);  return v.apply(x)
def _nothing(): return Constructor("Nothing", 0)
def _ok(x):    v = Constructor("Ok",1);    return v.apply(x)
def _err(x):   v = Constructor("Err",1);   return v.apply(x)

def _show(x) -> str:
    x = force(x)
    if x is None:   return "()"
    if x is True:   return "True"
    if x is False:  return "False"
    if isinstance(x, str):   return x
    if isinstance(x, float): return repr(round(x, 8))
    if isinstance(x, list):  return "[" + ", ".join(_show(e) for e in x) + "]"
    if isinstance(x, tuple): return "(" + ", ".join(_show(e) for e in x) + ")"
    if isinstance(x, dict):  return "{" + ", ".join(f"{k}: {_show(v)}" for k,v in x.items()) + "}"
    if isinstance(x, (Stream, Empty)):
        items = take(12, x)
        more  = not isinstance(force(drop(12, x)), Empty)
        tail  = ", ∞]" if more else "]"
        return "[" + ", ".join(_show(e) for e in items) + tail
    if isinstance(x, Constructor):
        if not x.args: return x.name
        return "(" + x.name + " " + " ".join(_show(a) for a in x.args) + ")"
    if isinstance(x, (BuiltinFn, IOAction)):  return repr(x)
    return repr(x)


# ── Prelude ───────────────────────────────────────────────────────────────────

PRELUDE: dict = {
    # Output
    "print":      _b(lambda x: IOAction(lambda: print(_show(force(x))), "print"), "print"),
    "putStr":     _b(lambda s: IOAction(lambda: print(force(s), end=""), "putStr"), "putStr"),
    "putStrLn":   _b(lambda s: IOAction(lambda: print(force(s)), "putStrLn"), "putStrLn"),
    "readLine":   IOAction(lambda: input(), "readLine"),

    # Show / convert
    "show":       _b(_show, "show"),
    "toInt":      _b(lambda x: int(force(x)), "toInt"),
    "toFloat":    _b(lambda x: float(force(x)), "toFloat"),
    "toString":   _b(lambda x: str(force(x)), "toString"),
    "ord":        _b(lambda c: ord(force(c)), "ord"),
    "chr":        _b(lambda n: chr(force(n)), "chr"),

    # Numeric
    "abs":    _b(lambda x: abs(force(x)), "abs"),
    "negate": _b(lambda x: -force(x), "negate"),
    "sqrt":   _b(lambda x: math.sqrt(force(x)), "sqrt"),
    "floor":  _b(lambda x: int(math.floor(force(x))), "floor"),
    "ceil":   _b(lambda x: int(math.ceil(force(x))), "ceil"),
    "round":  _b(lambda x: round(force(x)), "round"),
    "max":    _b(lambda a: _b(lambda b, a=a: max(force(a), force(b)), "max"), "max", 2),
    "min":    _b(lambda a: _b(lambda b, a=a: min(force(a), force(b)), "min"), "min", 2),
    "div":    _b(lambda a: _b(lambda b, a=a: force(a) // force(b), "div"), "div", 2),
    "mod":    _b(lambda a: _b(lambda b, a=a: force(a) % force(b), "mod"), "mod", 2),
    "gcd":    _b(lambda a: _b(lambda b, a=a: math.gcd(int(force(a)), int(force(b))), "gcd"), "gcd", 2),
    "even":   _b(lambda n: force(n) % 2 == 0, "even"),
    "odd":    _b(lambda n: force(n) % 2 != 0, "odd"),
    "succ":   _b(lambda n: force(n) + 1, "succ"),
    "pred":   _b(lambda n: force(n) - 1, "pred"),
    "fromInt":_b(lambda n: float(force(n)), "fromInt"),
    "sin":    _b(lambda x: math.sin(force(x)), "sin"),
    "cos":    _b(lambda x: math.cos(force(x)), "cos"),
    "exp":    _b(lambda x: math.exp(force(x)), "exp"),
    "log":    _b(lambda x: math.log(force(x)), "log"),

    # Logic
    "not":  _b(lambda b: not force(b), "not"),
    "True": True, "False": False, "otherwise": True,

    # Maybe
    "Just":       Constructor("Just", 1),
    "Nothing":    Constructor("Nothing", 0),
    "isJust":     _b(lambda m: isinstance(force(m), Constructor) and force(m).name == "Just", "isJust"),
    "isNothing":  _b(lambda m: isinstance(force(m), Constructor) and force(m).name == "Nothing", "isNothing"),
    "fromMaybe":  _b(lambda d: _b(lambda m, d=d:
        force(m).args[0] if isinstance(force(m), Constructor) and force(m).name == "Just"
        else force(d), "fromMaybe"), "fromMaybe", 2),
    "Ok":  Constructor("Ok", 1),
    "Err": Constructor("Err", 1),

    # Lists
    "length":   _b(lambda xs: len(force(xs)), "length"),
    "null":     _b(lambda xs: force(xs) == [] or isinstance(force(xs), Empty), "null"),
    "head":     _b(lambda xs: force(xs)[0] if isinstance(force(xs), list) else force(xs).head, "head"),
    "tail":     _b(lambda xs: force(xs)[1:] if isinstance(force(xs), list) else force(xs).tail, "tail"),
    "last":     _b(lambda xs: force(xs)[-1], "last"),
    "reverse":  _b(lambda xs: list(reversed(force(xs))), "reverse"),
    "concat":   _b(lambda xss: [x for xs in force(xss) for x in force(xs)], "concat"),
    "sum":      _b(lambda xs: sum(force(e) for e in force(xs)), "sum"),
    "product":  _b(lambda xs: math.prod(force(e) for e in force(xs)), "product"),
    "maximum":  _b(lambda xs: max(force(e) for e in force(xs)), "maximum"),
    "minimum":  _b(lambda xs: min(force(e) for e in force(xs)), "minimum"),
    "sort":     _b(lambda xs: sorted(force(xs)), "sort"),
    "nub":      _b(lambda xs: list(dict.fromkeys(force(xs))), "nub"),
    "elem":     _b(lambda x: _b(lambda xs, x=x: force(x) in force(xs), "elem"), "elem", 2),
    "fst":      _b(lambda t: force(t)[0], "fst"),
    "snd":      _b(lambda t: force(t)[1], "snd"),
    "zip":      _b(lambda a: _b(lambda b, a=a: list(zip(force(a), force(b))), "zip"), "zip", 2),
    "unzip":    _b(lambda xs: tuple(zip(*force(xs))), "unzip"),
    "words":    _b(lambda s: force(s).split(), "words"),
    "lines":    _b(lambda s: force(s).split("\n"), "lines"),
    "unwords":  _b(lambda ws: " ".join(force(ws)), "unwords"),
    "unlines":  _b(lambda ls: "\n".join(force(ls)), "unlines"),

    # Higher-order
    "map":       _b(lambda f: _b(lambda xs, f=f: [force(apply_fn(f, force(x))) for x in force(xs)], "map"), "map", 2),
    "filter":    _b(lambda p: _b(lambda xs, p=p: [x for x in force(xs) if force(apply_fn(p, force(x)))], "filter"), "filter", 2),
    "foldl":     _b(lambda f: _b(lambda z: _b(lambda xs, f=f, z=z:
        __import__("functools").reduce(lambda acc, x: apply_fn(apply_fn(f, acc), x), force(xs), force(z)),
        "foldl"), "foldl"), "foldl", 3),
    "foldr":     _b(lambda f: _b(lambda z: _b(lambda xs, f=f, z=z:
        __import__("functools").reduce(lambda x, acc: apply_fn(apply_fn(f, x), acc), reversed(force(xs)), force(z)),
        "foldr"), "foldr"), "foldr", 3),
    "any":       _b(lambda p: _b(lambda xs, p=p: any(force(apply_fn(p, x)) for x in force(xs)), "any"), "any", 2),
    "all":       _b(lambda p: _b(lambda xs, p=p: all(force(apply_fn(p, x)) for x in force(xs)), "all"), "all", 2),
    "zipWith":   _b(lambda f: _b(lambda a: _b(lambda b, f=f, a=a:
        [force(apply_fn(apply_fn(f, fa), fb)) for fa, fb in zip(force(a), force(b))], "zipWith"), "zipWith"), "zipWith", 3),
    "mapM_":     _b(lambda f: _b(lambda xs, f=f:
        IOAction(lambda: [force(apply_fn(f, x)).run() if isinstance(force(apply_fn(f, x)), IOAction) else force(apply_fn(f, x)) for x in force(xs)], "mapM_"),
        "mapM_"), "mapM_", 2),
    "return":    _b(lambda x: IOAction(lambda: force(x), "return"), "return"),
    "pure":      _b(lambda x: IOAction(lambda: force(x), "pure"), "pure"),
    "id":        _b(lambda x: force(x), "id"),
    "const":     _b(lambda a: _b(lambda _b, a=a: force(a), "const"), "const", 2),
    "firstJust": _b(lambda xs: next(
        (x for x in force(xs) if isinstance(force(x), Constructor) and force(x).name == "Just"),
        Constructor("Nothing", 0)), "firstJust"),
    "isPrime":   _b(lambda n: _is_prime(force(n)), "isPrime"),
}


def _is_prime(n: int) -> bool:
    n = abs(int(n))
    if n < 2: return False
    if n == 2: return True
    if n % 2 == 0: return False
    for i in range(3, int(n**0.5)+1, 2):
        if n % i == 0: return False
    return True


# ── Streams module ────────────────────────────────────────────────────────────

STREAMS: dict = {
    # Constructors
    "from":       _b(lambda n: from_n(force(n)), "from"),
    "fromStep":   _b(lambda n: _b(lambda s, n=n: from_n(force(n), force(s)), "fromStep"), "fromStep", 2),
    "repeat":     _b(lambda x: repeat(force(x)), "repeat"),
    "iterate":    _b(lambda f: _b(lambda x, f=f: iterate(lambda v: force(apply_fn(f, v)), force(x)), "iterate"), "iterate", 2),
    "cycle":      _b(lambda xs: cycle(force(xs)), "cycle"),
    "unfold":     _b(lambda f: _b(lambda s, f=f:
        unfold(lambda seed: (lambda r: (force(r)[0], force(r)[1]))(apply_fn(f, seed)), force(s)), "unfold"), "unfold", 2),

    # The demand operator
    "demand":     _b(lambda s: _b(lambda n, s=s: demand(force(s), force(n)), "demand"), "demand", 2),

    # Consuming
    "take":       _b(lambda n: _b(lambda s, n=n: take(force(n), force(s)), "take"), "take", 2),
    "drop":       _b(lambda n: _b(lambda s, n=n: drop(force(n), force(s)), "drop"), "drop", 2),
    "takeWhile":  _b(lambda p: _b(lambda s, p=p: take_while(lambda x: force(apply_fn(p, x)), force(s)), "takeWhile"), "takeWhile", 2),
    "dropWhile":  _b(lambda p: _b(lambda s, p=p: drop_while(lambda x: force(apply_fn(p, x)), force(s)), "dropWhile"), "dropWhile", 2),
    "firstWhere": _b(lambda p: _b(lambda s, p=p: first_where(lambda x: force(apply_fn(p, x)), force(s)), "firstWhere"), "firstWhere", 2),

    # Transforming
    "smap":       _b(lambda f: _b(lambda s, f=f: smap(lambda x: force(apply_fn(f, x)), force(s)), "smap"), "smap", 2),
    "sfilter":    _b(lambda p: _b(lambda s, p=p: sfilter(lambda x: force(apply_fn(p, x)), force(s)), "sfilter"), "sfilter", 2),
    "zipWith":    _b(lambda f: _b(lambda a: _b(lambda b, f=f, a=a:
        zip_with(lambda x,y: force(apply_fn(apply_fn(f,x),y)), force(a), force(b)), "szipWith"), "szipWith"), "zipWith", 3),
    "szip":       _b(lambda a: _b(lambda b, a=a: szip(force(a), force(b)), "szip"), "szip", 2),
    "scan":       _b(lambda f: _b(lambda z: _b(lambda s, f=f, z=z:
        scan(lambda acc,x: force(apply_fn(apply_fn(f,acc),x)), force(z), force(s)), "scan"), "scan"), "scan", 3),
    "interleave": _b(lambda a: _b(lambda b, a=a: interleave(force(a), force(b)), "interleave"), "interleave", 2),
    "merge":      _b(lambda a: _b(lambda b, a=a: merge_sorted(force(a), force(b)), "merge"), "merge", 2),
    "chunk":      _b(lambda n: _b(lambda s, n=n: chunk(force(n), force(s)), "chunk"), "chunk", 2),
    "window":     _b(lambda n: _b(lambda s, n=n: window(force(n), force(s)), "window"), "window", 2),
    "flatten":    _b(lambda s: flatten(force(s)), "flatten"),
    "nth":        _b(lambda n: _b(lambda s, n=n: nth(force(s), force(n)), "nth"), "nth", 2),

    # Info
    "shead":  _b(lambda s: force(s).head, "shead"),
    "stail":  _b(lambda s: force(s).tail, "stail"),
    "isEmpty":_b(lambda s: isinstance(force(s), Empty), "isEmpty"),

    # Classic infinite streams (pre-built)
    "primes":   _primes(),
    "fibs":     _fibs(),
    "naturals": from_n(0),
    "ones":     repeat(1),
    "zeros":    repeat(0),
    "pi":       pi_digits(),
}


# ── Math module ───────────────────────────────────────────────────────────────

MATH: dict = {
    "pi":        pi_digits(),
    "piFloat":   math.pi,
    "e":         math.e,
    "primes":    _primes(),
    "fibs":      _fibs(),
    "naturals":  from_n(0),
    "sqrt":      _b(lambda x: math.sqrt(force(x)), "sqrt"),
    "log":       _b(lambda x: math.log(force(x)), "log"),
    "log2":      _b(lambda x: math.log2(force(x)), "log2"),
    "log10":     _b(lambda x: math.log10(force(x)), "log10"),
    "exp":       _b(lambda x: math.exp(force(x)), "exp"),
    "sin":       _b(lambda x: math.sin(force(x)), "sin"),
    "cos":       _b(lambda x: math.cos(force(x)), "cos"),
    "tan":       _b(lambda x: math.tan(force(x)), "tan"),
    "atan2":     _b(lambda y: _b(lambda x,y=y: math.atan2(force(y),force(x)), "atan2"), "atan2", 2),
    "gcd":       _b(lambda a: _b(lambda b,a=a: math.gcd(int(force(a)),int(force(b))), "gcd"), "gcd", 2),
    "lcm":       _b(lambda a: _b(lambda b,a=a: math.lcm(int(force(a)),int(force(b))), "lcm"), "lcm", 2),
    "factorial": _b(lambda n: math.factorial(int(force(n))), "factorial"),
    "choose":    _b(lambda n: _b(lambda k,n=n: math.comb(force(n),force(k)), "choose"), "choose", 2),
    "isPrime":   _b(lambda n: _is_prime(force(n)), "isPrime"),
    "fraction":  _b(lambda n: _b(lambda d,n=n: Fraction(force(n),force(d)), "fraction"), "fraction", 2),

    # Signal processing
    "movingAvg": _b(lambda n: _b(lambda data, n=n: _moving_avg(force(data), force(n)), "movingAvg"), "movingAvg", 2),
    "fft":       _b(lambda data: _fft(force(data)), "fft"),
    "ifft":      _b(lambda coeffs: _ifft(force(coeffs)), "ifft"),
    "correlate": _b(lambda a: _b(lambda b, a=a: _correlate(force(a), force(b)), "correlate"), "correlate", 2),
}


def _moving_avg(data: list, n: int) -> list:
    result = []
    for i in range(len(data) - n + 1):
        result.append(sum(data[i:i+n]) / n)
    return result

def _fft(data: list) -> list:
    try:
        import numpy as np
        return list(np.fft.rfft(data))
    except ImportError:
        return data  # fallback

def _ifft(coeffs: list) -> list:
    try:
        import numpy as np
        return list(np.fft.irfft(coeffs))
    except ImportError:
        return coeffs


def _correlate(a: list, b: list) -> list:
    n = len(a)
    return [sum(a[i] * b[(i + lag) % n] for i in range(n)) / n
            for lag in range(n)]


# ── IO module ─────────────────────────────────────────────────────────────────

IO: dict = {
    "print":     _b(lambda x: IOAction(lambda: print(_show(force(x))), "print"), "print"),
    "putStr":    _b(lambda s: IOAction(lambda: print(force(s), end=""), "putStr"), "putStr"),
    "readLine":  IOAction(lambda: input(), "readLine"),
    "readFile":  _b(lambda p: IOAction(lambda: open(force(p)).read(), "readFile"), "readFile"),
    "writeFile": _b(lambda p: _b(lambda c, p=p: IOAction(lambda: open(force(p),"w").write(force(c)), "writeFile"), "writeFile"), "writeFile", 2),
    "appendFile":_b(lambda p: _b(lambda c, p=p: IOAction(lambda: open(force(p),"a").write(force(c)), "appendFile"), "appendFile"), "appendFile", 2),
    "fileExists":_b(lambda p: IOAction(lambda: os.path.exists(force(p)), "fileExists"), "fileExists"),
    "listDir":   _b(lambda p: IOAction(lambda: os.listdir(force(p)), "listDir"), "listDir"),
    "now":       IOAction(lambda: time.time(), "now"),
    "sleep":     _b(lambda s: IOAction(lambda: time.sleep(force(s)), "sleep"), "sleep"),
    "pure":      _b(lambda x: IOAction(lambda: force(x), "pure"), "pure"),
    "return":    _b(lambda x: IOAction(lambda: force(x), "return"), "return"),
}


# ── Crypto module ─────────────────────────────────────────────────────────────

def _hash_chain(seed: str):
    def go(s: str):
        nxt = hashlib.sha256(s.encode()).hexdigest()
        return cons(s, Thunk(lambda: go(nxt)))
    return go(force(seed))

CRYPTO: dict = {
    "entropy":       IOAction(lambda: _entropy_stream(), "entropy"),
    "randomBytes":   _b(lambda n: IOAction(lambda: secrets.token_bytes(force(n)), "randomBytes"), "randomBytes"),
    "randomInt":     _b(lambda lo: _b(lambda hi,lo=lo: IOAction(lambda: secrets.randbelow(force(hi)-force(lo))+force(lo), "randomInt"), "randomInt"), "randomInt", 2),
    "sha256":        _b(lambda x: hashlib.sha256(force(x).encode() if isinstance(force(x),str) else force(x)).hexdigest(), "sha256"),
    "sha512":        _b(lambda x: hashlib.sha512(force(x).encode() if isinstance(force(x),str) else force(x)).hexdigest(), "sha512"),
    "hashChain":     _b(_hash_chain, "hashChain"),
    "hmac":          _b(lambda k: _b(lambda m,k=k: __import__("hmac").new(force(k).encode(),force(m).encode(),"sha256").hexdigest(), "hmac"), "hmac", 2),
    "secureToken":   _b(lambda n: IOAction(lambda: secrets.token_hex(force(n)), "secureToken"), "secureToken"),
    "secureCompare": _b(lambda a: _b(lambda b,a=a: secrets.compare_digest(force(a),force(b)), "secureCompare"), "secureCompare", 2),
}

def _entropy_stream():
    def go():
        ch = secrets.token_bytes(64)
        def build(i):
            return EMPTY if i >= len(ch) else cons(ch[i], Thunk(lambda i=i: build(i+1)))
        return build(0)
    return go()


# ── Concurrent module ─────────────────────────────────────────────────────────

def _par(a, b):
    res, errs = [None,None], [None,None]
    def ra(): 
        try: res[0] = force(a)
        except Exception as e: errs[0] = e
    def rb(): 
        try: res[1] = force(b)
        except Exception as e: errs[1] = e
    t1, t2 = threading.Thread(target=ra), threading.Thread(target=rb)
    t1.start(); t2.start(); t1.join(); t2.join()
    if errs[0]: raise errs[0]
    if errs[1]: raise errs[1]
    return (res[0], res[1])

CONCURRENT: dict = {
    "par":       _b(lambda a: _b(lambda b,a=a: _par(a,b), "par"), "par", 2),
    "parMap":    _b(lambda f: _b(lambda xs,f=f:
        [force(apply_fn(f,x)) for x in
         __import__("concurrent.futures",fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor().map(
             lambda x,f=f: force(apply_fn(f,x)), force(xs))], "parMap"), "parMap", 2),
    "fork":      _b(lambda a: IOAction(lambda:
        threading.Thread(target=lambda: force(a).run() if isinstance(force(a),IOAction) else force(a), daemon=True).start(), "fork"), "fork"),
    "newChannel":IOAction(lambda: _new_channel(), "newChannel"),
}

def _new_channel():
    q = _queue.Queue()
    return {
        "send":       _b(lambda x: IOAction(lambda: q.put(force(x)), "send"), "send"),
        "receive":    IOAction(lambda: q.get(), "receive"),
        "tryReceive": IOAction(lambda: _just(q.get_nowait()) if not q.empty() else _nothing(), "tryReceive"),
    }


# ── Sources module ────────────────────────────────────────────────────────────

SOURCES: dict = {
    "openSDSS":  _b(lambda t: SDSSSource(obj_type=force(t)).stream(), "openSDSS"),
    "openJWST":  _b(lambda i: JWSTSource(instrument=force(i)).stream(), "openJWST"),
    "openLIGO":  LIGOSource().stream(),
    "openGAIA":  GAIASource().stream(),
    "openFile":  _b(lambda p: FileSource(force(p)).stream(), "openFile"),
    "openCSV":   _b(lambda p: CSVSource(force(p)).stream(), "openCSV"),
    "mockSpectra": MockSpectralSource().stream(),
    "openSource":  _b(lambda name: _b(lambda kw, name=name: open_source(force(name), **force(kw)), "openSource"), "openSource", 2),
}


# ── Compress module ────────────────────────────────────────────────────────────

COMPRESS: dict = {
    "FourierN":          _b(lambda n: FourierN(force(n)), "FourierN"),
    "PolynomialN":       _b(lambda n: PolynomialN(force(n)), "PolynomialN"),
    "BlackbodySpectrum": BlackbodySpectrum(),
    "GaussianMixture":   _b(lambda k: GaussianMixture(force(k)), "GaussianMixture"),
    "DeltaChain":        DeltaChain(),
    "WaveletModel":      _b(lambda f: WaveletModel(force(f)), "WaveletModel"),
    "auto":              _b(lambda data: auto_compress(force(data)), "auto"),
    "fit":               _b(lambda model: _b(lambda data, model=model:
        force(model).fit(force(data) if isinstance(force(data), list) else list(force(data))), "fit"), "fit", 2),
    "decode":            _b(lambda model: _b(lambda n, model=model: force(model).decode(force(n)), "decode"), "decode", 2),
    "ratio":             _b(lambda model: _b(lambda n, model=model: force(model).compression_ratio(force(n)), "ratio"), "ratio", 2),
    "paramBytes":        _b(lambda model: force(model).parameter_bytes(), "paramBytes"),
    "newArchive":        _b(lambda name: _b(lambda model_type, name=name:
        SymbolicArchive(force(name), eval(force(model_type))), "newArchive"), "newArchive", 2),
}
