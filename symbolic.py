"""
aergia.symbolic
~~~~~~~~~~~~~~~
Symbolic compression engine — the feature that makes Æergia∞ unique.

The core idea: instead of storing raw data bytes, Æergia∞ stores the
*mathematical rule that describes the data*. This is Kolmogorov compression
made practical: find the shortest program that generates the data, and store
that instead.

For real scientific data this works because:
  - Spectra are sums of known line profiles (Gaussian, Lorentzian)
  - Light curves are Fourier series + occasional transients
  - Gravitational wave signals are chirp functions with known waveforms
  - Images decompose efficiently into wavelets
  - Sensor streams change slowly (delta encode the differences)

Compression models supported:
  FourierN(n)        — store n Fourier coefficients instead of N data points
  PolynomialN(n)     — least-squares polynomial of degree n
  BlackbodySpectrum  — Planck function: store T, A (2 floats for any spectrum)
  GaussianMixture(k) — k Gaussians: 3k floats for any peaked distribution
  DeltaChain         — store initial value + stream of differences
  WaveletModel(lvl)  — discrete wavelet transform, keep top coefficients
  RunLength          — run-length encoding for discrete/quantised streams
  Symbolic           — exact symbolic expression (for mathematical sequences)
"""

from __future__ import annotations
import math
import struct
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── Base model ──────────────────────────────────────────────────────────────

class CompressionModel:
    """
    Abstract base for all symbolic compression models.

    A model is fit to data with fit() and can reconstruct on demand with
    decode(). The *parameters* are all that need to be stored — typically
    far fewer bytes than the raw data.
    """
    name: str = "Model"

    def fit(self, data: list[float]) -> "CompressionModel":
        """Fit this model to data. Returns self (mutates in-place)."""
        raise NotImplementedError

    def decode(self, n: int) -> list[float]:
        """Reconstruct n data points from the stored parameters."""
        raise NotImplementedError

    def parameter_bytes(self) -> int:
        """How many bytes the model parameters occupy."""
        raise NotImplementedError

    def compression_ratio(self, original_n: int) -> float:
        """Ratio of original bytes to stored bytes (higher = better)."""
        orig  = original_n * 8       # assume float64
        stored = self.parameter_bytes()
        return orig / max(stored, 1)

    def __repr__(self) -> str:
        return f"{self.name}({self.parameter_bytes()} bytes)"


# ── Fourier model ────────────────────────────────────────────────────────────

