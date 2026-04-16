# Changelog

All notable changes to Æergia∞ are documented here.

## [0.1.0] — 2024

### Initial release

**Core runtime**
- Lazy evaluation engine — memoised `Thunk` type, `force()`, `delay()`
- Infinite lazy streams — `Stream` codata type, `cons()`, `from_n()`, `repeat()`, `iterate()`, `cycle()`, `unfold()`
- Demand operator `~>` — int, predicate, "first", slice, and budget specs
- Built-in infinite sequences — `primes()`, `fibs()`, `pi_digits()`
- Stream combinators — `smap`, `sfilter`, `zip_with`, `scan`, `chunk`, `window`, `interleave`, `merge_sorted`, `flatten`

**Symbolic compression**
- `FourierN(n)` — Fourier coefficient compression
- `PolynomialN(n)` — least-squares polynomial fitting
- `BlackbodySpectrum` — Planck function (2 floats per spectrum)
- `GaussianMixture(k)` — EM-fitted mixture model
- `DeltaChain` — delta encoding with run-length compression
- `WaveletModel` — Haar wavelet transform with thresholding
- `auto_compress()` — automatic model selection
- `SymbolicArchive` — persistent compressed store with metadata queries

**Data source adapters (29 total)**
- Astronomical: SDSS, JWST, LIGO, GAIA (mock + live structure)
- REST APIs: OpenAlex, GBIF, NOAA, arXiv, Wikidata, FRED, OpenMeteo, GitHub, OpenFDA
- Streaming: WebSocket, Kafka, MQTT, SSE
- Files: FITS, HDF5, Parquet, NetCDF, FASTA, CSV, NDJSON
- Databases: PostgreSQL (+ LISTEN/NOTIFY), MongoDB (+ Change Streams), SQLite, DuckDB, InfluxDB

**Domain connectors**
- `astronomy`: SDSS, JWST, LIGO, GAIA, ZTF, LSST, TESS, VizieR
- `climate`: ERA5, NOAA
- `genomics`: NCBI, UniProt, PDB
- `finance`: FRED, crypto ticks
- `earth`: GBIF, IRIS seismology
- `physics`: CERN LHC, IceCube neutrinos
- `social`: OpenAlex, arXiv

**Stream operations**
- Windowing: `tumbling_window`, `sliding_window`, `session_window`, `time_window`
- Joining: `spatial_join` (sky cross-match), `temporal_join`, `join_by_key`
- Merging: `merge_sources` (N heterogeneous streams → one ∞T)
- Partitioning: `partition_by`
- Monitoring: `PipelineMonitor` (throughput, latency)
- Watching: `ArchiveWatcher` (poll → stream only new records)

**Language frontend**
- Lexer with all Æergia∞ tokens: `~>`, `∞`, `:>`, `!!`, `|>`, `Δ`, `⊳`, `∈`
- Recursive-descent Pratt parser for `.ae` source files
- Call-by-need evaluator with pattern matching
- Standard library: Prelude, Streams, Math, IO, Crypto, Concurrent, Sources, Compress
- Interactive REPL (`python -m aergia`) with `:load`, `:stream`, `:compress`, `:sources`

**Tests**: 42 passing (thunks, streams, compression, sources)
