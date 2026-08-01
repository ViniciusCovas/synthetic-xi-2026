# Clean-room reproduction — Official Experiment v1

- Status: **PASS**
- All frozen manifest artifacts byte-identical: **yes**
- Manifest artifacts checked: **15**
- Candidate simulations: **10000**
- Candidate master seed: **`2026073001`**
- Synthetic XI champion probability: **44.5900%**
- Real Best XI champion probability: **55.4100%**
- Environment lock SHA-256: `b81cdd2b578f8d60cef6971f2eeaa02fa8b159d72e1c557ee6daf26772e21f7f`

## Audit scope

The audit was executed in a fresh GitHub-hosted Ubuntu environment with a new Python 3.12 installation and dependencies installed without a pip cache. It regenerated the preregistered 10,000-run official experiment from the frozen code and seed. Every candidate artifact was checked against the SHA-256 recorded in the frozen manifest, including full match and state tables that are retained in the immutable experiment package rather than versioned individually in Git.

## Failed summary checks

- None

## Failed files

- None

## Interpretation

The independently regenerated 10,000-run official experiment reproduced every artifact hash recorded in the frozen manifest, together with the primary estimands and H5-H7 outputs.
