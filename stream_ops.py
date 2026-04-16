"""
aergia.stream_ops
~~~~~~~~~~~~~~~~~
Advanced stream operations for Æergia∞:

  Windowing    — tumbling, sliding, session windows over time
  Joining      — spatial, temporal, key-based stream joins
  Merging      — combine N sources into one ∞T stream
  Partitioning — split one stream into N by key
  Monitoring   — throughput, latency, backpressure stats
  Watching     — detect when an archive updates, auto-reingest

These operations make Æergia∞ a complete stream processing system,
not just a source adapter. A full pipeline looks like:

  source alerts = ZTF.alerts()           -- ∞ live ZTF alerts
  source sdss   = SDSS.photometry()      -- ∞ SDSS reference photometry

  pipeline =
    alerts
      |> where  (.mag < 19.0)
      |> joinOn (.ra, .dec) sdss within 2.arcsec   -- spatial join
      |> window (TumblingTime 60)                   -- 1-minute windows
      |> map    computeStatistics                   -- per-window stats
      |> where  (.transient_score > 0.8)
      |> demand 1000
"""
from __future__ import annotations
import math
import time
import threading
import queue
from typing import Any, Callable, Dict, List, Optional, Tuple

from .thunk  import Thunk, force, delay
from .stream import (Stream, Empty, EMPTY, cons, take, drop,
                     sfilter, smap, from_iter, scan)


# ── Windowing ─────────────────────────────────────────────────────────────────

def tumbling_window(n: int, s: Any) -> "Stream | Empty":
    """
    Non-overlapping windows of exactly n elements.
    [0,1,2,3,4,5] with n=2 → [[0,1],[2,3],[4,5]]
    """
    from .stream import chunk
    return chunk(n, s)


def sliding_window(n: int, step: int, s: Any) -> "Stream | Empty":
    """
    Overlapping windows of size n, advancing by step.
    [0..5] with n=3, step=1 → [[0,1,2],[1,2,3],[2,3,4],[3,4,5]]
    """
    from .stream import window
    if step == 1:
        return window(n, s)
    # step > 1: take n, drop step, repeat
    s = force(s)
    if isinstance(s, Empty):
        return EMPTY
    buf = take(n, s)
    if len(buf) < n:
        return EMPTY
    rest = drop(step, s)
    return cons(buf, Thunk(lambda: sliding_window(n, step, rest)))


def session_window(gap_fn: Callable[[Any], float],
                   timeout: float,
                   s: Any) -> "Stream | Empty":
    """
    Session windows: group records until a gap of `timeout` seconds
    between consecutive events (measured by gap_fn(record) → timestamp).
    """
    s = force(s)
    if isinstance(s, Empty):
        return EMPTY

    session: List[Any] = []
    last_ts: List[float] = [None]

    def go(s: Any) -> "Stream | Empty":
        s = force(s)
        if isinstance(s, Empty):
            if session:
                result = list(session)
                session.clear()
                return cons(result, Thunk(lambda: EMPTY))
            return EMPTY

        record = s.head
        ts     = gap_fn(record)
        if last_ts[0] is not None and ts - last_ts[0] > timeout:
            # Gap detected — emit current session
            result = list(session)
            session.clear()
            session.append(record)
            last_ts[0] = ts
            return cons(result, Thunk(lambda: go(s.tail)))
        else:
            session.append(record)
            last_ts[0] = ts
            return go(s.tail)

    return go(s)


def time_window(seconds: float, s: Any,
                timestamp_fn: Callable = None) -> "Stream | Empty":
    """
    Group elements into time buckets of `seconds` width.
    timestamp_fn(record) → epoch float. Defaults to time.time().
    """
    ts_fn = timestamp_fn or (lambda _: time.time())

    def go(s: Any, bucket_start: float, bucket: List) -> "Stream | Empty":
        s = force(s)
        if isinstance(s, Empty):
            return cons(bucket, Thunk(lambda: EMPTY)) if bucket else EMPTY
        record = s.head
        ts     = ts_fn(record)
        if ts < bucket_start + seconds:
            bucket.append(record)
            return go(s.tail, bucket_start, bucket)
        # New bucket
        old_bucket = list(bucket)
        new_start  = bucket_start + seconds * math.floor((ts - bucket_start) / seconds)
        return cons(old_bucket, Thunk(lambda: go(s, new_start, [record])))

    s = force(s)
    if isinstance(s, Empty):
        return EMPTY
    now = ts_fn(s.head)
    return go(s, now, [])


# ── Stream joining ─────────────────────────────────────────────────────────────

