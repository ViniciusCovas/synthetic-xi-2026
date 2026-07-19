#!/usr/bin/env python3
from pathlib import Path
import scripts.run_targeted_coverage_extraction as extractor
extractor.PRIORITY_PATH=Path('data/model_readiness/selection_sufficiency_priority_fixtures.csv')
if __name__=='__main__': extractor.main()
