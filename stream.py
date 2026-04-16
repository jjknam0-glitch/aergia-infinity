"""
aergia.stream
~~~~~~~~~~~~~
Infinite lazy streams — the primary data structure of Æergia∞.

The ~> demand operator is what makes Æergia∞ unique:

    primes ~> 10             -- materialise first 10 primes
    sdss   ~> 100            -- fetch exactly 100 records from SDSS
    fibs   ~> (> 1_000_000)  -- first Fibonacci > 1 million

A Stream is a codata type with exactly two observations:
    head : ∞T -> T
    tail : ∞T -> ∞T

The tail is always a Thunk, so infinite Streams live in O(1) space for
their definition. Forced elements are memoised automatically.
"""
from __future__ import annotations
from typing import Any, Callable, Iterator, Optional
from .thunk import Thunk, force


# ── Core types ─────────────────────────────────────────────────────────────

class Stream:
    """
    A lazy, potentially-infinite sequence.  Type: ∞T in Æergia∞ source.

    Never construct directly — use cons(), from_n(), repeat(), etc.
    """
    __slots__ = ("_head", "_tail_thunk", "_memo")

    def __init__(self, head: Any, tail_thunk: Thunk) -> None:
        self._head        = head
        self._tail_thunk  = tail_thunk
        self._memo: Optional["Stream | Empty"] = None

    @property
    def head(self) -> Any:
        return force(self._head)

    @property
    def tail(self) -> "Stream | Empty":
        if self._memo is None:
            t = force(self._tail_thunk)
            if not isinstance(t, (Stream, Empty)):
                raise TypeError(
                    f"Stream tail must be Stream or Empty, got {type(t).__name__}"
                )
            self._memo = t
        return self._memo

    # -- demand operator -----------------------------------------------
    def __matmul__(self, spec: Any) -> Any:
        """s ~> spec  (written as s @ spec internally)."""
        return demand(self, spec)

    def __iter__(self) -> Iterator[Any]:
        s: Any = self
        while isinstance(s, Stream):
            yield s.head
            s = s.tail

    def __getitem__(self, n: int) -> Any:
        return nth(self, n)

    def __repr__(self) -> str:
        items: list[str] = []
        s: Any = self
        for _ in range(8):
            if isinstance(s, Empty):
                return "[" + ", ".join(items) + "]"
            items.append(repr(s.head))
            try:
                s = s.tail
            except Exception:
                break
        return "[" + ", ".join(items) + ", ∞]"


class Empty(Stream):
    """The terminal empty stream singleton."""
    _inst: Optional["Empty"] = None

    def __new__(cls) -> "Empty":
        if cls._inst is None:
            cls._inst = object.__new__(cls)
        return cls._inst

    def __init__(self) -> None: pass

    @property
    def head(self) -> Any:
        raise IndexError("head of empty stream")

    @property
    def tail(self) -> "Empty":
        raise IndexError("tail of empty stream")

    def __iter__(self) -> Iterator[Any]:
        return iter([])

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "[]"


EMPTY: Empty = Empty()


# ── Demand operator ─────────────────────────────────────────────────────────

