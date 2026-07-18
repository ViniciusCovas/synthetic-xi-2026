from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_xi_2026.roles import infer_starting_roles


def test_433_role_inference():
    lineup = {
        "formation": "4-3-3",
        "startXI": [
            {"player": {"id": 1, "name": "GK", "pos": "G", "grid": "1:1"}},
            {"player": {"id": 2, "name": "RB", "pos": "D", "grid": "2:1"}},
            {"player": {"id": 3, "name": "CB1", "pos": "D", "grid": "2:2"}},
            {"player": {"id": 4, "name": "CB2", "pos": "D", "grid": "2:3"}},
            {"player": {"id": 5, "name": "LB", "pos": "D", "grid": "2:4"}},
            {"player": {"id": 6, "name": "M1", "pos": "M", "grid": "3:1"}},
            {"player": {"id": 7, "name": "M2", "pos": "M", "grid": "3:2"}},
            {"player": {"id": 8, "name": "M3", "pos": "M", "grid": "3:3"}},
            {"player": {"id": 9, "name": "RW", "pos": "F", "grid": "4:1"}},
            {"player": {"id": 10, "name": "ST", "pos": "F", "grid": "4:2"}},
            {"player": {"id": 11, "name": "LW", "pos": "F", "grid": "4:3"}},
        ],
    }
    roles = infer_starting_roles(lineup)
    assert roles[1]["position_group"] == "GK"
    assert roles[2]["position_group"] == "FB"
    assert roles[3]["position_group"] == "CB"
    assert roles[7]["position_group"] == "CM"
    assert roles[9]["position_group"] == "W"
    assert roles[10]["position_group"] == "ST"


def test_433_midfield_edges_remain_central_midfielders():
    lineup = {
        "formation": "4-3-3",
        "startXI": [
            {"player": {"id": 1, "pos": "G", "grid": "1:1"}},
            {"player": {"id": 2, "pos": "D", "grid": "2:1"}},
            {"player": {"id": 3, "pos": "D", "grid": "2:2"}},
            {"player": {"id": 4, "pos": "D", "grid": "2:3"}},
            {"player": {"id": 5, "pos": "D", "grid": "2:4"}},
            {"player": {"id": 6, "pos": "M", "grid": "3:1"}},
            {"player": {"id": 7, "pos": "M", "grid": "3:2"}},
            {"player": {"id": 8, "pos": "M", "grid": "3:3"}},
            {"player": {"id": 9, "pos": "F", "grid": "4:1"}},
            {"player": {"id": 10, "pos": "F", "grid": "4:2"}},
            {"player": {"id": 11, "pos": "F", "grid": "4:3"}},
        ],
    }
    roles = infer_starting_roles(lineup)
    assert {roles[i]["position_group"] for i in (6, 7, 8)} == {"CM"}


def test_back_three_wide_midfielders_are_wingbacks():
    lineup = {
        "formation": "3-4-3",
        "startXI": [
            {"player": {"id": 1, "pos": "G", "grid": "1:1"}},
            {"player": {"id": 2, "pos": "D", "grid": "2:1"}},
            {"player": {"id": 3, "pos": "D", "grid": "2:2"}},
            {"player": {"id": 4, "pos": "D", "grid": "2:3"}},
            {"player": {"id": 5, "pos": "M", "grid": "3:1"}},
            {"player": {"id": 6, "pos": "M", "grid": "3:2"}},
            {"player": {"id": 7, "pos": "M", "grid": "3:3"}},
            {"player": {"id": 8, "pos": "M", "grid": "3:4"}},
            {"player": {"id": 9, "pos": "F", "grid": "4:1"}},
            {"player": {"id": 10, "pos": "F", "grid": "4:2"}},
            {"player": {"id": 11, "pos": "F", "grid": "4:3"}},
        ],
    }
    roles = infer_starting_roles(lineup)
    assert roles[5]["position_group"] == "FB"
    assert roles[8]["position_group"] == "FB"
    assert roles[6]["position_group"] == "CM"
