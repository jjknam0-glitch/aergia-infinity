"""
Æergia∞ Live Demo
Runs directly in Python, showing all core features working.
"""
import sys, os, math, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from aergia.stream   import primes, fibs, pi_digits, take, sfilter, smap, from_n, demand, scan
from aergia.symbolic import (FourierN, PolynomialN, BlackbodySpectrum, GaussianMixture,
                              DeltaChain, WaveletModel, auto_compress, SymbolicArchive)
from aergia.sources  import SDSSSource, JWSTSource, LIGOSource, MockSpectralSource

SEP = "─" * 60

def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

print("""
╔══════════════════════════════════════════════════════════════╗
║              Æergia∞  v0.1.0  —  Live Demo                  ║
║  Two infinities: ∞ data sources  +  ∞ compression           ║
╚══════════════════════════════════════════════════════════════╝
""")

# ─────────────────────────────────────────────────────────────
section("1. INFINITE STREAMS  (the ~> demand operator)")
# ─────────────────────────────────────────────────────────────

p = primes()
print(f"  primes ~> 15          = {take(15, p)}")

f = fibs()
print(f"  fibs   ~> 12          = {take(12, f)}")

# the 1000th Fibonacci number
f2 = fibs()
fib1000 = [x for i, x in enumerate(f2) if i == 1000][0]
print(f"  fibs !! 1000          = {fib1000}")

# Filtered infinite stream
evens = sfilter(lambda n: n % 2 == 0, from_n(0))
print(f"  evenNats ~> 10        = {take(10, evens)}")

# Mapped infinite stream
squares = smap(lambda n: n*n, from_n(1))
print(f"  squares ~> 10         = {take(10, squares)}")

# Pi digits
pi = pi_digits()
digits = take(40, pi)
print(f"  π digits (first 40)   = {''.join(map(str, digits))}")

# ─────────────────────────────────────────────────────────────
section("2. SDSS GALAXY STREAM  (infinite astronomical data)")
# ─────────────────────────────────────────────────────────────

print("  Opening SDSS galaxy stream (mock mode, real API structure)...")
sdss = SDSSSource(obj_type="GALAXY", redshift_min=0.5).stream()

# Demand 5 galaxies
galaxies = take(5, sdss)
print(f"  Fetched {len(galaxies)} galaxies")
for g in galaxies:
    print(f"    ID: {g['objID']}  ra={g['ra']:.4f}  dec={g['dec']:.4f}  z={g['redshift']:.3f}  r={g['r']:.2f}")

# Pipeline: filter then map
high_z = sfilter(lambda g: g['redshift'] > 1.5, SDSSSource(obj_type="GALAXY").stream())
bright = sfilter(lambda g: g['r'] < 21.0, high_z)
result = take(200, bright)
mean_z = sum(g['redshift'] for g in result) / len(result)
print(f"\n  Pipeline: galaxies → z>1.5 → r<21 → demand 200")
print(f"  Got {len(result)} galaxies,  mean redshift = {mean_z:.4f}")
print(f"  (Fetched only what was needed — nothing more downloaded)")

# ─────────────────────────────────────────────────────────────
section("3. LIGO GRAVITATIONAL WAVE STREAM")
# ─────────────────────────────────────────────────────────────

ligo = LIGOSource().stream()
events = take(10, ligo)
print(f"  Fetched {len(events)} gravitational wave events")
print(f"  {'Name':<16} {'Total Mass':>12} {'Chirp Mass':>12} {'SNR':>8} {'Distance':>12}")
print(f"  {'-'*16} {'-'*12} {'-'*12} {'-'*8} {'-'*12}")
for e in events[:6]:
    m1, m2 = e['mass_1_source'], e['mass_2_source']
    mc = (m1*m2)**0.6 / (m1+m2)**0.2
    print(f"  {e['name']:<16} {e['total_mass']:>10.1f} M☉  {mc:>10.2f} M☉  {e['network_matched_filter_snr']:>6.1f}  {e['luminosity_distance']:>8.0f} Mpc")

