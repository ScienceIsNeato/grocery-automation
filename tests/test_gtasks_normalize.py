from grocery.tools import gtasks


def test_normalize_applies_corrections_exact_match():
    subs = {
        "corrections": {
            "your souls": "yasso bars",
        },
        "defaults": {},
    }
    out = gtasks.normalize(items=["your souls"], substitutions=subs)
    assert out == [{"original": "your souls", "normalized": "yasso bars", "quantity": 1}]


def test_normalize_applies_defaults_exact_match():
    subs = {
        "corrections": {},
        "defaults": {"orange juice": "Tropicana Lite 50"},
    }
    out = gtasks.normalize(items=["orange juice"], substitutions=subs)
    assert out == [{"original": "orange juice", "normalized": "Tropicana Lite 50", "quantity": 1}]


def test_normalize_strips_and_lowercases_before_lookup():
    subs = {
        "corrections": {"milk": "milk"},
        "defaults": {},
    }
    out = gtasks.normalize(items=["  MILK  "], substitutions=subs)
    assert out == [{"original": "  MILK  ", "normalized": "milk", "quantity": 1}]


def test_normalize_extracts_leading_quantity():
    subs = {"corrections": {}, "defaults": {}}
    out = gtasks.normalize(items=["2 bananas"], substitutions=subs)
    assert out == [{"original": "2 bananas", "normalized": "bananas", "quantity": 2}]


def test_normalize_parses_dozen_quantity():
    subs = {"corrections": {}, "defaults": {}}
    out = gtasks.normalize(items=["2 dozen eggs"], substitutions=subs)
    assert out == [{"original": "2 dozen eggs", "normalized": "eggs", "quantity": 24}]


def test_normalize_drops_empty_items():
    subs = {"corrections": {}, "defaults": {}}
    out = gtasks.normalize(items=["", "   "], substitutions=subs)
    assert out == []


