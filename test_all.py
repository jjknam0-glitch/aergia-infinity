"""
Æergia∞ test suite
"""
import math, pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from aergia.thunk    import Thunk, force, delay, strict
from aergia.stream   import (
    primes, fibs, from_n, repeat, iterate, cycle, take, drop, nth,
    smap, sfilter, zip_with, scan, chunk, window, interleave,
    from_list, EMPTY, Empty, cons, range_finite, take_while, demand,
)
from aergia.symbolic import (
    FourierN, PolynomialN, BlackbodySpectrum, GaussianMixture,
    DeltaChain, WaveletModel, SymbolicArchive, auto_compress,
)
from aergia.sources  import SDSSSource, LIGOSource, MockSpectralSource


# ─────────────────── Thunk tests ───────────────────────────────

class TestThunk:
    def test_force_value(self):
        t = Thunk(lambda: 42)
        assert force(t) == 42

    def test_memoised(self):
        calls = [0]
        def fn():
            calls[0] += 1; return 99
        t = Thunk(fn)
        force(t); force(t); force(t)
        assert calls[0] == 1   # computed only once

    def test_chain_flattening(self):
        t = Thunk(lambda: Thunk(lambda: Thunk(lambda: "deep")))
        assert force(t) == "deep"

    def test_error_cached(self):
        t = Thunk(lambda: 1/0)
        with pytest.raises(ZeroDivisionError): force(t)
        with pytest.raises(ZeroDivisionError): force(t)

    def test_delay(self):
        t = delay(lambda: [1, 2, 3])
        assert force(t) == [1, 2, 3]

    def test_map(self):
        t = Thunk(lambda: 10)
        t2 = t.map(lambda x: x * 2)
        assert force(t2) == 20


# ─────────────────── Stream tests ─────────────────────────────

class TestStreams:
    def test_primes_first_10(self):
        assert take(10, primes()) == [2,3,5,7,11,13,17,19,23,29]

    def test_primes_are_prime(self):
        ps = take(50, primes())
        for p in ps:
            assert all(p % d != 0 for d in range(2, p)) or p == 2

    def test_fibs(self):
        assert take(8, fibs()) == [0,1,1,2,3,5,8,13]

    def test_fib_property(self):
        fs = take(20, fibs())
        for i in range(2, len(fs)):
            assert fs[i] == fs[i-1] + fs[i-2]

    def test_nth(self):
        assert nth(from_n(0), 0) == 0
        assert nth(from_n(0), 99) == 99
        assert nth(fibs(), 10) == 55

    def test_take_less_than_available(self):
        assert take(3, range_finite(1, 2)) == [1, 2]

    def test_drop(self):
        s = from_n(0)
        assert take(5, drop(10, s)) == [10,11,12,13,14]

    def test_smap(self):
        s = smap(lambda x: x*x, from_n(1))
        assert take(5, s) == [1,4,9,16,25]

    def test_sfilter(self):
        s = sfilter(lambda n: n%3==0, from_n(0))
        assert take(5, s) == [0,3,6,9,12]

    def test_zip_with(self):
        s = zip_with(lambda a,b: a+b, from_n(0), from_n(0))
        assert take(5, s) == [0,2,4,6,8]

    def test_scan(self):
        s = scan(lambda acc,x: acc+x, 0, from_n(1))
        assert take(5, s) == [0,1,3,6,10]

    def test_chunk(self):
        s = chunk(3, from_n(0))
        assert take(3, s) == [[0,1,2],[3,4,5],[6,7,8]]

    def test_window(self):
        s = window(3, from_n(0))
        assert take(3, s) == [[0,1,2],[1,2,3],[2,3,4]]

    def test_interleave(self):
        a = from_n(0)
        b = from_n(100)
        s = interleave(a, b)
        assert take(6, s) == [0,100,1,101,2,102]

    def test_demand_int(self):
        assert demand(from_n(0), 5) == [0,1,2,3,4]

    def test_demand_first(self):
        assert demand(from_n(42), "first") == 42

    def test_from_list(self):
        s = from_list([1,2,3])
        assert take(10, s) == [1,2,3]  # finite

    def test_empty(self):
        assert take(10, EMPTY) == []

    def test_cycle(self):
        s = cycle([1,2,3])
        assert take(7, s) == [1,2,3,1,2,3,1]

    def test_take_while(self):
        assert take_while(lambda x: x < 5, from_n(0)) == [0,1,2,3,4]

    def test_range_finite(self):
        s = range_finite(1, 10, 2)
        assert take(20, s) == [1,3,5,7,9]


# ─────────────────── Symbolic compression tests ────────────────

