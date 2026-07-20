#!/usr/bin/env python3
"""Execute the frozen identified-set design with a prespecified precision budget.

This computational amendment changes only Monte Carlo sample sizes, not the estimand,
team construction, seeds, scenarios, parameter values, decision rule, or outputs.
The budget yields 3,200 matches per plausible Real XI in the primary analysis and
1,000 per plausible Real XI in each sensitivity analysis.
"""
from scripts.scientific import run_identified_set_simulation as simulation

PRIMARY_WORLDS = 40
PRIMARY_MATCHES_PER_ORIENTATION = 40
SENSITIVITY_WORLDS = 20
SENSITIVITY_MATCHES_PER_ORIENTATION = 25

for scenario in simulation.SCENARIOS:
    if scenario["primary"]:
        scenario["worlds"] = PRIMARY_WORLDS
        scenario["matches_per_orientation"] = PRIMARY_MATCHES_PER_ORIENTATION
    else:
        scenario["worlds"] = SENSITIVITY_WORLDS
        scenario["matches_per_orientation"] = SENSITIVITY_MATCHES_PER_ORIENTATION

if __name__ == "__main__":
    simulation.main()
