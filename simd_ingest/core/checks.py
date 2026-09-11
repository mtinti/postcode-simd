"""Structured check results, shared by the CLI and later by Dagster asset checks.

A check is blocking or diagnostic. Blocking failures stop the build before anything is
written. Diagnostic differences are recorded and reported, never enforced.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

BLOCKING = "blocking"
DIAGNOSTIC = "diagnostic"


class BuildStopped(Exception):
    """A blocking check failed."""


def _plain(value):
    """Make a value JSON-serialisable for the manifest."""
    if value is None:
        return None
    return json.loads(json.dumps(value, default=lambda x: x.item() if isinstance(x, np.generic) else str(x)))


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    severity: str
    detail: str
    expected: object = None
    actual: object = None


@dataclass
class Report:
    checks: list = field(default_factory=list)

    def add(self, name, passed, detail="", severity=BLOCKING, expected=None, actual=None) -> bool:
        self.checks.append(Check(name, bool(passed), severity, detail, _plain(expected), _plain(actual)))
        return bool(passed)

    def equal(self, name, actual, expected, severity=BLOCKING, detail="") -> bool:
        passed = bool(actual == expected)
        if not detail:
            detail = f"{actual}" if passed else f"expected {str(expected)[:200]}, got {str(actual)[:200]}"
        return self.add(name, passed, detail, severity, expected, actual)

    @property
    def blocking_failures(self):
        return [c for c in self.checks if c.severity == BLOCKING and not c.passed]

    @property
    def diagnostic_differences(self):
        return [c for c in self.checks if c.severity == DIAGNOSTIC and not c.passed]

    def require(self):
        """Raise if any blocking check has failed."""
        failed = self.blocking_failures
        if failed:
            first = failed[0]
            raise BuildStopped(f"{len(failed)} blocking check(s) failed; first: {first.name}: {first.detail}")

    def summary(self) -> dict:
        return {
            "checks": len(self.checks),
            "blocking_passed": sum(1 for c in self.checks if c.severity == BLOCKING and c.passed),
            "blocking_failed": len(self.blocking_failures),
            "diagnostic_agree": sum(1 for c in self.checks if c.severity == DIAGNOSTIC and c.passed),
            "diagnostic_differ": len(self.diagnostic_differences),
        }

    def to_records(self) -> list:
        return [asdict(c) for c in self.checks]


# --- shared numeric checks -------------------------------------------------------------

def divergence(source: pd.Series, published: pd.Series) -> dict:
    """Count and fingerprint the zones where two band series differ.

    The fingerprint is a SHA256 over sorted "zone|source|published" lines, so a baseline
    match proves the same zones differ by the same amounts, not merely the same count.
    """
    if not source.index.is_unique or set(source.index) != set(published.index):
        raise ValueError("Divergence comparison requires the same unique zone universe")
    published = published.reindex(source.index)
    delta = (source - published).abs()
    rows = pd.DataFrame({"source": source, "published": published})[delta.ne(0)].sort_index()
    payload = "\n".join(f"{zone}|{int(a)}|{int(b)}" for zone, a, b in rows.itertuples(index=True, name=None))
    return {"count": len(rows), "max_difference": int(delta.max()) if len(delta) else 0,
            "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}


def reconstruct_population_bands(rank: pd.Series, population: pd.Series, groups: pd.Series) -> pd.DataFrame:
    """Population-weighted bands by the midpoint rule, in exact integer arithmetic.

    Zones are ordered by rank within each group. A zone's band is the band into which the
    midpoint of its population interval falls. This reproduces PHS's published Scotland-level
    deciles and quintiles in every edition; it is a diagnostic, not a source of values.
    """
    frame = pd.DataFrame({"rank": rank, "pop": population.astype("int64"), "group": groups}).sort_values("rank")
    total = frame["pop"].groupby(frame["group"]).transform("sum")
    midpoint2 = 2 * frame["pop"].groupby(frame["group"]).cumsum() - frame["pop"]
    out = pd.DataFrame(index=frame.index)
    for name, k in (("decile", 10), ("quintile", 5)):
        out[name] = ((midpoint2 * k + 2 * total - 1) // (2 * total)).clip(upper=k)
    out["most15pc"] = (midpoint2 * 10 <= total * 3).astype(int)
    out["least15pc"] = (midpoint2 * 10 >= total * 17).astype(int)
    return out.reindex(rank.index)
