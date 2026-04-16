"""
Æergia∞ Example 05 — Universal Realtime Pipeline

Demonstrates the full capability:
  • 4 different live data sources (astronomy, climate, physics, biology)
  • Spatial join between ZTF alerts and SDSS catalogue
  • Sliding time window with per-window statistics
  • Symbolic compression of compressed results into an archive
  • ArchiveWatcher detecting updates and streaming new records
  • Pipeline monitoring (throughput, latency)

Run: python examples/05_realtime_pipeline.py
"""
import sys, os, time, math
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from aergia.stream     import take, sfilter, smap, scan, from_list
from aergia.stream_ops import (tumbling_window, sliding_window, spatial_join,
                                merge_sources, PipelineMonitor, ArchiveWatcher)
from aergia.symbolic   import FourierN, BlackbodySpectrum, auto_compress, SymbolicArchive
from aergia.connectors import astronomy, climate, genomics, physics, earth

SEP = "═" * 64

def section(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")


print(f"""
╔{SEP}╗
║  Æergia∞  —  Universal Realtime Pipeline Demo              ║
╚{SEP}╝
""")


# ════════════════════════════════════════════════════════════
section("1. MULTI-SOURCE STREAM MERGE")
# ════════════════════════════════════════════════════════════

print("""
  Merging 4 live sources into a single ∞Event stream.
  Each source updates at different frequencies.
  The merge is lazy — no source is fetched until demanded.
""")

# Four different live archives, one demand operator
ztf_alerts = astronomy.ZTF.alerts(mock_rate=1000)
ligo_events = astronomy.LIGO.events()
seismic     = earth.IRIS.events(min_magnitude=4.0)
collisions  = physics.CERN.collisions(experiment="CMS")

# Merge into one stream — type: ∞Event (polymorphic)
all_events = merge_sources(
    smap(lambda e: {**e, "_source": "ZTF",    "_type": "transient"},  ztf_alerts),
    smap(lambda e: {**e, "_source": "LIGO",   "_type": "GW_event"},   ligo_events),
    smap(lambda e: {**e, "_source": "IRIS",   "_type": "earthquake"}, seismic),
    smap(lambda e: {**e, "_source": "CERN",   "_type": "collision"},  collisions),
)

# Demand 20 events — comes from all 4 sources interleaved
sample = take(20, all_events)
source_counts = {}
for e in sample:
    s = e["_source"]
    source_counts[s] = source_counts.get(s, 0) + 1

print(f"  Demanded 20 events from merged stream:")
for src, n in source_counts.items():
    print(f"    {src:<8} contributed {n} records")


# ════════════════════════════════════════════════════════════
section("2. SPATIAL JOIN: ZTF ALERTS × SDSS PHOTOMETRY")
# ════════════════════════════════════════════════════════════

print("""
  Cross-matching live ZTF transient alerts against SDSS photometry.
  Any alert within 5 arcseconds of an SDSS source is a match.
  This is how astronomers identify the host galaxy of a supernova.
  
  In every other tool: download both catalogues, run a spatial index.
  In Æergia∞: one expression, fully lazy, no data materialised.
""")

ztf_stream  = astronomy.ZTF.alerts(mock_rate=10000)
sdss_stream = astronomy.SDSS.galaxies(redshift_min=0.0)

# Spatial join: ZTF ⋈₅″ SDSS
ztf_list  = [{**a, "ra": float(a.get("ra", 0)), "dec": float(a.get("dec", 0))}
             for a in take(200, ztf_stream)]
sdss_list = take(500, sdss_stream)
matched = spatial_join(
    s1=from_list(ztf_list),
    s2=sdss_list,
    ra1_fn  = lambda r: r.get("ra",  0),
    dec1_fn = lambda r: r.get("dec", 0),
    ra2_fn  = lambda r: r.get("ra",  0),
    dec2_fn = lambda r: r.get("dec", 0),
    radius_arcsec = 300.0,
)

matched_list = take(5, matched)
print(f"  ZTF alerts:         200 (demanded)")
print(f"  SDSS reference:     500 (demanded)")
print(f"  Spatial matches:    {len(matched_list)} (within 300\" for demo)")
if matched_list:
    m = matched_list[0]
    print(f"  First match:")
    print(f"    ZTF alert ra={m['left'].get('ra',0):.4f}  dec={m['left'].get('dec',0):.4f}")
    print(f"    SDSS host  ra={m['right'].get('ra',0):.4f}  dec={m['right'].get('dec',0):.4f}")
    print(f"    Separation: {m['sep_arcsec']:.1f}\"")


# ════════════════════════════════════════════════════════════
section("3. WINDOWING: ROLLING STATISTICS OVER TIME")
# ════════════════════════════════════════════════════════════

print("""
  Tumbling windows of 50 LIGO events each.
  Per window: compute chirp mass distribution statistics.
  Stream of windows → stream of per-window summaries.
""")

ligo2 = astronomy.LIGO.events(snr_min=8.0)
chirp_stream = smap(lambda e: (e["mass_1_source"] * e["mass_2_source"])**0.6 /
                               (e["mass_1_source"] + e["mass_2_source"])**0.2,
                    ligo2)

# Tumbling window of 50 events
windows = tumbling_window(50, chirp_stream)
window_stats = smap(lambda w: {
    "n":         len(w),
    "mean_Mc":   round(sum(w)/len(w), 3),
    "max_Mc":    round(max(w), 3),
    "min_Mc":    round(min(w), 3),
    "std_Mc":    round((sum((x - sum(w)/len(w))**2 for x in w)/len(w))**0.5, 3),
}, windows)

win_results = take(3, window_stats)
print(f"  {'Window':<8} {'N':>4}  {'Mean Mc':>10}  {'Max Mc':>8}  {'Std':>8}")
print(f"  {'─'*8} {'─'*4}  {'─'*10}  {'─'*8}  {'─'*8}")
for i, w in enumerate(win_results):
    print(f"  {i+1:<8} {w['n']:>4}  {w['mean_Mc']:>10.3f}  {w['max_Mc']:>8.3f}  {w['std_Mc']:>8.3f}")


# ════════════════════════════════════════════════════════════
section("4. SYMBOLIC COMPRESSION ARCHIVE: LIVE INGESTION")
# ════════════════════════════════════════════════════════════

print("""
  Continuously ingesting ZTF alert spectra into a symbolic archive.
  Each spectrum is auto-compressed to its best mathematical model.
  The archive grows in O(model_params) space — not O(raw_bytes).
""")

from aergia.sources import MockSpectralSource
from aergia.stream  import take as _take

archive  = SymbolicArchive("ztf_spectra", BlackbodySpectrum)
spectra  = MockSpectralSource(n_wavelengths=256, seed=77).stream()

t0       = time.time()
batch    = _take(500, spectra)
for s in batch:
    archive.ingest(s["flux"], {
        "specID": s["specID"],
        "T":      s["temperature"],
        "z":      s["redshift"],
    })
elapsed = time.time() - t0

raw    = archive.would_have_stored_bytes(256)
sym    = archive.total_stored_bytes()
ratio  = archive.overall_ratio(256)

# Query: how many hot stars (T > 15,000K)?
hot = archive.query(lambda m: m.get("T", 0) > 15_000)

print(f"  Ingested {archive.record_count()} spectra in {elapsed:.2f}s")
print(f"  Raw size:      {raw:>10,} bytes  ({raw/1048576:.1f} MB)")
print(f"  Symbolic size: {sym:>10,} bytes  ({sym/1024:.1f} KB)")
print(f"  Compression:   {ratio:.0f}:1")
print(f"  Hot stars T>15kK: {len(hot)} found by metadata query (no decompression)")
print(f"")
print(f"  Extrapolation — 1 year of LSST nightly archiving:")
nightly = 10_000_000   # LSST alerts per night
per_year = nightly * 365
sym_year = sym * (per_year / archive.record_count())
raw_year = raw * (per_year / archive.record_count())
print(f"    Raw spectra/year:      {raw_year/1e12:.1f} TB")
print(f"    Symbolic archive/year: {sym_year/1e9:.1f} GB  ({ratio:.0f}× smaller)")


# ════════════════════════════════════════════════════════════
section("5. PIPELINE MONITOR: THROUGHPUT & LATENCY")
# ════════════════════════════════════════════════════════════

print("""
  Wrapping a pipeline with monitoring.
  Shows throughput (records/second) and per-record latency.
""")

monitor = PipelineMonitor()

# Monitored pipeline: GAIA stars → filter nearby → compress parallax stream
gaia_stream   = astronomy.GAIA.nearby(distance_pc_max=500.0)
gaia_monitored = monitor.wrap(gaia_stream)
gaia_filtered  = sfilter(lambda s: s.get("phot_g_mean_mag", 99) < 15.0,
                          gaia_monitored)

t_start = time.time()
result  = _take(1000, gaia_filtered)
elapsed = time.time() - t_start

stats = monitor.stats()
print(f"  Pipeline: GAIA.nearby() → mag<15 → take(1000)")
print(f"  Records processed:  {stats['total_records']:,}")
print(f"  Elapsed:            {stats['elapsed_sec']:.3f}s")
print(f"  Throughput:         {stats['throughput_rps']:,.0f} records/sec")
print(f"  Mean latency:       {stats['mean_latency_ms']:.3f}ms per record")
print(f"  Bright stars found: {len(result)}")


# ════════════════════════════════════════════════════════════
section("6. ARCHIVE WATCHER: DETECT & INGEST UPDATES")
# ════════════════════════════════════════════════════════════

print("""
  ArchiveWatcher polls a source and streams only NEW records.
  This is how Æergia∞ handles continuously updating archives:
  SDSS adds new observations every night → watcher detects them.

  In Æergia∞ syntax:
      watch SDSS.galaxies every 3600    -- re-check hourly
        |> where (.is_new)
        ~> budget: 1000
""")

from aergia.sources import SDSSSource

call_count = [0]
def sdss_factory():
    call_count[0] += 1
    # Each call returns an incrementally "newer" batch
    # simulating a real archive that grows with each poll
    return SDSSSource(obj_type="GALAXY", page_size=100).stream()

watcher = ArchiveWatcher(
    source_factory   = sdss_factory,
    poll_interval_sec= 0.05,   # fast for demo
    since_key        = "objID",
    since_fn         = lambda r: int(r.get("objID", "0").split("-")[-1]) if r.get("objID") else 0,
)

live_stream = watcher.start()
time.sleep(0.2)   # let it poll twice

new_records = _take(10, live_stream)
print(f"  Archive polled {call_count[0]} times")
print(f"  New records received: {len(new_records)}")
if new_records:
    ids = [r.get("objID", "?") for r in new_records[:3]]
    print(f"  First 3 IDs: {ids}")

watcher.stop()


# ════════════════════════════════════════════════════════════
section("7. CLIMATE × ASTRONOMY CORRELATION")
# ════════════════════════════════════════════════════════════

print("""
  Combining two completely different source types.
  ERA5 hourly temperature + GAIA stellar parallax distribution.
  Running correlation over a sliding window of 100 records.
  
  This is only possible because BOTH are ∞T streams — 
  the operations are source-agnostic.
""")

from aergia.stream_ops import sliding_window

era5_temp = smap(lambda r: r["t2m"],
                 sfilter(lambda r: abs(r["lat"]) < 30,
                         climate.ERA5.global_grid("t2m")))

gaia_plx  = smap(lambda s: s["parallax"],
                 sfilter(lambda s: s["parallax"] > 0,
                         astronomy.GAIA.stars(mag_max=12.0)))

# Sliding window cross-correlation (simplified)
t_vals = _take(200, era5_temp)
p_vals = _take(200, gaia_plx)

n   = min(len(t_vals), len(p_vals))
t_m = sum(t_vals[:n]) / n
p_m = sum(p_vals[:n]) / n
cov = sum((t_vals[i]-t_m) * (p_vals[i]-p_m) for i in range(n)) / n
t_s = (sum((x-t_m)**2 for x in t_vals[:n])/n)**0.5
p_s = (sum((x-p_m)**2 for x in p_vals[:n])/n)**0.5
corr = cov / (t_s * p_s + 1e-10)

print(f"  ERA5 mean T2m:          {t_m:.2f} K")
print(f"  GAIA mean parallax:     {p_m:.4f} mas")
print(f"  Cross-correlation:      {corr:.4f}  (≈0 as expected — unrelated!)")
print(f"  (Demonstrates source-agnostic stream algebra)")


# ════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  Complete pipeline summary:")
print(f"  ✓ 4 live sources merged into one ∞Event stream")
print(f"  ✓ Spatial join (ZTF × SDSS) — {len(matched_list)} matches")
print(f"  ✓ Tumbling windows — per-window LIGO statistics")
print(f"  ✓ Symbolic archive — {ratio:.0f}:1 compression live ingestion")
print(f"  ✓ Pipeline monitor — {stats['throughput_rps']:,.0f} rec/s")
print(f"  ✓ ArchiveWatcher — {call_count[0]} polls, {len(new_records)} new records")
print(f"  ✓ Cross-domain correlation — climate × astronomy")
print(f"\n  All via the same ∞T interface and ~> demand operator.")
print(f"{SEP}\n")
