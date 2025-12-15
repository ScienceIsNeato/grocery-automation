from grocery.tools.errors import GroceryError, unknown_item


def test_error_format_includes_code_context_next_step():
    err = GroceryError(code=11, short="x", context="c", next_step="n")
    s = err.format()
    assert "ERROR [11]" in s
    assert "Context: c" in s
    assert "Next step: n" in s


def test_unknown_item_error_has_code_1():
    err = unknown_item("milk", "https://example/search?milk")
    assert err.code == 1
    assert "Unknown" in err.short


