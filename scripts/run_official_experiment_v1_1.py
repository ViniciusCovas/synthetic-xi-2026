#!/usr/bin/env python3
"""Canonical launcher for official_v1 with paired orientation equivalence.

This launcher preserves the audited experiment runner while replacing only its
orientation diagnostic dependency with the preregistered confidence-interval
equivalence implementation in ``simulator.official_orientation``.
"""
from __future__ import annotations

import scripts.run_official_experiment as runner
from simulator.official_orientation import paired_orientation_diagnostic

runner.paired_orientation_diagnostic = paired_orientation_diagnostic

if __name__ == "__main__":
    runner.main()
