"""Statistics for profiles, leaderboards and reports (sections 11.4, 16.3, 16.6).

* Success rate is escapes over certified runs.
* Its 95% interval comes from resampling instances, because runs on one
  instance are not independent. With few instances a percentile bootstrap can
  collapse to a single point (10 escapes on 10 instances gives [100%, 100%]),
  which overclaims, so the interval is widened to at least the Wilson score
  interval computed with the number of instances as the sample size.
* pass^3 is the share of instances where all three runs escaped, borrowed
  from tau-bench. Only instances with at least three runs count.
* Rank bands: agents whose intervals overlap heavily share a band instead of
  a false strict order.

Everything is deterministic: the bootstrap uses a fixed seeded stream.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from statistics import median
from typing import Any

from .rng import SeededRandom

Z95 = 1.959963984540054


def wilson(k: float, n: float, z: float = Z95) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def cluster_bootstrap(results: dict[str, list[bool]], resamples: int = 2000, seed: str = "escapement-bootstrap") -> tuple[float, float]:
    keys = sorted(k for k, v in results.items() if v)
    if not keys:
        return 0.0, 1.0
    rng = SeededRandom(seed, str(len(keys)))
    totals = [(sum(results[k]), len(results[k])) for k in keys]
    rates = []
    n = len(keys)
    for _ in range(resamples):
        esc = runs = 0
        for _ in range(n):
            e, r = totals[rng.below(n)]
            esc += e
            runs += r
        rates.append(esc / runs)
    rates.sort()
    lo = rates[int(0.025 * (resamples - 1))]
    hi = rates[int(math.ceil(0.975 * (resamples - 1)))]
    return lo, hi


@dataclass
class RateSummary:
    runs: int
    escapes: int
    instances: int
    rate: float | None
    ci_low: float | None
    ci_high: float | None
    pass3: float | None
    pass3_instances: int
    median_actions_success: float | None
    method: str = "instance bootstrap, widened to Wilson on instance count"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize(results: dict[str, list[tuple[bool, int]]], resamples: int = 2000) -> RateSummary:
    """`results` maps instance id -> list of (escaped, actions_used) per run."""
    flat = {k: [e for e, _ in v] for k, v in results.items() if v}
    runs = sum(len(v) for v in flat.values())
    escapes = sum(sum(v) for v in flat.values())
    if runs == 0:
        return RateSummary(0, 0, 0, None, None, None, None, 0, None)
    b_lo, b_hi = cluster_bootstrap(flat, resamples=resamples)
    per_instance = [sum(v) / len(v) for v in flat.values()]
    w_lo, w_hi = wilson(sum(per_instance), len(per_instance))
    p3, p3n = pass_k(flat, 3)
    actions = [a for v in results.values() for e, a in v if e]
    return RateSummary(
        runs=runs,
        escapes=escapes,
        instances=len(flat),
        rate=escapes / runs,
        ci_low=min(b_lo, w_lo),
        ci_high=max(b_hi, w_hi),
        pass3=p3,
        pass3_instances=p3n,
        median_actions_success=float(median(actions)) if actions else None,
    )


def pass_k(results: dict[str, list[bool]], k: int = 3) -> tuple[float | None, int]:
    eligible = [v[:k] for v in results.values() if len(v) >= k]
    if not eligible:
        return None, 0
    return sum(all(v) for v in eligible) / len(eligible), len(eligible)


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def rank_bands(rows: Iterable[tuple[str, float, float, float]], heavy: float = 0.5) -> dict[str, int]:
    """rows: (id, rate, ci_low, ci_high). An agent joins the current band when
    its interval overlaps the band leader's by at least `heavy` of the narrower
    interval's width (or contains the leader's estimate)."""
    ordered = sorted(rows, key=lambda r: (-r[1], r[0]))
    bands: dict[str, int] = {}
    band = 0
    leader: tuple[str, float, float, float] | None = None
    for row in ordered:
        if leader is None:
            band = 1
            leader = row
        else:
            li, ri = (leader[2], leader[3]), (row[2], row[3])
            narrow = max(1e-9, min(li[1] - li[0], ri[1] - ri[0]))
            same = _overlap(li, ri) >= heavy * narrow or ri[0] <= leader[1] <= ri[1]
            if not same:
                band += 1
                leader = row
        bands[row[0]] = band
    return bands


def floor_pct(x: float | None, digits: int = 1) -> str:
    """Format a share as a percentage, never rounding upward (14.4)."""
    if x is None:
        return "n/a"
    f = 10**digits
    return f"{math.floor(x * 100 * f + 1e-9) / f:.{digits}f}%"


def ceil_pct(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "n/a"
    f = 10**digits
    return f"{math.ceil(x * 100 * f - 1e-9) / f:.{digits}f}%"


def interval_text(lo: float | None, hi: float | None) -> str:
    """Intervals are widened outward when rounded, never narrowed."""
    return f"{floor_pct(lo)}–{ceil_pct(hi)}"
