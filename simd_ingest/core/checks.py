"""Structured check results, shared by the CLI and later by Dagster asset checks.

A check is blocking or diagnostic. Blocking failures stop the build before anything is
written. Diagnostic differences are recorded and reported, never enforced.
"""

from __future__ import annotations

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
