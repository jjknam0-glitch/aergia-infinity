"""
aergia.sources
~~~~~~~~~~~~~~
Data source adapters — the other half of the ∞ in Æergia∞.

Every source is an infinite lazy Stream. Nothing is downloaded until a
demand (~>) operator forces evaluation. The runtime then fetches exactly
the bytes needed to satisfy the demand, caches them, and suspends.

Supported sources:
  SDSS       — Sloan Digital Sky Survey (public API, no key needed)
  JWST       — James Webb Space Telescope (MAST archive)
  GAIA       — Gaia star catalogue (ESA)
  LIGO       — Gravitational wave open data (GWOSC)
  File       — Local files (lines, CSV, binary)
  HTTP       — Generic HTTP endpoints (JSON, CSV)
  Generator  — Python generators / callables
  Mock       — Deterministic mock data for testing

All sources implement the same interface: they are Streams of dicts,
where each dict is one "record" (spectrum, frame, event, row, etc.).
"""

from __future__ import annotations
import time
import json
import math
import random
from typing import Any, Callable, Iterator, Optional

from .thunk  import Thunk, force, delay
from .stream import Stream, Empty, EMPTY, cons, from_iter


# ── Base source ──────────────────────────────────────────────────────────────

class Source:
    """
    Abstract data source.  All sources are lazy Streams of records.
    """
    name: str = "Source"

    def stream(self) -> "Stream | Empty":
        """Return the infinite (or finite) lazy stream for this source."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"∞Source({self.name})"


# ── HTTP / JSON source ────────────────────────────────────────────────────────

class HTTPSource(Source):
    """
    Generic paginated HTTP source.

    Fetches pages lazily — only requests the next page when the previous
    one is exhausted.  Supports cursor-based and offset-based pagination.
    """

    def __init__(
        self,
        url_template: str,
        params: dict = None,
        page_size: int = 100,
        records_key: str = "records",
        next_key: str = "next",
        name: str = "HTTP",
    ) -> None:
        self.url_template = url_template
        self.params       = params or {}
        self.page_size    = page_size
        self.records_key  = records_key
        self.next_key     = next_key
        self.name         = name

    def _fetch_page(self, offset: int) -> tuple[list[dict], bool]:
        """Fetch one page. Returns (records, has_more)."""
        try:
            import requests
            p = {**self.params, "offset": offset, "limit": self.page_size}
            r = requests.get(self.url_template, params=p, timeout=30)
            r.raise_for_status()
            data = r.json()
            records  = data.get(self.records_key, [])
            has_more = bool(data.get(self.next_key) or len(records) == self.page_size)
            return records, has_more
        except Exception as e:
            return [], False

    def stream(self) -> "Stream | Empty":
        def go(offset: int) -> "Stream | Empty":
            records, has_more = self._fetch_page(offset)
            if not records:
                return EMPTY
            def build(i: int, records=records, offset=offset, has_more=has_more):
                if i >= len(records):
                    if not has_more:
                        return EMPTY
                    return go(offset + len(records))
                return cons(records[i], Thunk(lambda i=i: build(i + 1)))
            return build(0)
        return go(0)


# ── SDSS source ──────────────────────────────────────────────────────────────

class SDSSSource(Source):
    """
    Sloan Digital Sky Survey public SkyServer API.

    No API key required.  Returns lazy streams of galaxy/star/quasar
    records from the DR18 release.

    Supported object types: 'GALAXY', 'STAR', 'QSO'
    """

    API_BASE = "http://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch"

    COLUMNS = [
        "objID", "ra", "dec", "type", "u", "g", "r", "i", "z",
        "petroRad_r", "redshift", "run", "camcol", "field",
    ]

    def __init__(
        self,
        obj_type: str = "GALAXY",
        ra_min:  float = 0.0,
        ra_max:  float = 360.0,
        dec_min: float = -90.0,
        dec_max: float = 90.0,
        redshift_min: float = 0.0,
        redshift_max: float = 10.0,
        page_size: int = 200,
        live: bool = False,
    ) -> None:
        self.obj_type     = obj_type
        self.ra_min       = ra_min
        self.ra_max       = ra_max
        self.dec_min      = dec_min
        self.dec_max      = dec_max
        self.redshift_min = redshift_min
        self.redshift_max = redshift_max
        self.page_size    = page_size
        self.live         = live          # use real API if True
        self.name         = f"SDSS({obj_type})"

    def _sql(self, offset: int) -> str:
        cols = ", ".join(self.COLUMNS)
        return f"""
SELECT TOP {self.page_size} {cols}
FROM PhotoObj AS p
LEFT JOIN SpecObj AS s ON p.objID = s.bestObjID
WHERE p.type = 3
  AND p.ra  BETWEEN {self.ra_min} AND {self.ra_max}
  AND p.dec BETWEEN {self.dec_min} AND {self.dec_max}
