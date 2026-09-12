"""Structured checks and non-gating observations for the build report.

Every check is blocking. Descriptive release facts are observations, not pass/fail checks.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import numpy as np


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
    detail: str
    expected: object = None
    actual: object = None


@dataclass
class Report:
    checks: list = field(default_factory=list)
    observations: dict = field(default_factory=dict)

    def observe(self, name, value):
        self.observations[name] = _plain(value)

    def add(self, name, passed, detail="", expected=None, actual=None) -> bool:
        self.checks.append(Check(name, bool(passed), detail, _plain(expected), _plain(actual)))
        return bool(passed)

    def equal(self, name, actual, expected, detail="") -> bool:
        passed = bool(actual == expected)
        if not detail:
            detail = f"{actual}" if passed else f"expected {str(expected)[:200]}, got {str(actual)[:200]}"
        return self.add(name, passed, detail, expected, actual)

    @property
    def blocking_failures(self):
        return [c for c in self.checks if not c.passed]

    def require(self):
        """Raise if any blocking check has failed."""
        failed = self.blocking_failures
        if failed:
            first = failed[0]
            raise BuildStopped(f"{len(failed)} blocking check(s) failed; first: {first.name}: {first.detail}")

    def summary(self) -> dict:
        return {
            "checks": len(self.checks),
            "blocking_passed": sum(1 for c in self.checks if c.passed),
            "blocking_failed": len(self.blocking_failures),
        }

    def to_records(self) -> list:
        return [asdict(c) for c in self.checks]
