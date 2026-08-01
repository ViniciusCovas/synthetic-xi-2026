"""Football simulation package with fail-closed official_v1 runtime policy."""

from .engine import MatchSimulator, SimulationConfig, simulate_many

# Official v1 is patched at the package boundary so every consumer—runner,
# validator, test or sensitivity analysis—receives the same frozen real-player,
# roster and emergency-substitution policy.
from . import official_profile_sensitivity as _official_profile_sensitivity
from . import official_profiles as _official_profiles
from .official_frozen_runtime import (
    build_official_bundles as _build_official_bundles,
    build_official_bundles_with_role_variant as _build_with_role_variant,
    compatible_reserves as _compatible_reserves,
)

_official_profiles.build_official_bundles = _build_official_bundles
_official_profiles.compatible_reserves = _compatible_reserves
_official_profile_sensitivity.build_official_bundles_with_role_variant = (
    _build_with_role_variant
)

__all__ = ["MatchSimulator", "SimulationConfig", "simulate_many"]
