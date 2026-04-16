<div align="center">

# Æergia∞

**A lazy, symbolic, stream-oriented language built for infinite data.**

[![CI](https://github.com/YOUR_USERNAME/Aergia-infinity/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/Aergia-infinity/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![42 tests passing](https://img.shields.io/badge/tests-42%20passing-brightgreen)](#testing)

```
primes ~> 15         →  [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
fibs !! 100          →  354224848179261915075
SDSS.galaxies ~> 5   →  [{ra: 83.2, dec: 12.4, redshift: 2.71, ...}, ...]
spectrum ~ FourierN 32   →  512 bytes  (instead of 32768 bytes raw)
```

</div>

---

## What is Æergia∞?

**Æergia∞** (pronounced *ay-ergia infinity*) is a programming language with two core ideas that have never existed together in any language before:

| The two ∞ | Meaning |
|-----------|---------|
| **∞ input** | Any data archive — astronomical, genomic, financial, climate, real-time sensor — is a lazy stream. Nothing downloads until you demand it with `~>`. |
| **∞ storage** | Values are stored as the *mathematical rule that describes them*, not as raw bytes. A star's full spectrum becomes 2 numbers. A galaxy survey becomes a 16 MB archive instead of 32 GB. |

The name works exactly like **C++**: C plus the `++` operator. Æergia (the Greek spirit of idleness — perfectly lazy) plus `∞`, its signature operator.

---

## The Problem It Solves

Modern science produces data faster than we can store or process it:

- **Vera Rubin Observatory** — 15 TB per night, starting 2025
- **Square Kilometre Array** — 5 exabytes per year
- **CERN LHC** — discards 99.999% of collision data in real time
- **Gaia** — 1.8 billion stars, continuously updated
- **Genomics sequencers** — running 24/7, producing infinite read streams

Every existing tool forces a choice: download everything (impossible), or pre-filter manually (lossy, slow, needs re-doing when your question changes).

Æergia∞ gives you a third option: write the entire analysis as a lazy symbolic expression, and let the runtime pull exactly the bytes needed, compressed to mathematical models, on demand.

---

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/Aergia-infinity.git
cd Aergia-infinity
pip install -e ".[dev]"

# Interactive REPL
python -m aergia

# Run the live demo (all features, no network required)
python demo.py

# Run the realtime pipeline example
python examples/05_realtime_pipeline.py
```

### Requirements

- Python ≥ 3.11 (zero required dependencies for core features)
- `numpy`, `scipy` — optional, for faster compression models
- `requests` — optional, for live REST API sources
- `astropy` — optional, for astronomical coordinate handling

---

## Language Syntax

Æergia∞ source files use the `.ae` extension. Run them with `python -m aergia file.ae`.

### Infinite streams — `∞T`

```aergia
-- Every stream has type ∞T. Nothing is evaluated until demanded.
primes  : ∞Int
fibs    : ∞Int
sdss    : ∞Galaxy
```

### The demand operator — `~>`

```aergia
primes ~> 10           -- [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
fibs   ~> first        -- 0  (single element)
sdss   ~> 1000         -- fetches exactly 1000 galaxy records
sdss   ~> budget: 100MB  -- fetches as many as fit in 100 MB
```

### Lazy pipelines

```aergia
-- Nothing fetches until ~> is applied. The whole pipeline
-- compiles into a single parameterised source query.
highZ =
  SDSS.galaxies
    |> where  (.redshift > 2.5)
    |> where  (.r < 22.0)
    |> map    fitBlackbody
    |> sortBy .luminosity

highZ ~> 500   -- one round-trip to the source
```

### Symbolic compression — `T ~ Model`

```aergia
-- The ~ type modifier binds a compression model to a type.
-- Spectrum ~ BlackbodySpectrum  is a DIFFERENT type from Spectrum.
-- The type system prevents accidental decompression.

spectra : ∞(Spectrum ~ BlackbodySpectrum)   -- each spectrum = 2 floats
temp    : Δ[Float] by 0.1                   -- delta-encoded, 0.1°C precision
```

### Source declarations — a new kind of binding

```aergia
-- Not a function call. A declaration.
-- The runtime treats this as an eternal, lazy, live-updating value.
source galaxies : ∞Galaxy
  from   = SDSS
  where  = { .redshift > 0.5 }
  encode = BlackbodySpectrum

source alerts : ∞Alert = Kafka "kafka://lsst-broker:9092/alerts"
source climate : ∞Reading = MQTT "mqtt://sensors.example.com/temp/#"
```

### Infinite comprehensions — `{ x ∈ S | pred }`

```aergia
-- Set-builder notation over infinite sources.
-- The predicate is pushed to the source — it becomes an API query,
-- not a filter loop in Æergia∞.
-- Result type: ∞Galaxy

{ g ∈ SDSS | g.redshift > 1.5 ∧ g.r < 22.0 }
```

### Symbolic archives

```aergia
archive stellarSurvey : Archive FourierN
  source = SDSS.spectra |> where (.type == Galaxy)
  encode = FourierN 64       -- 512 bytes per spectrum instead of 32 KB
  index  = (.objID, .ra, .dec)
  update = streaming         -- continuously ingests new observations
```

### Δ type — delta encoding in the type system

```aergia
-- Δ[T] means "stored as initial value + differences".
-- Δ[T] by q adds quantisation precision.
-- O(1) append preserves the encoding.

temperature : Δ[Float] by 0.05   -- 20× compression over raw
temperature ⊕ 21.3               -- append in O(1), stays Δ-encoded
```

---

## Data Sources — 29 Built-in Connectors

Every source returns the same `∞T` type. `~>` works identically on all of them.

### Astronomy & Space

| Source | Archive | Records | Update freq |
|--------|---------|---------|-------------|
| `astronomy.SDSS` | Sloan Digital Sky Survey DR18 | 500M objects | nightly |
| `astronomy.JWST` | James Webb Space Telescope (MAST) | live ingestion | continuous |
| `astronomy.LIGO` | Gravitational wave events (GWOSC) | O1–O4 catalogue | per-run |
| `astronomy.GAIA` | Gaia stellar catalogue DR3 | 1.8B stars | per-release |
| `astronomy.ZTF` | Zwicky Transient Facility alerts | 1M/night via Kafka | realtime |
| `astronomy.LSST` | Vera Rubin/LSST (simulation) | 10M/night | realtime |
| `astronomy.TESS` | TESS light curves | 200K stars/sector | per-sector |
| `astronomy.VizieR` | CDS VizieR (22,000 catalogues) | any catalogue | varies |

### Climate & Earth

| Source | Archive | Records |
|--------|---------|---------|
| `climate.ERA5` | ECMWF global reanalysis 1940–present | hourly, 0.25° grid |
| `climate.NOAA` | NOAA weather stations (ISD) | 100K+ stations, daily |
| `adapters.OpenMeteo` | Free forecast API | 16-day hourly, no key |
| `earth.GBIF` | Biodiversity occurrences | 2B+ records |
| `earth.IRIS` | Global seismic event catalogue | continuous |

### Life Sciences

| Source | Archive | Records |
|--------|---------|---------|
| `genomics.NCBI` | GenBank, RefSeq, dbSNP, ClinVar | billions of sequences |
| `genomics.UniProt` | Protein sequences & function | 250M entries |
| `genomics.PDB` | Protein 3D structures | 215K structures |
| `adapters.FASTA` | Any FASTA/FASTQ file | lazy streaming |

### Research & Knowledge

| Source | Archive |
|--------|---------|
| `social.OpenAlex` | 200M+ scholarly papers (open access) |
| `social.ArXiv` | Preprints: physics, math, CS, bio, econ |
| `adapters.Wikidata` | 90M+ entities via SPARQL |

### Finance & Economics

| Source | Archive |
|--------|---------|
| `finance.FRED` | 800K+ FRED economic time series |
| `finance.Crypto` | Live crypto tick stream |

### Physics

| Source | Archive |
|--------|---------|
| `physics.CERN` | LHC collision events (CMS, ATLAS) |
| `physics.IceCube` | IceCube neutrino event stream |

### Protocol Adapters (any source)

| Adapter | Use case |
|---------|---------|
| `REST` | Any paginated JSON API — auto-detects cursor/offset/Link pagination |
| `WebSocket` | Live JSON streams (GraceDB, telescope feeds, IoT gateways) |
| `Kafka` | Distributed event streams (LSST, SKA, industrial) |
| `MQTT` | IoT sensors, weather stations, satellite telemetry |
| `FITS` | All professional astronomy data files |
| `HDF5` | Neuroscience, physics, genomics data |
| `Parquet` | Big data columnar format (Spark, BigQuery) |
| `NetCDF` | Climate and ocean grids (ERA5, CMIP6, GFS) |
| `PostgreSQL` | SQL tables + LISTEN/NOTIFY live change streaming |
| `MongoDB` | Documents + Change Streams live updates |
| `InfluxDB` | IoT and metrics time-series |
| `DuckDB` | Analytical SQL over Parquet/CSV/JSON files |

```python
from aergia.adapters import open_any

# Works with anything
papers    = open_any("OpenAlex", filter_str="publication_year:2024")
alerts    = open_any("kafka://lsst-broker:9092/ztf-alerts")
survey    = open_any("/data/gaia_dr3.fits")
climate   = open_any("/data/era5_2023.nc")
genome    = open_any("/data/GRCh38.fa.gz")
table     = open_any("postgresql://host/db?table=observations")
sensors   = open_any("mqtt://broker/sensors/#")

# All return ∞T — use ~> to demand
from aergia.stream import take
result = take(100, papers)
```

---

## Symbolic Compression

The core innovation: values are stored as the shortest mathematical rule that generates them, not as raw bytes.

| Model | Best for | Example ratio |
|-------|---------|---------------|
| `BlackbodySpectrum` | Stellar emission spectra | **512:1** (entire star = 2 floats) |
| `FourierN(n)` | Oscillating signals, spectra | 16:1 at n=32 |
| `PolynomialN(n)` | Smooth trends, light curves | 100:1 for quadratic data |
| `GaussianMixture(k)` | Peaked distributions, line profiles | 30–100:1 |
| `DeltaChain` | Slow-changing sensor streams | 10–20:1 with quantisation |
| `WaveletModel` | Images, spatially correlated data | 4–20:1 |
| `auto_compress` | Unknown data — picks best model | varies |

```python
from aergia.symbolic import BlackbodySpectrum, auto_compress, SymbolicArchive

# Compress a stellar spectrum to 2 numbers
model = BlackbodySpectrum()
model.fit(spectrum_1024_points)
print(model.parameter_bytes())          # → 16 bytes
print(model.compression_ratio(1024))   # → 512.0

# Automatically pick the best model
best = auto_compress(any_signal)

# Persistent archive: grows in O(model_params), not O(data_points)
archive = SymbolicArchive("survey", BlackbodySpectrum)
for spectrum in spectra:
    archive.ingest(spectrum["flux"], {"T": spectrum["temperature"]})

# Query without decompressing
hot_stars = archive.query(lambda m: m["T"] > 15_000)
print(f"Ratio: {archive.overall_ratio(1024):.0f}:1")
```

---

## Stream Operations

```python
from aergia.stream import (
    primes, fibs, from_n, repeat, iterate, cycle,
    take, drop, nth, smap, sfilter, zip_with, scan,
    chunk, window, interleave, demand,
)
from aergia.stream_ops import (
    tumbling_window, sliding_window, time_window,
    spatial_join, temporal_join, merge_sources,
    partition_by, ArchiveWatcher, PipelineMonitor,
)

# Infinite streams
print(take(10, primes()))      # [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
print(nth(fibs(), 100))        # 354224848179261915075

# Pipeline — all lazy
result = take(100,
    sfilter(lambda g: g["redshift"] > 2.0,
    smap(lambda g: {**g, "luminosity": compute_lum(g)},
    SDSS.galaxies())))

# Spatial join — cross-match two sky surveys
matched = spatial_join(ztf_alerts, sdss_catalogue, radius_arcsec=5.0)

# Merge N heterogeneous sources into one stream
all_events = merge_sources(ztf_stream, ligo_stream, seismic_stream)

# Live update watching — streams only new records since last poll
watcher = ArchiveWatcher(lambda: SDSS.galaxies(), poll_interval_sec=3600)
new_galaxies = watcher.start()   # ∞ stream of new records

# Pipeline monitoring
monitor = PipelineMonitor()
monitored = monitor.wrap(my_pipeline)
take(10_000, monitored)
print(monitor.stats())   # throughput, latency, record count
```

---

## Python API — Working Today

The interpreter is in progress. All runtime features work directly from Python:

```python
from aergia.stream   import primes, fibs, take, sfilter, smap, from_n
from aergia.symbolic import FourierN, BlackbodySpectrum, auto_compress, SymbolicArchive
from aergia.adapters import open_any
from aergia.connectors import astronomy, climate, genomics, physics

# Infinite streams
print(take(15, primes()))
print(nth(fibs(), 1000))

# Live SDSS galaxy stream
galaxies = astronomy.SDSS.galaxies(redshift_min=0.5)
high_z   = sfilter(lambda g: g["redshift"] > 2.0, galaxies)
batch    = take(500, high_z)

# Gravitational wave events
events = astronomy.LIGO.events(snr_min=12.0)
bbh    = astronomy.LIGO.bbh()    # binary black holes only

# Climate data
temp = climate.NOAA.daily("USW00094728")   # Central Park, NYC

# Genomics
proteins = genomics.UniProt.reviewed(organism="human")

# Physics
collisions = physics.CERN.collisions(experiment="CMS")

# Symbolic compression
model = BlackbodySpectrum().fit(spectrum)
print(f"{model.parameter_bytes()} bytes (vs {len(spectrum)*8} bytes raw)")

# Symbolic archive
archive = SymbolicArchive("survey", BlackbodySpectrum)
# ...ingest millions of spectra...
hot = archive.query(lambda m: m["T"] > 15_000)   # no decompression
print(f"Compression: {archive.overall_ratio(1024):.0f}:1")
```

---

## Project Structure

```
Aergia-infinity/
│
├── aergia/                     # Core language runtime
│   ├── thunk.py                # Lazy evaluation (memoised thunks)
│   ├── stream.py               # Infinite lazy streams + demand operator
│   ├── stream_ops.py           # Windowing, joining, merging, monitoring
│   ├── symbolic.py             # Symbolic compression engine
│   ├── sources.py              # Astronomical source adapters (SDSS, JWST, LIGO, Gaia)
│   ├── lexer.py                # Tokeniser for .ae source files
│   ├── ast_nodes.py            # AST node dataclasses
│   ├── parser.py               # Recursive-descent Pratt parser
│   ├── evaluator.py            # Call-by-need graph-reduction interpreter
│   ├── stdlib.py               # Standard library (Prelude, Streams, Math, IO, ...)
│   ├── repl.py                 # Interactive REPL (æ∞> prompt)
│   ├── __init__.py
│   └── __main__.py             # python -m aergia entry point
│
├── aergia/adapters/            # Universal source adapter layer
│   ├── protocol.py             # SourceProtocol base class + SourceRegistry
│   ├── rest.py                 # REST/JSON (OpenAlex, GBIF, NOAA, arXiv, FRED, ...)
│   ├── streaming.py            # WebSocket, Kafka, MQTT, SSE
│   ├── files.py                # FITS, HDF5, Parquet, NetCDF, FASTA, CSV, NDJSON
│   ├── database.py             # PostgreSQL, MongoDB, SQLite, DuckDB, InfluxDB
│   └── __init__.py             # open_any() universal entry point
│
├── aergia/connectors/          # Domain-specific pre-configured wrappers
│   ├── astronomy.py            # SDSS, JWST, LIGO, Gaia, ZTF, LSST, TESS, VizieR
│   ├── climate.py              # ERA5, NOAA, Open-Meteo
│   ├── genomics.py             # NCBI, UniProt, PDB
│   ├── finance.py              # FRED, crypto ticks
│   ├── earth.py                # GBIF, IRIS seismology
│   ├── physics.py              # CERN LHC, IceCube neutrinos
│   ├── social.py               # OpenAlex, arXiv
│   └── __init__.py
│
├── examples/
│   ├── 01_hello_universe.ae    # Primes, Fibonacci, π — basic streams
│   ├── 02_galaxy_survey.ae     # SDSS pipeline + symbolic compression
│   ├── 03_gravitational_waves.ae  # LIGO events + waveform compression
│   ├── 04_symbolic_compression.ae # All compression models demonstrated
│   └── 05_realtime_pipeline.py    # 4 live sources, spatial join, windowing
│
├── tests/
│   └── test_all.py             # 42 tests: thunks, streams, compression, sources
│
├── demo.py                     # Standalone demo — all features, no network needed
├── novel_syntax.py             # The genuinely novel language features explained
├── pyproject.toml
├── LICENSE                     # MIT
└── .github/workflows/ci.yml   # GitHub Actions CI (Python 3.11 + 3.12)
```

---

## Genuinely Novel Language Features

Most features in Æergia∞ refine existing ideas. Five are genuinely new — absent from every published language and academic paper:

### 1. `T ~ Model` — compression in the type

```aergia
x : Spectrum ~ BlackbodySpectrum   -- stored as 2 floats (T, A)
y : [Float]  ~ FourierN 32         -- stored as 32 coefficients
z : ∞(Spectrum ~ BlackbodySpectrum)  -- infinite compressed stream
```

No language has ever put a compression algorithm in a type signature. Not Haskell, Rust, Zig, Julia, APL, or any academic language. The type system prevents accidental decompression.

### 2. `source` as a declaration kind

```aergia
source galaxies : ∞Galaxy
  from   = SDSS
  where  = { .redshift > 0.5 }
  encode = BlackbodySpectrum
```

Every other language uses a function call to open a data source. Æergia∞ uses a **declaration** — a fourth kind of top-level binding alongside `let`, `type`, and `import`. The runtime treats it as an eternal, self-replenishing lazy value.

### 3. `{ x ∈ S | pred }` — infinite comprehension

```aergia
{ g ∈ SDSS | g.redshift > 1.5 ∧ g.r < 22.0 }  : ∞Galaxy
```

List comprehensions exist in many languages, but they produce `[T]`. This produces `∞T`. The `∈` binds to an infinite source, and the predicate is pushed into the source's query protocol, not evaluated locally.

### 4. `Δ[T] by q` — delta encoding in the type

```aergia
temperature : Δ[Float] by 0.1   -- quantised to 0.1° precision
temperature ⊕ 21.3              -- O(1) append, stays Δ-encoded
```

Delta encoding with quantisation as a primitive type modifier. `Δ[Float]` and `[Float]` are different types. The type system prevents O(n) appends and accidental decompression.

### 5. `budget:` / `while:` demand modifiers

```aergia
galaxies budget: 100MB     -- pull as many records as fit in 100 MB
alerts   while: (.snr > 8) -- pull while condition holds
stream   until: "2024-06-01"  -- pull until a timestamp
```

"Give me as many records as fit in 100 MB" cannot be expressed in any existing language. The budget propagates backwards to the source fetcher.

---

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

**42 tests** covering: thunk memoisation, infinite stream operations, demand operator, symbolic compression models, archive storage and query, all source adapters.

```
TestThunk   (6)   ✓ force, memoisation, chain-flattening, error caching
TestStreams (21)  ✓ primes, fibs, nth, map, filter, zip, scan, window, chunk, demand
TestSymbolic(10)  ✓ Fourier roundtrip, blackbody fitting, delta chain, auto-select, archive
TestSources  (5)  ✓ SDSS stream, infinite paging, LIGO events, lazy strain, mock spectra
```

---

## Roadmap

**Core language (in progress)**
- [x] Lazy stream engine with memoisation
- [x] Demand operator `~>` with int, predicate, and budget specs
- [x] Symbolic compression (6 models + auto-selector)
- [x] 29 data source adapters across 6 protocols
- [x] Stream windowing, joining, merging, partitioning
- [x] ArchiveWatcher (live update detection)
- [x] Interactive REPL (`python -m aergia`)
- [x] Lexer + Parser for `.ae` files
- [x] Call-by-need evaluator
- [ ] `T ~ Model` type checker (compression in types)
- [ ] `Δ[T]` primitive type
- [ ] Linear type system (prevents observing `∞T` without `~>`)
- [ ] Refinement types (`{n : Int | n > 0}`)

**Infrastructure**
- [ ] LLVM compilation backend
- [ ] Native `.aeg` archive file format with indexing
- [ ] Distributed demand propagation (multi-node pipelines)
- [ ] HEALPix spatial indexing for sky surveys
- [ ] GPU-accelerated compression fitting

---

## Contributing

Contributions welcome. The most impactful areas:

1. **Type checker** — implement `T ~ Model` and `Δ[T]` in the type system
2. **New connectors** — add adapters for archives not yet covered
3. **Compression models** — new symbolic models for domain-specific data
4. **Real API testing** — test live adapters against real endpoints

Please open an issue before submitting large PRs.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Name & Etymology

**Æergia∞** — *Æergia* (from *Aergia*, the Greek spirit of idleness and sloth; *Æ* is the classical ligature of A and E) plus **∞**, the infinity operator and the language's signature symbol.

Just as **C++** is C incremented by one, **Æergia∞** is Æergia taken to infinity.

The name is intentional: a lazy language, named after the spirit of laziness, that uses laziness as a superpower to handle infinite data sources and infinite storage compression.
