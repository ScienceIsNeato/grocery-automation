from grocery.tools import gtasks


def test_normalize_strips_and_lowercases():
    out = gtasks.normalize(items=["  MILK  "])
    assert out == [{"original": "  MILK  ", "normalized": "milk", "quantity": 1}]


def test_normalize_extracts_leading_quantity():
    out = gtasks.normalize(items=["2 bananas"])
    assert out == [{"original": "2 bananas", "normalized": "bananas", "quantity": 2}]


def test_normalize_parses_dozen_quantity():
    out = gtasks.normalize(items=["2 dozen eggs"])
    assert out == [{"original": "2 dozen eggs", "normalized": "eggs", "quantity": 24}]


def test_normalize_parses_single_dozen():
    out = gtasks.normalize(items=["dozen eggs"])
    assert out == [{"original": "dozen eggs", "normalized": "eggs", "quantity": 12}]


def test_normalize_drops_empty_items():
    out = gtasks.normalize(items=["", "   "])
    assert out == []


def test_normalize_preserves_original_case():
    out = gtasks.normalize(items=["Your Souls"])
    assert out == [{"original": "Your Souls", "normalized": "your souls", "quantity": 1}]


