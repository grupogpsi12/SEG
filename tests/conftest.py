"""Perfiles de hypothesis: `mutacion` es determinista y mas corto, para que mutmut sea estable."""

import os

from hypothesis import HealthCheck, settings

settings.register_profile(
    "mutacion",
    derandomize=True,
    max_examples=25,
    deadline=None,
    suppress_health_check=list(HealthCheck),
    database=None,
)
settings.register_profile("ci", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
