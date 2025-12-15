from dataclasses import dataclass


@dataclass
class _FakeButton:
    aria: str
    href: str | None = None

    def get_attribute(self, name: str):
        if name == "aria-label":
            return self.aria
        return None

    def locator(self, selector: str):
        # Used by code: button.locator("xpath=ancestor::article").first.locator("a").first.get_attribute("href")
        return self

    @property
    def first(self):
        return self

    def inner_text(self, *args, **kwargs):
        return ""

    def click(self, *args, **kwargs):
        return None


class _FakeLink:
    def __init__(self, href: str | None):
        self._href = href

    @property
    def first(self):
        return self

    def get_attribute(self, name: str):
        if name == "href":
            return self._href
        return None


class _FakeArticle:
    def __init__(self, href: str | None):
        self._href = href

    @property
    def first(self):
        return self

    def locator(self, selector: str):
        # selector "a"
        return _FakeLink(self._href)


class _FakeButtonWithAncestor(_FakeButton):
    def locator(self, selector: str):
        if selector == "xpath=ancestor::article":
            return _FakeArticle(self.href)
        return super().locator(selector)


class _FakeLocator:
    def __init__(self, buttons):
        self._buttons = buttons

    def all(self):
        return self._buttons


class _FakePage:
    def __init__(self, buttons):
        self._buttons = buttons
        self.calls = []

        class _Keyboard:
            def __init__(self, outer):
                self._outer = outer

            def press(self, key: str):
                self._outer.calls.append(("key", key))

        self.keyboard = _Keyboard(self)

    def goto(self, url: str, *args, **kwargs):
        self.calls.append(("goto", url))

    def locator(self, selector: str):
        self.calls.append(("locator", selector))
        return _FakeLocator(self._buttons)


def test_search_parses_add_to_cart_labels_and_urls():
    from grocery.tools.hyvee import search

    buttons = [
        _FakeButtonWithAncestor(
            aria="Add to cart, Hy-Vee Vitamin D Milk $5.29 1 gal",
            href="/aisles-online/p/12345/something",
        ),
        _FakeButtonWithAncestor(
            aria="Add to cart, Hy-Vee White Bread $1.99 20 oz",
            href="https://www.hy-vee.com/aisles-online/p/9999/other",
        ),
    ]
    page = _FakePage(buttons)
    results = search(page, query="milk", limit=5)

    assert len(results) == 2
    assert results[0].name == "Hy-Vee Vitamin D Milk"
    assert results[0].price == "$5.29"
    assert results[0].product_id == "12345"
    assert results[0].url.startswith("https://www.hy-vee.com/")

    assert results[1].name == "Hy-Vee White Bread"
    assert results[1].price == "$1.99"
    assert results[1].product_id == "9999"
    assert results[1].url == "https://www.hy-vee.com/aisles-online/p/9999/other"