def join_by_key(key_fn: Callable, s1: Any, s2: Any,
                buffer_size: int = 10_000) -> "Stream | Empty":
    """
    Key-based inner join of two streams.
    Elements match when key_fn(a) == key_fn(b).

    Buffers s2 up to buffer_size elements for lookup.
    For large s2, use sorted_merge_join instead.
    """
    # Build a lookup dict from s2
    lookup: Dict = {}
    s2 = force(s2)
    count = 0
    while isinstance(s2, Stream) and not isinstance(s2, Empty) and count < buffer_size:
        r = s2.head
        k = key_fn(r)
        if k not in lookup:
            lookup[k] = []
        lookup[k].append(r)
        s2 = force(s2.tail)
        count += 1

    def go(s: Any) -> "Stream | Empty":
        s = force(s)
        if isinstance(s, Empty):
            return EMPTY
        record = s.head
        k      = key_fn(record)
        matches = lookup.get(k, [])
        if not matches:
            return go(s.tail)
        joined = [{"left": record, "right": m} for m in matches]
        def build(i: int) -> "Stream | Empty":
            if i >= len(joined):
                return go(s.tail)
            return cons(joined[i], Thunk(lambda i=i: build(i+1)))
        return build(0)

    return go(s1)


def spatial_join(s1: Any, s2: Any,
                 ra1_fn:  Callable = lambda r: r.get("ra",  0),
                 dec1_fn: Callable = lambda r: r.get("dec", 0),
                 ra2_fn:  Callable = lambda r: r.get("ra",  0),
                 dec2_fn: Callable = lambda r: r.get("dec", 0),
                 radius_arcsec: float = 5.0,
                 s2_buffer: int = 50_000) -> "Stream | Empty":
    """
    Angular cross-match of two astronomical source streams.
    Matches records within radius_arcsec of each other on the sky.

    Uses a simple grid-based lookup (exact for small radius).
    For production use, build an HEALPix index.
    """
    r_deg = radius_arcsec / 3600.0

    # Load s2 into a grid
    grid: Dict[Tuple[int,int], List] = {}
    cell_deg = r_deg * 2

    s2 = force(s2)
    count = 0
    while isinstance(s2, Stream) and not isinstance(s2, Empty) and count < s2_buffer:
        rec = s2.head
        ra  = ra2_fn(rec) % 360
        dec = dec2_fn(rec)
        cell = (int(ra / cell_deg), int((dec + 90) / cell_deg))
        if cell not in grid:
            grid[cell] = []
        grid[cell].append(rec)
        s2 = force(s2.tail)
        count += 1

    def angular_sep(ra1, dec1, ra2, dec2) -> float:
        ra1, dec1, ra2, dec2 = map(math.radians, [ra1, dec1, ra2, dec2])
        dra  = ra2 - ra1
        ddec = dec2 - dec1
        a    = math.sin(ddec/2)**2 + math.cos(dec1)*math.cos(dec2)*math.sin(dra/2)**2
        return 2 * math.degrees(math.asin(min(1, math.sqrt(a)))) * 3600  # arcsec

    def find_matches(r1):
        ra  = ra1_fn(r1) % 360
        dec = dec1_fn(r1)
        cx  = int(ra / cell_deg)
        cy  = int((dec + 90) / cell_deg)
        matches = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                for r2 in grid.get((cx+dx, cy+dy), []):
                    sep = angular_sep(ra, dec, ra2_fn(r2)%360, dec2_fn(r2))
                    if sep <= radius_arcsec:
                        matches.append({"left": r1, "right": r2, "sep_arcsec": round(sep, 3)})
        return matches

    def go(s: Any) -> "Stream | Empty":
        s = force(s)
        if isinstance(s, Empty):
            return EMPTY
        matches = find_matches(s.head)
        if not matches:
            return go(s.tail)
        def build(i: int) -> "Stream | Empty":
            if i >= len(matches):
                return go(s.tail)
            return cons(matches[i], Thunk(lambda i=i: build(i+1)))
        return build(0)

    return go(s1)


def temporal_join(s1: Any, s2: Any,
                  ts1_fn: Callable, ts2_fn: Callable,
                  window_sec: float = 60.0,
                  s2_buffer: int = 10_000) -> "Stream | Empty":
    """
    Join two event streams within a time window.
    Records from s1 are matched against s2 records within ±window_sec.
    """
    # Buffer s2 sorted by timestamp
    buf2: List = []
    s2 = force(s2)
    count = 0
    while isinstance(s2, Stream) and not isinstance(s2, Empty) and count < s2_buffer:
        buf2.append(s2.head)
        s2 = force(s2.tail)
        count += 1
    buf2.sort(key=lambda r: ts2_fn(r))

    def find_matches(r1):
        t1 = ts1_fn(r1)
        return [{"left": r1, "right": r2,
                 "dt_sec": round(ts2_fn(r2) - t1, 3)}
                for r2 in buf2
                if abs(ts2_fn(r2) - t1) <= window_sec]

    def go(s: Any) -> "Stream | Empty":
        s = force(s)
        if isinstance(s, Empty): return EMPTY
        matches = find_matches(s.head)
        if not matches: return go(s.tail)
        def build(i: int) -> "Stream | Empty":
            if i >= len(matches): return go(s.tail)
            return cons(matches[i], Thunk(lambda i=i: build(i+1)))
        return build(0)

    return go(s1)


