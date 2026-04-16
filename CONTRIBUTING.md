# Contributing to Æergia∞

Thank you for your interest in contributing. Æergia∞ is a research language
prototype — contributions at any level are welcome.

## Getting Started

```bash
git clone https://github.com/YOUR_USERNAME/Aergia-infinity.git
cd Aergia-infinity
pip install -e ".[dev]"
pytest tests/ -v          # should show 42 passing
python demo.py            # should run cleanly
```

## Areas Most Needing Contribution

### 1. Type Checker (highest impact)
The `T ~ Model` and `Δ[T]` types are implemented at the runtime level but
not yet enforced by a type checker. Implementing the type system is the
single most impactful contribution.

Files to work on: `aergia/types.py` (create), `aergia/evaluator.py`

### 2. New Data Source Connectors
Any major public archive not yet covered. Good candidates:
- **NASA HEASARC** (high-energy astrophysics)
- **ESO Archive** (European Southern Observatory)
- **ENCODE** (genomic regulatory elements)
- **OpenStreetMap** (via Overpass API)
- **ClinicalTrials.gov**
- **World Bank Open Data**

Add to `aergia/adapters/rest.py` or `aergia/connectors/`.
Register in `aergia/adapters/protocol.py`'s `SourceRegistry`.

### 3. Compression Models
New symbolic models for domain-specific data. Each model needs:
- `fit(data: list[float]) -> self`
- `decode(n: int) -> list[float]`
- `parameter_bytes() -> int`

Ideas:
- **ChirpModel** — for gravitational wave waveforms
- **SinusoidalMixture** — for stellar oscillation spectra
- **ExponentialDecay** — for radioactive decay / fluorescence
- **PowerLaw** — for particle energy spectra

### 4. Parser Completeness
The parser in `aergia/parser.py` handles the most common constructs but
is missing some Æergia∞ syntax. Any `.ae` file that fails to parse is a bug.

### 5. Tests
More tests are always welcome, especially:
- Parser round-trip tests (parse → eval → result)
- Live source integration tests (marked `@pytest.mark.network`)
- Compression model quality benchmarks

## Code Style

- Follow the existing docstring style (module docstrings explain purpose + syntax)
- Keep each file focused on one concern
- All new sources must work in mock mode (no network required for tests)
- All new compression models must pass `model.fit(data).decode(len(data))` roundtrip

## Pull Request Process

1. Open an issue first for anything non-trivial
2. Branch from `main`, name it `feature/description` or `fix/description`
3. Add tests for new functionality
4. Run `pytest tests/ -v` — all 42 must pass
5. Run `python demo.py` — must complete without errors
6. Update `README.md` if you add sources or features

## Questions

Open a GitHub Issue. Label it `question`.
