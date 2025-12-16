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


def test_ensure_items_in_cart_skips_when_already_present(monkeypatch, tmp_path):
    from grocery.tools import hyvee

    products_path = tmp_path / "products.json"
    products_path.write_text(
        '{"products": {"milk": {"display_name": "Hy-Vee Vitamin D Milk"}}}',
        encoding="utf-8",
    )

    # Cart already contains the item.
    monkeypatch.setattr(hyvee, "get_cart_contents", lambda page: ["Hy-Vee Vitamin D Milk"])

    search_calls: list[tuple] = []
    monkeypatch.setattr(hyvee, "search", lambda page, **kwargs: search_calls.append(("search", kwargs)) or [])
    monkeypatch.setattr(hyvee, "add_to_cart_from_search", lambda page, **kwargs: False)

    hyvee.ensure_items_in_cart(page=object(), products_path=products_path, items=["milk"], unavailable_path=None)
    assert search_calls == []


def test_ensure_items_in_cart_adds_when_missing_and_verifies(monkeypatch, tmp_path):
    from grocery.tools import hyvee

    products_path = tmp_path / "products.json"
    products_path.write_text(
        '{"products": {"milk": {"display_name": "Hy-Vee Vitamin D Milk"}}}',
        encoding="utf-8",
    )

    # Cart is empty initially, then contains item after add.
    cart_snapshots = [[], ["Hy-Vee Vitamin D Milk"]]

    def fake_cart(_page):
        return cart_snapshots.pop(0) if cart_snapshots else ["Hy-Vee Vitamin D Milk"]

    monkeypatch.setattr(hyvee, "get_cart_contents", fake_cart)

    # Search returns a candidate.
    candidate = hyvee.ProductCandidate(
        name="Hy-Vee Vitamin D Milk",
        price="$5.29",
        url="https://www.hy-vee.com/aisles-online/p/12345/x",
        product_id="12345",
        add_button_label="Add to cart, Hy-Vee Vitamin D Milk $5.29 1 gal",
    )
    monkeypatch.setattr(hyvee, "search", lambda page, **kwargs: [candidate])

    add_calls: list[tuple] = []

    def fake_add(_page, **kwargs):
        add_calls.append(("add", kwargs["add_button_label"]))
        return True

    monkeypatch.setattr(hyvee, "add_to_cart_from_search", fake_add)

    hyvee.ensure_items_in_cart(page=object(), products_path=products_path, items=["milk"], unavailable_path=None)
    assert add_calls == [("add", candidate.add_button_label)]


def test_ensure_items_in_cart_logs_unavailable_when_no_results(monkeypatch, tmp_path):
    from grocery.tools import hyvee
    from grocery.tools.errors import GroceryError

    products_path = tmp_path / "products.json"
    products_path.write_text(
        '{"products": {"milk": {"display_name": "Hy-Vee Vitamin D Milk"}}}',
        encoding="utf-8",
    )
    unavailable_path = tmp_path / "unavailable.json"

    # Cart is empty.
    monkeypatch.setattr(hyvee, "get_cart_contents", lambda page: [])
    # Search returns no candidates.
    monkeypatch.setattr(hyvee, "search", lambda page, **kwargs: [])

    with pytest.raises(GroceryError) as excinfo:
        hyvee.ensure_items_in_cart(
            page=object(),
            products_path=products_path,
            items=["milk"],
            unavailable_path=unavailable_path,
        )

    err = excinfo.value
    assert err.code == 10
    assert "search returned no results" in err.short.lower()

    data = unavailable_path.read_text(encoding="utf-8")
    assert '"reason": "not_found"' in data