def demand(s: Any, spec: Any) -> Any:
    """
    The Æergia∞ demand operator: stream ~> spec

    spec may be:
      int           →  first n elements as a list
      callable      →  first element satisfying predicate
      slice         →  slice of elements as a list
      "first"/"any" →  the single head element
      None          →  the stream itself (identity, no evaluation)
    """
    s = force(s)
    if spec is None:
        return s
    if isinstance(spec, int):
        return take(spec, s)
    if isinstance(spec, str):
        if spec in ("first", "one", "any"):
            if isinstance(s, Empty):
                raise IndexError("demand 'first' on empty stream")
            return s.head
        raise ValueError(f"Unknown demand string spec: {spec!r}")
    if isinstance(spec, slice):
        start = spec.start or 0
        stop  = spec.stop
        step  = spec.step  or 1
        s     = drop(start, s)
        if stop is None:
            return s
        n = max(0, (stop - start + step - 1) // step)
        return take(n, s)
    if callable(spec):
        return first_where(spec, s)
    raise TypeError(f"Invalid demand spec: {type(spec).__name__!r} {spec!r}")


# ── Constructors ────────────────────────────────────────────────────────────

def cons(head: Any, tail: Any) -> Stream:
    """Build a Stream cell. tail may be Thunk, Stream, or zero-arg callable."""
    if callable(tail) and not isinstance(tail, (Stream, Thunk)):
        tail = Thunk(tail)
    elif not isinstance(tail, Thunk):
        t = tail
        tail = Thunk(lambda t=t: t)
    return Stream(head, tail)


def from_list(xs: list) -> "Stream | Empty":
    """Finite stream from a Python list."""
    def build(i: int) -> "Stream | Empty":
        if i >= len(xs):
            return EMPTY
        return cons(xs[i], Thunk(lambda i=i: build(i + 1)))
    return build(0)


def from_iter(it: Iterator) -> "Stream | Empty":
    """Lazily convert a Python iterator to a Stream."""
    try:
        x = next(it)
        return cons(x, Thunk(lambda: from_iter(it)))
    except StopIteration:
        return EMPTY


# ── Infinite constructors ───────────────────────────────────────────────────

def from_n(n: int, step: int = 1) -> Stream:
    """Integers from n upward: n, n+step, n+2*step, …"""
    return cons(n, Thunk(lambda: from_n(n + step, step)))


def repeat(x: Any) -> Stream:
    """Infinite constant stream: x, x, x, …"""
    def go() -> Stream:
        return cons(x, Thunk(go))
    return go()


def iterate(f: Callable, x: Any) -> Stream:
    """x, f(x), f(f(x)), … — infinite iteration of f."""
    return cons(x, Thunk(lambda: iterate(f, f(x))))


def cycle(xs: list) -> "Stream | Empty":
    """Repeat a finite list forever."""
    if not xs:
        return EMPTY
    def go(i: int) -> Stream:
        return cons(xs[i], Thunk(lambda: go((i + 1) % len(xs))))
    return go(0)


def unfold(f: Callable, seed: Any) -> Stream:
    """
    General stream producer. f(seed) must return (value, new_seed).

        nats = unfold (\\s -> (s, s + 1)) 0
    """
    val, ns = f(seed)
    return cons(val, Thunk(lambda: unfold(f, ns)))


def range_finite(start: int, stop: int, step: int = 1) -> "Stream | Empty":
    """[start..stop] — finite integer range stream."""
    if (step > 0 and start > stop) or (step < 0 and start < stop):
        return EMPTY
    return cons(start, Thunk(lambda: range_finite(start + step, stop, step)))


# ── Combinators ─────────────────────────────────────────────────────────────

def take(n: int, s: Any) -> list:
    """Materialise first n elements as a Python list. Safe on infinite streams."""
    result: list = []
    s = force(s)
    while n > 0 and isinstance(s, Stream) and not isinstance(s, Empty):
        result.append(s.head)
        s = force(s.tail)
        n -= 1
    return result


def drop(n: int, s: Any) -> "Stream | Empty":
    """Skip first n elements."""
    s = force(s)
    for _ in range(n):
        if not isinstance(s, Stream) or isinstance(s, Empty):
            return EMPTY
        s = force(s.tail)
    return s


def nth(s: Any, n: int) -> Any:
    """0-indexed element access — forces n+1 elements."""
    if n < 0:
        raise IndexError("Stream indices must be non-negative")
    s = drop(n, s)
    if isinstance(s, Empty):
        raise IndexError(f"Stream index {n} out of range")
    return force(s).head


def take_while(pred: Callable, s: Any) -> list:
    """Collect elements while pred holds."""
    result: list = []
    s = force(s)
    while isinstance(s, Stream) and not isinstance(s, Empty):
        h = s.head
        if not pred(h):
            break
        result.append(h)
        s = force(s.tail)
    return result


def drop_while(pred: Callable, s: Any) -> "Stream | Empty":
    """Skip elements while pred holds."""
    s = force(s)
    while isinstance(s, Stream) and not isinstance(s, Empty):
        if not pred(s.head):
            return s
        s = force(s.tail)
    return EMPTY


def first_where(pred: Callable, s: Any) -> Any:
    """Return the first element satisfying pred."""
    s = force(s)
    while isinstance(s, Stream) and not isinstance(s, Empty):
        h = s.head
        if pred(h):
            return h
        s = force(s.tail)
    raise ValueError("No element in stream satisfies the predicate")


def smap(f: Callable, s: Any) -> "Stream | Empty":
    """Lazy map — applies f to every element without materialising."""
    s = force(s)
    if isinstance(s, Empty):
        return EMPTY
    return cons(f(s.head), Thunk(lambda s=s: smap(f, s.tail)))


def sfilter(pred: Callable, s: Any) -> "Stream | Empty":
    """
    Lazy filter. Non-matching elements are skipped iteratively to avoid
    deep Python recursion when many consecutive elements are rejected.
    """
    s = force(s)
    while isinstance(s, Stream) and not isinstance(s, Empty):
        if pred(s.head):
            h = s.head
            return cons(h, Thunk(lambda s=s: sfilter(pred, s.tail)))
        s = force(s.tail)
    return EMPTY


def zip_with(f: Callable, s1: Any, s2: Any) -> "Stream | Empty":
    """Combine two streams element-wise with f."""
    s1, s2 = force(s1), force(s2)
    if isinstance(s1, Empty) or isinstance(s2, Empty):
        return EMPTY
    return cons(
        f(s1.head, s2.head),
        Thunk(lambda: zip_with(f, s1.tail, s2.tail)),
    )


def szip(s1: Any, s2: Any) -> "Stream | Empty":
    """Pair elements: (a0,b0), (a1,b1), …"""
    return zip_with(lambda a, b: (a, b), s1, s2)


def scan(f: Callable, z: Any, s: Any) -> Stream:
    """
    Running accumulation (infinite fold).
    scan f z [a,b,c,…] = [z, f(z,a), f(f(z,a),b), …]
    """
    s = force(s)
    if isinstance(s, Empty):
        return cons(z, Thunk(lambda: EMPTY))
    acc = f(z, s.head)
    return cons(z, Thunk(lambda acc=acc, s=s: scan(f, acc, s.tail)))


def interleave(s1: Any, s2: Any) -> "Stream | Empty":
    """s1[0], s2[0], s1[1], s2[1], …"""
    s1 = force(s1)
    if isinstance(s1, Empty):
        return force(s2)
    return cons(s1.head, Thunk(lambda: interleave(s2, s1.tail)))


def merge_sorted(s1: Any, s2: Any) -> "Stream | Empty":
    """Merge two sorted streams."""
    s1, s2 = force(s1), force(s2)
    if isinstance(s1, Empty): return s2
    if isinstance(s2, Empty): return s1
    if s1.head <= s2.head:
        return cons(s1.head, Thunk(lambda: merge_sorted(s1.tail, s2)))
    return cons(s2.head, Thunk(lambda: merge_sorted(s1, s2.tail)))


def chunk(n: int, s: Any) -> "Stream | Empty":
    """Group elements into lists of size n."""
    if n <= 0:
        raise ValueError("chunk size must be positive")
    s = force(s)
    if isinstance(s, Empty):
        return EMPTY
    c = take(n, s)
    r = drop(n, s)
    return cons(c, Thunk(lambda: chunk(n, r)))


def window(n: int, s: Any) -> "Stream | Empty":
    """Sliding window of size n: [s0..sn-1], [s1..sn], …"""
    buf = take(n, s)
    if len(buf) < n:
        return EMPTY
    rest = drop(1, s)
    return cons(buf, Thunk(lambda: window(n, rest)))


def flatten(ss: Any) -> "Stream | Empty":
    """Flatten a stream of finite lists into a stream of elements."""
    ss = force(ss)
    if isinstance(ss, Empty):
        return EMPTY
    inner = force(ss.head)
    if isinstance(inner, list):
        if not inner:
            return flatten(ss.tail)
        return cons(inner[0], Thunk(lambda: _prepend(inner[1:], flatten(ss.tail))))
    return cons(inner, Thunk(lambda: flatten(ss.tail)))


def _prepend(xs: list, s: Any) -> "Stream | Empty":
    if not xs:
        return force(s)
    return cons(xs[0], Thunk(lambda: _prepend(xs[1:], s)))


# ── Numeric streams ─────────────────────────────────────────────────────────

def primes() -> Stream:
    """
    The infinite prime stream via the Sieve of Eratosthenes.
    Elements are memoised — the 1000th prime costs O(1) after first access.
    """
    def sieve(s: Stream) -> Stream:
        p = s.head
        return cons(
            p,
            Thunk(lambda: sieve(sfilter(lambda n: n % p != 0, s.tail))),
        )
    return sieve(from_n(2))


def fibs() -> Stream:
    """
    The Fibonacci stream, self-referentially defined.
    Runs in linear time thanks to memoisation.
    """
    cell: list = [None]

    def rest() -> Stream:
        return zip_with(lambda a, b: a + b, cell[0], cell[0].tail)

    s = cons(0, Thunk(lambda: cons(1, Thunk(rest))))
    cell[0] = s
    return s


def pi_digits() -> Stream:
    """
    Digits of π as an infinite stream, computed via Machin's formula
    with exact rational arithmetic — no floating-point rounding errors.
    """
    from decimal import Decimal, getcontext

    def arctan(x: Decimal, terms: int) -> Decimal:
        res, xsq, term = Decimal(0), x * x, x
        for k in range(terms):
            res += (term if k % 2 == 0 else -term) / (2 * k + 1)
            term *= xsq
        return res

    def chunk_at(offset: int, count: int) -> list[int]:
        prec = offset + count + 40
        getcontext().prec = prec
        pi = 4 * (4 * arctan(Decimal(1) / 5, 200)
                    - arctan(Decimal(1) / 239, 100))
        s = str(pi).replace(".", "").replace("-", "")
        return [int(c) for c in s[offset: offset + count] if c.isdigit()]

    def go(pos: int) -> Stream:
        digits = chunk_at(pos, 30)
        def build(i: int) -> "Stream | Empty":
            if i >= len(digits):
                return go(pos + 30)
            return cons(digits[i], Thunk(lambda i=i: build(i + 1)))
        return build(0)

    return go(0)