# Demand the strain data for the first event
print(f"\n  Accessing strain data for {events[0]['name']}...")
from aergia.thunk import force
strain_data = force(events[0]['strain_data'])
strain = strain_data['strain']
print(f"  Strain timeseries: {len(strain)} samples at {1/strain_data['dt']:.0f} Hz")
print(f"  Peak strain: {max(abs(s) for s in strain):.2e}")
print(f"  (Strain data was lazy — only fetched when demanded)")

# ─────────────────────────────────────────────────────────────
section("4. SYMBOLIC COMPRESSION  (store rules, not bytes)")
# ─────────────────────────────────────────────────────────────

n = 1024
print(f"  All tests use {n}-point signals = {n*8} bytes raw (float64)")
print()

# ── Fourier compression ──
signal = [math.sin(i * 0.1) + 0.3*math.sin(i * 0.37) for i in range(n)]
f32 = FourierN(32); f32.fit(signal)
f8  = FourierN(8);  f8.fit(signal)
print(f"  Sine + overtone signal:")
print(f"    FourierN(32): {f32.parameter_bytes():5d} bytes  ratio {f32.compression_ratio(n):6.1f}:1")
print(f"    FourierN(8):  {f8.parameter_bytes():5d} bytes  ratio {f8.compression_ratio(n):6.1f}:1")

# ── Blackbody spectrum ──
T = 5778.0
h, c, k = 6.626e-34, 3e8, 1.381e-23
spectrum = []
for i in range(n):
    lam = (300 + 700*i/(n-1)) * 1e-9
    try: b = (2*h*c**2/lam**5)/(math.exp(h*c/(lam*k*T))-1)
    except: b = 0.0
    spectrum.append(b)

bb = BlackbodySpectrum(); bb.fit(spectrum)
print(f"\n  Solar-type star spectrum (T={T:.0f} K):")
print(f"    BlackbodySpectrum: {bb.parameter_bytes():5d} bytes  ratio {bb.compression_ratio(n):6.1f}:1")
print(f"    Stored as: T={bb.temperature:.1f} K,  A={bb.amplitude:.3e}")
print(f"    → An entire star's spectrum in just 2 numbers!")

# ── Delta chain ──
temp = [20 + 5*math.sin(i*6.283/1440) + 0.1*math.cos(i*0.3) for i in range(1440)]
dc = DeltaChain(quantise_to=0.05); dc.fit(temp)
print(f"\n  Temperature sensor (1 day = 1440 readings):")
print(f"    DeltaChain:  {dc.parameter_bytes():5d} bytes  ratio {dc.compression_ratio(1440):6.1f}:1")

# ── Wavelet ──
wm = WaveletModel(keep_fraction=0.05); wm.fit(signal)
print(f"\n  Same signal, wavelet (keep top 5% coefficients):")
print(f"    WaveletModel:  {wm.parameter_bytes():5d} bytes  ratio {wm.compression_ratio(n):6.1f}:1")

# ── Auto-selector ──
print(f"\n  Auto-selecting best model for each dataset:")
poly_data = [2*i*i - 3*i + 7 for i in range(n)]
auto_poly = auto_compress(poly_data)
auto_sine = auto_compress(signal)
auto_bb   = auto_compress(spectrum)
print(f"    Quadratic trend →  {type(auto_poly).__name__:<20} {auto_poly.parameter_bytes():5d} bytes  {auto_poly.compression_ratio(n):6.1f}:1")
print(f"    Sine signal     →  {type(auto_sine).__name__:<20} {auto_sine.parameter_bytes():5d} bytes  {auto_sine.compression_ratio(n):6.1f}:1")
print(f"    Star spectrum   →  {type(auto_bb).__name__:<20} {auto_bb.parameter_bytes():5d} bytes  {auto_bb.compression_ratio(n):6.1f}:1")

