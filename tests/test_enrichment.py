from datetime import datetime, timezone

from scripts.enrichment.common import choose_geocode_result, nearest_time_index, slug


def test_slug_normalizes_accents_and_symbols():
    assert slug("México City") == "mexico-city"


def test_nearest_time_index():
    times = ["2026-06-11T18:00+00:00", "2026-06-11T19:00+00:00", "2026-06-11T20:00+00:00"]
    target = datetime(2026, 6, 11, 19, 20, tzinfo=timezone.utc)
    assert nearest_time_index(times, target) == 1


def test_choose_geocode_result_prefers_country_and_exact_city():
    results = [
        {"name": "Guadalajara", "country": "Spain", "population": 85000},
        {"name": "Guadalajara", "country": "Mexico", "population": 1495000},
    ]
    assert choose_geocode_result(results, "Guadalajara", "Mexico")["country"] == "Mexico"
