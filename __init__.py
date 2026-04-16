"""
Æergia∞ — A lazy, symbolic, stream-oriented language for infinite data.

Named after Aergia (Greek spirit of idleness) and the ∞ operator:
  Infinite INPUT  — any data archive is a lazy stream
  Infinite STORAGE — symbolic compression stores rules, not bytes

Quick start:
    from aergia.stream import primes, take
    print(take(20, primes()))

    from aergia.repl import REPL
    REPL().run()
"""
__version__ = "0.1.0"
__author__  = "Æergia∞ Project"
__license__ = "MIT"

from .thunk  import Thunk, force, delay
from .stream import (Stream, Empty, EMPTY, cons, from_n, repeat,
                     take, drop, smap, sfilter, primes, fibs, demand)
from .symbolic import (FourierN, PolynomialN, BlackbodySpectrum,
                       DeltaChain, WaveletModel, auto_compress)
from .sources import open_source
from .repl    import REPL, run_script

__all__ = [
    "Thunk","force","delay",
    "Stream","Empty","EMPTY","cons","from_n","repeat",
    "take","drop","smap","sfilter","demand","primes","fibs",
    "FourierN","PolynomialN","BlackbodySpectrum","DeltaChain",
    "WaveletModel","auto_compress","open_source",
    "REPL","run_script","__version__",
]
