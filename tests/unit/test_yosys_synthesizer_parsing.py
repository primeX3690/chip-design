"""Cell-count parsing must handle old + new Yosys `stat` formats and never default silently to 0."""
from evohdl.sandbox.yosys_synthesizer import parse_cell_count

OLD = "=== alu ===\n   Number of wires:   44\n   Number of cells:  1409\n"
NEW = "=== alu ===\n\n        44 wires\n      1318 cells\n"


def test_old_format():
    assert parse_cell_count(OLD) == 1409


def test_new_format():
    assert parse_cell_count(NEW) == 1318


def test_missing_is_none_not_zero():
    assert parse_cell_count("unrelated yosys log") is None