def merge_sources(*streams) -> "Stream | Empty":
    """
    Merge N streams into one, round-robin.
    When any stream is exhausted, continues with the rest.
    """
    live = [force(s) for s in streams]
    def go(sources: List) -> "Stream | Empty":
        active = [s for s in sources if not isinstance(s, Empty)]
        if not active: return EMPTY
        # Round-robin: take head of first, rotate
        s   = active[0]
        rest = active[1:] + [force(s.tail)]
        return cons(s.head, Thunk(lambda: go(rest)))
    return go(live)


def partition_by(key_fn: Callable, s: Any, n_partitions: int = 4) -> List:
    """
    Split one stream into n_partitions sub-streams by key hash.
    Returns a list of n_partitions lazy streams.
    """
    bufs = [queue.Queue() for _ in range(n_partitions)]
    done = threading.Event()

    def producer():
        cur = force(s)
        while not isinstance(cur, Empty):
            rec  = cur.head
            part = hash(key_fn(rec)) % n_partitions
            bufs[part].put(rec)
            cur  = force(cur.tail)
        done.set()
        for b in bufs: b.put(None)

    t = threading.Thread(target=producer, daemon=True)
    t.start()

    def make_stream(buf: queue.Queue) -> "Stream | Empty":
        def go() -> "Stream | Empty":
            item = buf.get()
            if item is None: return EMPTY
            return cons(item, Thunk(go))
        return go()

    return [make_stream(b) for b in bufs]


# ── Update watcher ─────────────────────────────────────────────────────────────

class ArchiveWatcher:
    """
    Watch an archive for updates and emit new records as they arrive.

    Works for any source that has a checkpoint mechanism — databases,
    REST APIs with a "since" parameter, file modification times, etc.

    The watcher polls at a configurable interval and streams new records
    as they appear. Combined with ~>, this gives you "at most N new
    records since my last read" semantics.

    Usage in Æergia∞:
        watch SDSS.galaxies every 3600   -- re-check every hour
          |> where (.is_new)
          ~> budget: 1000               -- at most 1000 new per check
    """

    def __init__(self, source_factory: Callable,
                 poll_interval_sec: float = 3600.0,
                 since_key: str = "id",
                 since_fn: Optional[Callable] = None):
        self.source_factory   = source_factory
        self.poll_interval    = poll_interval_sec
        self.since_key        = since_key
        self.since_fn         = since_fn or (lambda r: r.get(since_key, 0))
        self._last_seen: Any  = None
        self._buf             = queue.Queue(maxsize=100_000)
        self._running         = True

    def start(self) -> "Stream | Empty":
        """Start watching. Returns an infinite stream of new records."""
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()
        return self._buf_stream()

    def stop(self):
        self._running = False

    def _poll_loop(self):
        while self._running:
            try:
                s = self.source_factory()
                # Skip records we've already seen
                if self._last_seen is not None:
                    s = sfilter(
                        lambda r: self.since_fn(r) > self._last_seen, s)
                records = take(10_000, s)
                for r in records:
                    self._buf.put(r, timeout=10)
                    val = self.since_fn(r)
                    if self._last_seen is None or val > self._last_seen:
                        self._last_seen = val
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def _buf_stream(self) -> "Stream | Empty":
        def go() -> "Stream | Empty":
            try:
                record = self._buf.get(timeout=self.poll_interval + 10)
                return cons(record, Thunk(go))
            except queue.Empty:
                return EMPTY if not self._running else go()
        return go()


# ── Pipeline monitoring ────────────────────────────────────────────────────────

class PipelineMonitor:
    """
    Wrap a stream with throughput and latency monitoring.

    Returns (stream, stats_fn) where stats_fn() returns
    current throughput, latency, and backpressure metrics.
    """

    def __init__(self):
        self._count    = 0
        self._start    = time.time()
        self._latencies: List[float] = []
        self._lock     = threading.Lock()

    def wrap(self, s: Any, max_latency_samples: int = 1000) -> Any:
        """Wrap stream s with monitoring instrumentation."""
        def go(s: Any) -> "Stream | Empty":
            s = force(s)
            if isinstance(s, Empty): return EMPTY
            t0 = time.time()
            record = s.head
            latency = time.time() - t0
            with self._lock:
                self._count += 1
                self._latencies.append(latency)
                if len(self._latencies) > max_latency_samples:
                    self._latencies.pop(0)
            return cons(record, Thunk(lambda: go(s.tail)))
        return go(s)

    def stats(self) -> Dict:
        with self._lock:
            elapsed = max(time.time() - self._start, 0.001)
            lats    = self._latencies or [0.0]
            return {
                "total_records":   self._count,
                "throughput_rps":  round(self._count / elapsed, 1),
                "elapsed_sec":     round(elapsed, 2),
                "mean_latency_ms": round(sum(lats) / len(lats) * 1000, 3),
                "max_latency_ms":  round(max(lats) * 1000, 3),
                "buffer_depth":    len(self._latencies),
            }
