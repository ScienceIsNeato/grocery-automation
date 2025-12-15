import pytest


class _FakeLocatorAll:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeItem:
    def __init__(self, name: str):
        self._name = name

    def locator(self, selector: str):
        return self

    @property
    def first(self):
        return self

    def inner_text(self, *args, **kwargs):
        return self._name


class _FakePage:
    def __init__(self):
        self.calls = []
        self._items = []

    def goto(self, url: str, *args, **kwargs):
        self.calls.append(("goto", url))

    def locator(self, selector: str):
        self.calls.append(("locator", selector))
        if selector.startswith("article") or "cart-item" in selector:
            return _FakeLocatorAll(self._items)
        raise AssertionError(f"Unexpected selector: {selector}")


def test_get_cart_contents_returns_names():
    from grocery.tools.hyvee import get_cart_contents

    page = _FakePage()
    page._items = [_FakeItem("Hy-Vee Vitamin D Milk"), _FakeItem("Hy-Vee White Bread")]
    items = get_cart_contents(page)
    assert items == ["Hy-Vee Vitamin D Milk", "Hy-Vee White Bread"]


def test_add_to_cart_from_search_returns_false_on_exception(monkeypatch):
    from grocery.tools.hyvee import add_to_cart_from_search

    class _Page:
        def locator(self, selector: str):
            raise RuntimeError("boom")

    assert add_to_cart_from_search(_Page(), add_button_label="x") is False