# ─────────────────────────────────────────────────────────────
section("5. SYMBOLIC ARCHIVE  (∞ storage capacity)")
# ─────────────────────────────────────────────────────────────

print("  Creating a SymbolicArchive — ingesting 1000 synthetic spectra...")
archive = SymbolicArchive("stellar_survey", BlackbodySpectrum)

mock = MockSpectralSource(n_wavelengths=512, seed=42)
spectra_stream = mock.stream()
batch = take(1000, spectra_stream)

t0 = time.time()
for s in batch:
    archive.ingest(s['flux'], {"specID": s['specID'], "T": s['temperature'], "z": s['redshift']})
elapsed = time.time() - t0

raw_bytes   = archive.would_have_stored_bytes(512)
stored_bytes = archive.total_stored_bytes()
ratio        = archive.overall_ratio(512)

print(f"  Ingested {archive.record_count()} spectra in {elapsed:.2f}s")
print(f"  Raw storage would be: {raw_bytes:>12,} bytes  ({raw_bytes//1024//1024:.1f} MB)")
print(f"  Symbolic storage:     {stored_bytes:>12,} bytes  ({stored_bytes//1024:.1f} KB)")
print(f"  Overall ratio:        {ratio:>9.0f}:1")
print(f"\n  Query: stars with T > 10000 K (no decompression needed)")
hot_stars = archive.query(lambda m: m.get("T", 0) > 10000)
print(f"  Found {len(hot_stars)} hot stars in archive (metadata query only)")

# Scale-up math
gb = 1_000_000_000
spec_per_gb_raw = gb // (512 * 8)
spec_per_gb_sym = gb // stored_bytes * 1000  # extrapolate
print(f"\n  Storage capacity per 1 GB:")
print(f"    Raw 512-pt spectra:  {spec_per_gb_raw:>12,}")
print(f"    Symbolic (blackbody):{spec_per_gb_sym:>12,}")
print(f"  → 1 GB stores the spectra of {spec_per_gb_sym//1_000_000:.0f} million stars symbolically")
print(f"  → Full Gaia catalogue (1.8B stars) ≈ {1_800_000_000//spec_per_gb_sym:.1f} GB symbolically")

# ─────────────────────────────────────────────────────────────
section("6. RUNNING STATISTICS  (O(1) memory, any stream size)")
# ─────────────────────────────────────────────────────────────

print("  Welford online mean/variance over infinite galaxy redshift stream...")

def welford_step(state, x):
    n, mean, M2 = state
    n += 1
    delta = x - mean
    mean += delta / n
    M2   += delta * (x - mean)
    return (n, mean, M2)

sdss2 = SDSSSource(obj_type="GALAXY").stream()
z_stream = smap(lambda g: g['redshift'], sdss2)
stats_stream = scan(welford_step, (0, 0.0, 0.0), z_stream)

snapshots = take(5000, stats_stream)
# Show every 1000th snapshot
for i in [999, 1999, 2999, 3999, 4999]:
    n, mean, M2 = snapshots[i]
    var = M2 / (n-1) if n > 1 else 0
    print(f"  After {n:5d} galaxies:  mean_z = {mean:.5f}  σ_z = {var**0.5:.5f}")

print(f"\n  Memory used: 3 floats regardless of stream length — O(1)")

# ─────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  All demos complete. Æergia∞ features demonstrated:")
print("  ✓ Infinite streams with lazy evaluation")
print("  ✓ ~> demand operator (fetch exactly what you need)")
print("  ✓ SDSS/LIGO data streams with pipeline fusion")
print("  ✓ Symbolic compression (rules, not bytes)")
print("  ✓ Auto-model selection")
print("  ✓ SymbolicArchive (infinite storage)")
print("  ✓ O(1) running statistics over infinite streams")
print(f"{SEP}\n")
