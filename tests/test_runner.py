"""run_capped — the hard-cap chokepoint.

Pins: a plain callable returns its result; a call exceeding the wall-clock budget
raises TimeoutError.
"""

from __future__ import annotations

import time

import pytest

from house_harness.agents.runner import Caps, run_capped


def test_plain_callable_returns_result():
    assert run_capped(lambda p: "ok", "hi") == "ok"


def test_timeout_raises():
    def slow(_prompt):
        time.sleep(1)
        return "too late"

    with pytest.raises(TimeoutError):
        run_capped(slow, "hi", caps=Caps(timeout_s=0.2))