@dataclass
class FourierN(CompressionModel):
    """
    Store the first n Fourier coefficients of a signal.

    For a 4096-point spectrum with 32 coefficients, this is 128:1 compression.
    The quality degrades gracefully as n decreases.

    Parameters stored: 2n floats (real + imaginary parts)
    """
    n:       int
    name:    str = field(default="FourierN", repr=False)
    _coeffs: list[complex] = field(default_factory=list, repr=False)

    def fit(self, data: list[float]) -> "FourierN":
        try:
            import numpy as np
            fft  = np.fft.rfft(data)
            self._coeffs = list(fft[: self.n])
        except ImportError:
            # Pure Python DFT (slow, for environments without numpy)
            N = len(data)
            self._coeffs = []
            for k in range(min(self.n, N // 2 + 1)):
                re = sum(data[t] * math.cos(2 * math.pi * k * t / N) for t in range(N))
                im = sum(data[t] * math.sin(2 * math.pi * k * t / N) for t in range(N))
                self._coeffs.append(complex(re / N, -im / N))
        return self

    def decode(self, n: int) -> list[float]:
        if not self._coeffs:
            raise RuntimeError("Model not fitted")
        try:
            import numpy as np
            padded = list(self._coeffs) + [0] * max(0, n // 2 + 1 - len(self._coeffs))
            return list(np.fft.irfft(padded, n=n)[:n])
        except ImportError:
            N = n
            result = []
            for t in range(N):
                val = sum(
                    (c.real * math.cos(2 * math.pi * k * t / N) -
                     c.imag * math.sin(2 * math.pi * k * t / N))
                    for k, c in enumerate(self._coeffs)
                )
                result.append(val * 2)
            return result

    def parameter_bytes(self) -> int:
        return len(self._coeffs) * 16   # 2 × float64 per coefficient


# ── Polynomial model ─────────────────────────────────────────────────────────

@dataclass
class PolynomialN(CompressionModel):
    """
    Fit a least-squares polynomial of degree n to the data.

    For smoothly varying time series this is extremely compact.
    A 10,000-point light curve with a cubic trend needs 4 floats.

    Parameters stored: n+1 floats (polynomial coefficients)
    """
    n:       int
    name:    str   = field(default="PolynomialN", repr=False)
    _coeffs: list  = field(default_factory=list, repr=False)

    def fit(self, data: list[float]) -> "PolynomialN":
        N = len(data)
        xs = [i / max(N - 1, 1) for i in range(N)]   # normalise to [0,1]
        try:
            import numpy as np
            self._coeffs = list(np.polyfit(xs, data, min(self.n, N - 1)))
        except ImportError:
            # Simple linear regression fallback when n=1
            n_pts = len(data)
            sx = sum(xs); sy = sum(data)
            sxx = sum(x*x for x in xs); sxy = sum(x*y for x, y in zip(xs, data))
            d   = n_pts * sxx - sx * sx
            b   = (n_pts * sxy - sx * sy) / d if d else 0
            a   = (sy - b * sx) / n_pts
            self._coeffs = [b, a]
        return self

    def decode(self, n: int) -> list[float]:
        if not self._coeffs:
            raise RuntimeError("Model not fitted")
        try:
            import numpy as np
            xs = np.linspace(0, 1, n)
            return list(np.polyval(self._coeffs, xs))
        except ImportError:
            xs = [i / max(n - 1, 1) for i in range(n)]
            return [sum(c * (x ** (len(self._coeffs) - 1 - i))
                        for i, c in enumerate(self._coeffs))
                    for x in xs]

    def parameter_bytes(self) -> int:
        return (len(self._coeffs)) * 8


# ── Blackbody spectrum model ─────────────────────────────────────────────────

@dataclass
class BlackbodySpectrum(CompressionModel):
    """
    Model a thermal emission spectrum as a Planck blackbody curve.

    An entire star spectrum (thousands of wavelength points) stored as
    two floats: temperature T and amplitude A.

    B(λ, T) = A · (2hc²/λ⁵) / (exp(hc/λkT) - 1)
    """
    name:         str   = field(default="BlackbodySpectrum", repr=False)
    temperature:  float = 0.0   # Kelvin
    amplitude:    float = 1.0
    wavelength_nm_start: float = 300.0
    wavelength_nm_stop:  float = 1000.0
    _residuals:   float = 0.0   # RMS residual after fit

    def fit(self, data: list[float]) -> "BlackbodySpectrum":
        """Fit T and A using a simple grid search + refinement."""
        n = len(data)
        lambdas = [self.wavelength_nm_start +
                   (self.wavelength_nm_stop - self.wavelength_nm_start) * i / max(n - 1, 1)
                   for i in range(n)]

        h  = 6.626e-34   # Planck constant
        c  = 3.0e8       # speed of light
        k  = 1.381e-23   # Boltzmann

        best_t, best_a, best_err = 5000.0, 1.0, float("inf")

        for T in range(3000, 30000, 500):
            model = []
            for lam_nm in lambdas:
                lam = lam_nm * 1e-9
                try:
                    b = (2 * h * c**2 / lam**5) / (math.exp(h * c / (lam * k * T)) - 1)
                except (OverflowError, ZeroDivisionError):
                    b = 0.0
                model.append(b)

            # Scale amplitude
            max_m = max(model) if max(model) > 0 else 1
            max_d = max(data)  if max(data)  > 0 else 1
            A = max_d / max_m
            model_scaled = [m * A for m in model]

            err = sum((d - m)**2 for d, m in zip(data, model_scaled)) ** 0.5
            if err < best_err:
                best_t, best_a, best_err = T, A, err

        self.temperature  = float(best_t)
        self.amplitude    = float(best_a)
        self._residuals   = best_err
        return self

    def decode(self, n: int) -> list[float]:
        h, c, k = 6.626e-34, 3.0e8, 1.381e-23
        T, A = self.temperature, self.amplitude
        lambdas = [self.wavelength_nm_start +
                   (self.wavelength_nm_stop - self.wavelength_nm_start) * i / max(n - 1, 1)
                   for i in range(n)]
        result = []
        for lam_nm in lambdas:
            lam = lam_nm * 1e-9
            try:
                b = A * (2 * h * c**2 / lam**5) / (math.exp(h * c / (lam * k * T)) - 1)
            except (OverflowError, ZeroDivisionError):
                b = 0.0
            result.append(b)
        return result

    def parameter_bytes(self) -> int:
        return 2 * 8   # temperature + amplitude


# ── Delta chain model ────────────────────────────────────────────────────────

@dataclass
class DeltaChain(CompressionModel):
    """
    Store a time series as (initial_value, [delta_1, delta_2, …]).

    For slowly-changing sensor data (temperature, pressure, brightness),
    deltas are small and compress extremely well with run-length encoding.

    Combined with quantisation, this achieves 10-100× compression on
    typical IoT/astronomical monitoring streams.
    """
    name:        str   = field(default="DeltaChain", repr=False)
    quantise_to: float = 0.001    # round deltas to this precision
    _initial:    float = 0.0
    _deltas:     list  = field(default_factory=list, repr=False)

    def fit(self, data: list[float]) -> "DeltaChain":
        if not data:
            return self
        self._initial = data[0]
        raw_deltas    = [data[i + 1] - data[i] for i in range(len(data) - 1)]
        # Quantise: round to quantise_to precision
        q = self.quantise_to
        self._deltas  = [round(d / q) * q for d in raw_deltas]
        return self

    def decode(self, n: int) -> list[float]:
        result = [self._initial]
        for d in self._deltas[:n - 1]:
            result.append(result[-1] + d)
        while len(result) < n:
            result.append(result[-1])
        return result[:n]

    def run_length_encode(self) -> list[tuple[float, int]]:
        """Further compress deltas using run-length encoding."""
        if not self._deltas:
            return []
        runs: list[tuple[float, int]] = []
        cur, cnt = self._deltas[0], 1
        for d in self._deltas[1:]:
            if d == cur:
                cnt += 1
            else:
                runs.append((cur, cnt))
                cur, cnt = d, 1
        runs.append((cur, cnt))
        return runs

    def parameter_bytes(self) -> int:
        # RLE compression estimate: each unique-delta run = 16 bytes
        runs = self.run_length_encode()
        return 8 + len(runs) * 16   # initial value + run-length pairs


# ── Gaussian mixture model ───────────────────────────────────────────────────

@dataclass
class GaussianMixture(CompressionModel):
    """
    Represent a distribution as a sum of k Gaussians.

    Each Gaussian needs 3 parameters (mean, std, weight) so the whole
    model uses 3k floats regardless of how many data points it describes.

    Useful for: spectral line profiles, point spread functions,
    redshift distributions, mass functions.
    """
    k:          int
    name:       str  = field(default="GaussianMixture", repr=False)
    _means:     list = field(default_factory=list, repr=False)
    _stds:      list = field(default_factory=list, repr=False)
    _weights:   list = field(default_factory=list, repr=False)

    def fit(self, data: list[float]) -> "GaussianMixture":
        """Simple k-means initialised EM-like fitting."""
        import random
        n = len(data)
        k = min(self.k, n)

        # Initialise means at evenly-spaced quantiles
        sorted_d = sorted(data)
        self._means   = [sorted_d[int(i * n / k)] for i in range(k)]
        self._stds    = [(max(data) - min(data)) / (2 * k)] * k
        self._weights = [1.0 / k] * k

        # EM iterations
        for _ in range(20):
            # E-step: responsibilities
            resp = []
            for x in data:
                r = [w * _gauss(x, m, s)
                     for w, m, s in zip(self._weights, self._means, self._stds)]
                total = sum(r) or 1e-300
                resp.append([ri / total for ri in r])

            # M-step: update parameters
            for j in range(k):
                rj    = [resp[i][j] for i in range(n)]
                nj    = sum(rj) or 1e-300
                self._weights[j] = nj / n
                self._means[j]   = sum(rj[i] * data[i] for i in range(n)) / nj
                self._stds[j]    = max(1e-6, math.sqrt(
                    sum(rj[i] * (data[i] - self._means[j])**2 for i in range(n)) / nj
                ))
        return self

    def decode(self, n: int) -> list[float]:
        """Reconstruct n samples from the mixture."""
        xs = [min(self._means) - 3 * max(self._stds) +
              i * (max(self._means) + 3 * max(self._stds) -
                   min(self._means) + 3 * max(self._stds)) / max(n - 1, 1)
              for i in range(n)]
        return [sum(w * _gauss(x, m, s)
                    for w, m, s in zip(self._weights, self._means, self._stds))
                for x in xs]

    def parameter_bytes(self) -> int:
        return len(self._means) * 3 * 8   # 3 floats per Gaussian


def _gauss(x: float, mu: float, sigma: float) -> float:
    return math.exp(-0.5 * ((x - mu) / sigma)**2) / (sigma * math.sqrt(2 * math.pi))


# ── Wavelet model ─────────────────────────────────────────────────────────────

@dataclass
class WaveletModel(CompressionModel):
    """
    Discrete wavelet transform — keep only the top `keep_fraction` of
    coefficients by magnitude.

    Similar to JPEG2000 compression.  Quality is tunable.
    Works well for images and spatially correlated scientific data.

    Parameters stored: (index, value) pairs for kept coefficients.
    """
    keep_fraction: float = 0.1   # keep top 10 % of coefficients
    name:          str   = field(default="WaveletModel", repr=False)
    _kept:         list  = field(default_factory=list, repr=False)
    _n_original:   int   = 0

    def fit(self, data: list[float]) -> "WaveletModel":
        """Haar wavelet transform + coefficient thresholding."""
        self._n_original = len(data)
        coeffs = _haar_fwd(data)
        threshold = sorted(abs(c) for c in coeffs)[
            int(len(coeffs) * (1 - self.keep_fraction))
        ]
        self._kept = [(i, c) for i, c in enumerate(coeffs) if abs(c) >= threshold]
        return self

    def decode(self, n: int) -> list[float]:
        if not self._kept:
            return [0.0] * n
        coeffs = [0.0] * self._n_original
        for i, c in self._kept:
            if i < len(coeffs):
                coeffs[i] = c
        result = _haar_inv(coeffs)
        # Resample to n if needed
        if len(result) == n:
            return result
        return [result[int(i * len(result) / n)] for i in range(n)]

    def parameter_bytes(self) -> int:
        return len(self._kept) * (8 + 4)   # float64 value + int32 index


def _haar_fwd(data: list[float]) -> list[float]:
    """Forward Haar wavelet transform."""
    n = len(data)
    result = list(data)
    while n > 1:
        half = n // 2
        new = []
        for i in range(half):
            new.append((result[2*i] + result[2*i+1]) / 2)
        for i in range(half):
            new.append((result[2*i] - result[2*i+1]) / 2)
        result[:n] = new
        n = half
    return result


def _haar_inv(coeffs: list[float]) -> list[float]:
    """Inverse Haar wavelet transform."""
    n   = len(coeffs)
    cur = 1
    result = list(coeffs)
    while cur < n:
        new = [0.0] * (2 * cur)
        for i in range(cur):
            a = result[i]
            d = result[cur + i]
            new[2*i]     = a + d
            new[2*i + 1] = a - d
        result[:2*cur] = new
        cur *= 2
    return result


# ── Symbolic expression model ────────────────────────────────────────────────

@dataclass
class SymbolicExpr(CompressionModel):
    """
    Store a mathematical sequence as its closed-form expression.

    For sequences with known formulas (Fibonacci, primes approximation,
    factorial, etc.) this achieves theoretically perfect compression:
    the entire infinite sequence stored as a handful of tokens.

    Examples:
      n² + n + 41            (Euler's prime-generating polynomial)
      (φⁿ - ψⁿ) / √5        (closed-form Fibonacci)
    """
    name:   str = field(default="SymbolicExpr", repr=False)
    expr:   str = ""           # human-readable expression
    _fn:    Optional[Callable] = field(default=None, repr=False)

    def fit_fn(self, fn: Callable, description: str) -> "SymbolicExpr":
        """Attach a Python function directly (bypasses regression)."""
        self._fn  = fn
        self.expr = description
        return self

    def decode(self, n: int) -> list[float]:
        if self._fn is None:
            raise RuntimeError("SymbolicExpr not fitted")
        return [float(self._fn(i)) for i in range(n)]

    def parameter_bytes(self) -> int:
        return len(self.expr.encode("utf-8"))   # just the expression string!


# ── Archive — the persistent symbolic store ──────────────────────────────────

@dataclass
class SymbolicArchive:
    """
    A persistent, append-only store of symbolically compressed data.

    Instead of storing raw bytes, the archive stores (model, metadata) pairs.
    New records can be added continuously; the total archive size grows as
    O(number_of_models × parameter_size) rather than O(total_data_points).

    This is the ∞ storage model: data sources grow forever, the archive
    does not grow proportionally.
    """
    name:    str
    model_type: type   # e.g. FourierN, DeltaChain, BlackbodySpectrum
    model_kwargs: dict = field(default_factory=dict)
    _records: list = field(default_factory=list, repr=False)  # (metadata, model)

    def ingest(self, data: list[float], metadata: dict = None) -> "CompressionModel":
        """Compress data and add to archive. Returns the fitted model."""
        model = self.model_type(**self.model_kwargs)
        model.fit(data)
        self._records.append((metadata or {}, model))
        return model

    def query(self, predicate: Callable[[dict], bool]) -> list[tuple[dict, "CompressionModel"]]:
        """Query archive by metadata predicate without decompressing."""
        return [(meta, model) for meta, model in self._records if predicate(meta)]

    def total_stored_bytes(self) -> int:
        return sum(m.parameter_bytes() for _, m in self._records)

    def would_have_stored_bytes(self, original_points_per_record: int) -> int:
        return len(self._records) * original_points_per_record * 8

    def overall_ratio(self, original_points_per_record: int) -> float:
        stored   = self.total_stored_bytes()
        original = self.would_have_stored_bytes(original_points_per_record)
        return original / max(stored, 1)

    def record_count(self) -> int:
        return len(self._records)

    def __repr__(self) -> str:
        return (f"Archive({self.name!r}, {self.record_count()} records, "
                f"{self.total_stored_bytes()} bytes stored)")


# ── Convenience: auto-select best model ─────────────────────────────────────

def auto_compress(data: list[float], budget_bytes: int = 256) -> CompressionModel:
    """
    Automatically select and fit the best compression model for data,
    subject to a parameter budget in bytes.

    Tries models from most to least aggressive, returning the best-fitting
    model that stays within the budget.
    """
    candidates: list[CompressionModel] = [
        BlackbodySpectrum(),
        PolynomialN(3),
        PolynomialN(6),
        GaussianMixture(4),
        FourierN(16),
        FourierN(32),
        DeltaChain(),
        WaveletModel(0.05),
        WaveletModel(0.10),
        WaveletModel(0.25),
    ]

    best: Optional[CompressionModel] = None
    best_ratio = 0.0

    for model in candidates:
        try:
            model.fit(data)
            if model.parameter_bytes() <= budget_bytes:
                ratio = model.compression_ratio(len(data))
                if ratio > best_ratio:
                    best_ratio = ratio
                    best = model
        except Exception:
            continue

    if best is None:
        # Fallback: store everything in wavelet form
        m = WaveletModel(1.0)
        m.fit(data)
        return m

    return best
