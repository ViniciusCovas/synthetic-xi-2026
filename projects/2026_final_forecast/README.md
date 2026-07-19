# Spain vs Argentina — 2026 World Cup Final Forecast

Pre-match, reproducible probabilistic forecast generated before kick-off on 19 July 2026.

## Main result

- Spain win after 90 minutes: **45.7%**
- Draw after 90 minutes: **28.5%**
- Argentina win after 90 minutes: **25.8%**
- Spain lifts the trophy: **61.4%**
- Argentina lifts the trophy: **38.6%**
- Most common regulation score: **Spain 1–0 Argentina (14.2%)**

This is a calibrated probabilistic forecast, not proof of the future result.

## Reproduce

```bash
python projects/2026_final_forecast/forecast_model.py
```

The script reads `data/processed/fixtures.csv` and verifies the frozen source snapshot documented in `forecast_results.json`.

## Files

- `forecast_model.py`: executable model.
- `forecast_results.json`: machine-readable forecast.
- `METHOD.md`: design, assumptions and claim limits.
- `model_tuning.csv`: chronological holdout comparison.
- `top_scorelines.csv`: most probable regulation scorelines.
- `social_copy_en.md`: English reel copy and caption.
