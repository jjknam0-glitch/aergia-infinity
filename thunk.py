"""
aergia.thunk
~~~~~~~~~~~~
Memoised suspended computation — the atomic unit of Æergia∞'s runtime.

Every binding in Æergia∞ is a Thunk until it is observed. The runtime
never computes anything it doesn't have to. This is the foundation that
allows an Æergia∞ program to reference petabytes of astronomical data
without downloading a single byte — until a demand (~>) forces it.

Thunk lifecycle:
  PENDING  →  fn() called on first force()  →  FORCED (value cached)
                                             ↘  ERROR  (exception cached, re-raised)
"""
from __future__ import annotations
from typing import Any, Callable

_UNSET     = object()   # sentinel: not yet evaluated
_MAX_CHAIN = 2048       # max thunk-chain depth before error


class Thunk:
    """
    A lazy, memoised computation.

    In Æergia∞ source, the ~ prefix creates a thunk::

        ~expensive_computation   -- suspended, not yet run

    The ! prefix forces one::

        !suspended_value         -- demand the result now
    """

    __slots__ = ("_fn", "_val", "_done", "_exc")

    def __init__(self, fn: Callable[[], Any]) -> None:
        if not callable(fn):
            raise TypeError(f"Thunk requires callable, got {type(fn).__name__!r}")
        self._fn:   Callable[[], Any] | None = fn
        self._val:  Any  = _UNSET
        self._done: bool = False
        self._exc:  BaseException | None = None

    # ------------------------------------------------------------------ #

    def force(self) -> Any:
        """
        Evaluate and return the concrete value.
        Subsequent calls return the cached result in O(1).
        """
        if self._done:
            if self._exc is not None:
                raise self._exc
            return self._val

        fn = self._fn
        if fn is None:
            raise RuntimeError("Thunk in corrupt state — should never happen")

        try:
            result = fn()
            # Flatten chained thunks without recursion
            depth = 0
            while isinstance(result, Thunk):
                if depth > _MAX_CHAIN:
                    raise RecursionError(
                        "Thunk chain exceeded maximum depth. "
                        "Possible infinite loop in non-productive definition."
                    )
                if result._done:
                    if result._exc:
                        raise result._exc
                    result = result._val
                    break
                result = result._fn()   # type: ignore[misc]
                depth += 1
            self._val = result
        except BaseException as exc:
            self._exc  = exc
            self._done = True
            self._fn   = None
            raise
        else:
            self._done = True
            self._fn   = None   # release closure — GC can collect it
            return self._val

    def is_forced(self) -> bool:
        return self._done

    def peek(self) -> Any:
        """Return cached value without forcing. Raises if unevaluated."""
        if not self._done:
            raise RuntimeError("peek() on unevaluated Thunk")
        return self._val

    def map(self, f: Callable[[Any], Any]) -> "Thunk":
        """Return a new thunk applying f to this one's result."""
        return Thunk(lambda: f(self.force()))

    def __repr__(self) -> str:
        if not self._done:
            return "<~ pending>"
        if self._exc:
            return f"<~ error: {self._exc!r}>"
        return f"<~ = {self._val!r}>"


# ── Module-level helpers ───────────────────────────────────────────────────

def force(val: Any) -> Any:
    """
    Force val if it is a Thunk; return it unchanged otherwise.
    Safe to call on any value. This is the ! operator in Æergia∞.
    """
    while isinstance(val, Thunk):
        val = val.force()
    return val


def delay(fn: Callable[[], Any]) -> Thunk:
    """Suspend fn as a Thunk.  The ~ prefix operator in Æergia∞."""
    return Thunk(fn)


def strict(val: Any) -> Any:
    """
    Deeply force all nested Thunks in a structure.
    Use only for debugging — defeats the purpose of laziness.
    """
    val = force(val)
    if isinstance(val, (list, tuple)):
        return type(val)(strict(x) for x in val)
    if isinstance(val, dict):
        return {k: strict(v) for k, v in val.items()}
    return val
