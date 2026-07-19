from pathlib import Path
import json

RESULT = {
    "seed": 20260719,
    "source": "data/processed/fixtures.csv",
    "source_blob_sha": "e2fa340a1dd3b4678f85f89684fe5b9acc30e6d6",
}

if __name__ == "__main__":
    Path("data/forecasts").mkdir(parents=True, exist_ok=True)
    Path("data/forecasts/spain_argentina_final.json").write_text(json.dumps(RESULT, indent=2))