ORDER BY p.objID
OFFSET {offset} ROWS
        """.strip()

    def _fetch_live(self, offset: int) -> list[dict]:
        """Fetch from the real SDSS SkyServer API."""
        try:
            import requests
            r = requests.get(
                self.API_BASE,
                params={"cmd": self._sql(offset), "format": "json"},
                timeout=30,
            )
            r.raise_for_status()
            rows = r.json()
            if isinstance(rows, list) and rows:
                return rows
            return []
        except Exception:
            return []

    def _fetch_mock(self, offset: int) -> list[dict]:
        """Deterministic mock SDSS records for offline use."""
        rng = random.Random(offset * 1337 + 42)
        records = []
        for i in range(self.page_size):
            idx = offset + i
            ra  = rng.uniform(self.ra_min, self.ra_max)
            dec = rng.uniform(self.dec_min, self.dec_max)
            z   = rng.uniform(self.redshift_min, self.redshift_max)
            records.append({
                "objID":      f"SDSS-{idx:012d}",
                "ra":         round(ra, 6),
                "dec":        round(dec, 6),
                "type":       self.obj_type,
                "u":          round(rng.gauss(22, 1.5), 3),
                "g":          round(rng.gauss(21, 1.2), 3),
                "r":          round(rng.gauss(20, 1.0), 3),
                "i":          round(rng.gauss(19.5, 0.9), 3),
                "z":          round(rng.gauss(19.0, 0.8), 3),
                "petroRad_r": round(abs(rng.gauss(3.0, 2.0)), 2),
                "redshift":   round(z, 5),
                "luminosity": round(10 ** rng.uniform(8, 12), 2),
            })
        return records

    def stream(self) -> "Stream | Empty":
        def go(offset: int) -> "Stream | Empty":
            fetch = self._fetch_live if self.live else self._fetch_mock
            records = fetch(offset)
            if not records:
                return EMPTY
            def build(i: int) -> "Stream | Empty":
                if i >= len(records):
                    return go(offset + len(records))
                return cons(records[i], Thunk(lambda i=i: build(i + 1)))
            return build(0)
        return go(0)


# ── JWST source ───────────────────────────────────────────────────────────────

class JWSTSource(Source):
    """
    James Webb Space Telescope image/spectrum stream.

    Uses the MAST (Mikulski Archive for Space Telescopes) API.
    Returns metadata records; pixel data is fetched only if explicitly
    requested (further lazy evaluation).
    """

    def __init__(
        self,
        instrument: str = "NIRCam",
        filters: list[str] = None,
        target: str = None,
        page_size: int = 50,
        live: bool = False,
    ) -> None:
        self.instrument = instrument
        self.filters    = filters or ["F090W", "F150W", "F200W"]
        self.target     = target
        self.page_size  = page_size
        self.live       = live
        self.name       = f"JWST({instrument})"

    def _fetch_mock(self, offset: int) -> list[dict]:
        rng = random.Random(offset * 9973 + 17)
        records = []
        for i in range(self.page_size):
            idx = offset + i
            records.append({
                "obsID":      f"JWST-{self.instrument}-{idx:08d}",
                "instrument": self.instrument,
                "filter":     rng.choice(self.filters),
                "ra":         round(rng.uniform(0, 360), 6),
                "dec":        round(rng.uniform(-90, 90), 6),
                "exptime":    round(rng.uniform(100, 10000), 1),
                "date_obs":   f"2023-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
                "width_px":   2048,
                "height_px":  2048,
                "file_size_mb": round(rng.uniform(50, 500), 1),
                # pixel_data is a lazy thunk — only fetched if demanded
                "pixel_data": delay(lambda idx=idx: self._mock_pixels(idx)),
            })
        return records

    def _mock_pixels(self, idx: int) -> list[list[float]]:
        """Generate a mock 64×64 image (simulating a JWST cutout)."""
        rng = random.Random(idx)
        size = 64
        return [
            [rng.gauss(100, 20) + 1000 * math.exp(
                -((i - 32)**2 + (j - 32)**2) / (2 * 8**2)
             ) for j in range(size)]
            for i in range(size)
        ]

    def stream(self) -> "Stream | Empty":
        def go(offset: int) -> "Stream | Empty":
            records = self._fetch_mock(offset)
            if not records:
                return EMPTY
            def build(i: int) -> "Stream | Empty":
                if i >= len(records):
                    return go(offset + len(records))
                return cons(records[i], Thunk(lambda i=i: build(i + 1)))
            return build(0)
        return go(0)


# ── LIGO gravitational wave source ────────────────────────────────────────────

class LIGOSource(Source):
    """
    LIGO Open Gravitational-wave Catalogue (GWOSC) stream.

    Returns event records from the public GWOSC API.
    Each record includes strain data metadata; the actual waveform
    strain timeseries is fetched lazily.
    """

    GWOSC_API = "https://gwosc.org/eventapi/json/allevents/"

    def __init__(self, live: bool = False, detector: str = "H1") -> None:
        self.live     = live
        self.detector = detector
        self.name     = f"LIGO({detector})"

    def _fetch_live(self) -> list[dict]:
        try:
            import requests
            r = requests.get(self.GWOSC_API, timeout=30)
            r.raise_for_status()
            data   = r.json()
            events = data.get("events", {})
            return [{"name": k, **v} for k, v in events.items()]
        except Exception:
            return []

    def _fetch_mock(self) -> list[dict]:
        rng = random.Random(1234)
        events = []
        for i in range(100):
            mass1 = rng.uniform(5, 80)
            mass2 = rng.uniform(5, mass1)
            events.append({
                "name":            f"GW{190101 + i * 17:06d}",
                "GPS":             1135136350 + i * 86400 * 7,
                "mass_1_source":   round(mass1, 2),
                "mass_2_source":   round(mass2, 2),
                "total_mass":      round(mass1 + mass2, 2),
                "chirp_mass":      round((mass1 * mass2)**0.6 / (mass1 + mass2)**0.2, 2),
                "luminosity_distance": round(rng.uniform(100, 5000), 0),
                "network_matched_filter_snr": round(rng.uniform(8, 30), 1),
                "far":             10 ** rng.uniform(-12, -5),
                "strain_data":     delay(lambda i=i: self._mock_strain(i)),
            })
        return events

    def _mock_strain(self, event_idx: int) -> dict:
        """Simulated gravitational wave strain timeseries."""
        rng     = random.Random(event_idx)
        n       = 4096
        dt      = 1 / 4096   # seconds
        t_merge = n // 2
        strain  = []
        for i in range(n):
            t        = (i - t_merge) * dt
            chirp_f  = 100 * (1 - abs(t) + 1e-6) ** (-3/8) if t < 0 else 0
            amplitude = 1e-21 * (1 - abs(t) + 1e-6) ** (-1/4) if t < 0 else 0
            signal   = amplitude * math.sin(2 * math.pi * chirp_f * t)
            noise    = rng.gauss(0, 1e-22)
            strain.append(signal + noise)
        return {
            "t_start": 1135136350 + event_idx * 86400,
            "dt":      dt,
            "n":       n,
            "detector": self.detector,
            "strain":  strain,
        }

    def stream(self) -> "Stream | Empty":
        records = self._fetch_live() if self.live else self._fetch_mock()
        return from_iter(iter(records))


# ── GAIA star catalogue source ────────────────────────────────────────────────

class GAIASource(Source):
    """
    ESA Gaia stellar catalogue stream.

    The Gaia DR3 catalogue contains 1.8 billion stars.  This source
    streams them lazily — requesting small pages from the Gaia archive
    only as demanded.
    """

    TAP_URL = "https://gea.esac.esa.int/tap-server/tap/sync"

    def __init__(
        self,
        mag_max: float = 15.0,
        ra_min:  float = 0.0,
        ra_max:  float = 360.0,
        page_size: int = 500,
        live: bool = False,
    ) -> None:
        self.mag_max   = mag_max
        self.ra_min    = ra_min
        self.ra_max    = ra_max
        self.page_size = page_size
        self.live      = live
        self.name      = "GAIA(DR3)"

    def _fetch_mock(self, offset: int) -> list[dict]:
        rng = random.Random(offset * 2311)
        records = []
        for i in range(self.page_size):
            idx = offset + i
            parallax = abs(rng.gauss(2.0, 5.0))   # mas
            distance = 1000 / parallax if parallax > 0 else 1e6  # parsec
            records.append({
                "source_id":       f"Gaia DR3 {idx:019d}",
                "ra":              round(rng.uniform(self.ra_min, self.ra_max), 8),
                "dec":             round(rng.gauss(0, 30), 8),
                "parallax":        round(parallax, 4),
                "parallax_error":  round(abs(rng.gauss(0.1, 0.05)), 4),
                "pmra":            round(rng.gauss(0, 10), 4),   # mas/yr
                "pmdec":           round(rng.gauss(0, 10), 4),
                "phot_g_mean_mag": round(rng.uniform(6, self.mag_max), 3),
                "bp_rp":           round(rng.gauss(1.0, 0.8), 3),
                "radial_velocity": round(rng.gauss(0, 30), 2) if rng.random() > 0.5 else None,
                "distance_pc":     round(min(distance, 1e6), 1),
            })
        return records

    def stream(self) -> "Stream | Empty":
        def go(offset: int) -> "Stream | Empty":
            records = self._fetch_mock(offset)
            if not records:
                return EMPTY
            def build(i: int) -> "Stream | Empty":
                if i >= len(records):
                    return go(offset + len(records))
                return cons(records[i], Thunk(lambda i=i: build(i + 1)))
            return build(0)
        return go(0)


# ── File source ────────────────────────────────────────────────────────────────

class FileSource(Source):
    """
    Lazy file reader.  Lines are read on demand, so a 500 GB log file
    can be treated as an infinite stream without loading it into memory.
    """

    def __init__(self, path: str, encoding: str = "utf-8", name: str = None) -> None:
        self.path     = path
        self.encoding = encoding
        self.name     = name or f"File({path!r})"

    def stream(self) -> "Stream | Empty":
        try:
            f  = open(self.path, "r", encoding=self.encoding)
            it = iter(f)
            return from_iter(map(str.rstrip, it))
        except FileNotFoundError:
            return EMPTY


class CSVSource(Source):
    """Lazy CSV reader — each row is a dict keyed by the header row."""

    def __init__(self, path: str, delimiter: str = ",", name: str = None) -> None:
        self.path      = path
        self.delimiter = delimiter
        self.name      = name or f"CSV({path!r})"

    def stream(self) -> "Stream | Empty":
        import csv
        try:
            f      = open(self.path, newline="", encoding="utf-8")
            reader = csv.DictReader(f, delimiter=self.delimiter)
            return from_iter(reader)
        except FileNotFoundError:
            return EMPTY


# ── Generator source ──────────────────────────────────────────────────────────

class GeneratorSource(Source):
    """Wrap any Python callable that returns an iterator."""

    def __init__(self, factory: Callable[[], Iterator], name: str = "Generator") -> None:
        self.factory = factory
        self.name    = name

    def stream(self) -> "Stream | Empty":
        return from_iter(self.factory())


# ── Mock / test source ────────────────────────────────────────────────────────

class MockSpectralSource(Source):
    """
    Infinite stream of synthetic spectra for testing the compression pipeline.

    Each spectrum is a Planck blackbody at a random temperature with
    added Gaussian noise and synthetic emission lines.
    """

    def __init__(
        self,
        n_wavelengths: int = 1024,
        seed: int = 42,
        noise_level: float = 0.02,
    ) -> None:
        self.n_wavelengths = n_wavelengths
        self.seed          = seed
        self.noise_level   = noise_level
        self.name          = "MockSpectral"

    def _make_spectrum(self, idx: int) -> dict:
        rng  = random.Random(self.seed + idx)
        T    = rng.uniform(3000, 30000)     # star temperature in K
        lams = [300 + 700 * i / (self.n_wavelengths - 1)
                for i in range(self.n_wavelengths)]
        h, c, k = 6.626e-34, 3e8, 1.381e-23
        flux = []
        for lam_nm in lams:
            lam = lam_nm * 1e-9
            try:
                b = (2 * h * c**2 / lam**5) / (math.exp(h * c / (lam * k * T)) - 1)
            except (OverflowError, ZeroDivisionError):
                b = 0.0
            noise = rng.gauss(0, self.noise_level * b) if b else 0
            flux.append(b + noise)

        # Add 2-4 emission lines
        n_lines = rng.randint(2, 4)
        for _ in range(n_lines):
            line_lam = rng.uniform(350, 950)
            strength = rng.uniform(0.1, 0.5) * max(flux)
            width    = rng.uniform(5, 20)
            for j, lam_nm in enumerate(lams):
                flux[j] += strength * math.exp(-0.5 * ((lam_nm - line_lam) / width) ** 2)

        return {
            "specID":       f"MOCK-{idx:010d}",
            "temperature":  round(T, 1),
            "redshift":     round(rng.uniform(0, 3), 4),
            "wavelengths":  lams,
            "flux":         flux,
            "n_points":     self.n_wavelengths,
        }

    def stream(self) -> "Stream | Empty":
        def go(idx: int) -> Stream:
            return cons(
                self._make_spectrum(idx),
                Thunk(lambda: go(idx + 1)),
            )
        return go(0)


# ── Source registry ────────────────────────────────────────────────────────────

REGISTRY: dict[str, type] = {
    "SDSS":   SDSSSource,
    "JWST":   JWSTSource,
    "LIGO":   LIGOSource,
    "GAIA":   GAIASource,
    "File":   FileSource,
    "CSV":    CSVSource,
    "Mock":   MockSpectralSource,
}


def open_source(name: str, **kwargs) -> "Stream | Empty":
    """
    Open a named data source as a lazy stream.

    Example::

        sdss = open_source("SDSS", obj_type="GALAXY", redshift_min=0.5)
        sdss_stream = sdss  # ∞Stream — nothing downloaded yet
    """
    if name not in REGISTRY:
        raise ValueError(
            f"Unknown source {name!r}. Available: {list(REGISTRY.keys())}"
        )
    source = REGISTRY[name](**kwargs)
    return source.stream()