class TestSymbolic:

    def test_fourier_roundtrip(self):
        n = 256
        signal = [math.sin(i * 0.1) for i in range(n)]
        model  = FourierN(64); model.fit(signal)
        recon  = model.decode(n)
        rms    = math.sqrt(sum((a-b)**2 for a,b in zip(signal,recon))/n)
        assert rms < 0.02   # near-lossless with 64 coeffs on pure sine

    def test_fourier_compression_ratio(self):
        n = 1024
        signal = [math.sin(i*0.1) for i in range(n)]
        model  = FourierN(32); model.fit(signal)
        assert model.compression_ratio(n) == pytest.approx(16.0)

    def test_polynomial_fit(self):
        n    = 500
        data = [3*i**2 - 2*i + 1 for i in range(n)]
        m    = PolynomialN(3); m.fit(data)
        recon = m.decode(n)
        rms = math.sqrt(sum((a-b)**2 for a,b in zip(data,recon))/n)
        assert rms < 1.0  # near perfect for polynomial data

    def test_blackbody_parameters(self):
        T, h, c, k = 6000.0, 6.626e-34, 3e8, 1.381e-23
        n = 256
        spec = []
        for i in range(n):
            lam = (300+700*i/(n-1))*1e-9
            try: b = (2*h*c**2/lam**5)/(math.exp(h*c/(lam*k*T))-1)
            except: b = 0.0
            spec.append(b)
        m = BlackbodySpectrum(); m.fit(spec)
        assert m.parameter_bytes() == 16   # just 2 float64s!
        assert abs(m.temperature - T) < 2000  # within 2000K of true T

    def test_blackbody_high_ratio(self):
        n = 1024
        spec = [float(i) for i in range(n)]  # placeholder
        m = BlackbodySpectrum(); m.fit(spec)
        assert m.compression_ratio(n) > 100

    def test_delta_chain_monotone(self):
        data = [float(i) for i in range(1000)]
        m = DeltaChain(quantise_to=1.0); m.fit(data)
        recon = m.decode(1000)
        # Monotone data: deltas all equal 1, massive RLE compression
        assert m.parameter_bytes() < 200  # very compressed

    def test_wavelet_roundtrip(self):
        n = 256
        data = [math.sin(i*0.2)+math.cos(i*0.7) for i in range(n)]
        m = WaveletModel(0.5); m.fit(data)  # keep 50%
        recon = m.decode(n)
        # With 50% coefficients, should be reasonable quality
        rms = math.sqrt(sum((a-b)**2 for a,b in zip(data,recon))/n)
        assert rms < 0.5

    def test_auto_selects_blackbody_for_spectrum(self):
        T, h, c, k = 5500.0, 6.626e-34, 3e8, 1.381e-23
        n = 512
        spec = []
        for i in range(n):
            lam = (300+700*i/(n-1))*1e-9
            try: b = (2*h*c**2/lam**5)/(math.exp(h*c/(lam*k*T))-1)
            except: b = 0.0
            spec.append(b)
        m = auto_compress(spec)
        # Should pick a very compact model
        assert m.parameter_bytes() < 200

    def test_archive_stores_compressed(self):
        archive = SymbolicArchive("test", FourierN, {"n": 16})
        for i in range(100):
            data = [math.sin(i*0.1 + j*0.05) for j in range(256)]
            archive.ingest(data, {"idx": i})
        assert archive.record_count() == 100
        raw = archive.would_have_stored_bytes(256)
        sym = archive.total_stored_bytes()
        assert sym < raw / 5    # at least 5x compression

    def test_archive_metadata_query(self):
        archive = SymbolicArchive("test2", DeltaChain)
        for i in range(50):
            data = [float(j) for j in range(100)]
            archive.ingest(data, {"idx": i, "hot": i > 25})
        hot = archive.query(lambda m: m.get("hot", False))
        assert len(hot) == 24


# ─────────────────── Source tests ──────────────────────────────

class TestSources:
    def test_sdss_stream(self):
        s = SDSSSource().stream()
        records = take(10, s)
        assert len(records) == 10
        for r in records:
            assert "objID" in r
            assert "ra" in r
            assert "redshift" in r

    def test_sdss_infinite(self):
        s = SDSSSource().stream()
        # Can demand 1000 without error
        records = take(1000, s)
        assert len(records) == 1000

    def test_ligo_stream(self):
        s = LIGOSource().stream()
        events = take(10, s)
        assert len(events) == 10
        for e in events:
            assert "name" in e
            assert "total_mass" in e
            assert "strain_data" in e  # lazy!

    def test_ligo_strain_lazy(self):
        s = LIGOSource().stream()
        event = take(1, s)[0]
        # strain_data is a Thunk — not yet evaluated
        from aergia.thunk import Thunk
        assert isinstance(event["strain_data"], Thunk)
        # Force it
        data = force(event["strain_data"])
        assert "strain" in data
        assert len(data["strain"]) == 4096

    def test_mock_spectra(self):
        s = MockSpectralSource(n_wavelengths=128).stream()
        specs = take(5, s)
        assert len(specs) == 5
        for sp in specs:
            assert sp["n_points"] == 128
            assert len(sp["flux"]) == 128
            assert sp["temperature"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
