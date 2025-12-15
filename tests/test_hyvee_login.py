import os

import pytest


class _FakeLocator:
    def __init__(self, page, selector: str):
        self._page = page
        self._selector = selector
        self.first = self
        self.last = self

    def click(self, *args, **kwargs):
        self._page.calls.append(("click", self._selector))

    def fill(self, value: str):
        self._page.calls.append(("fill", self._selector, value))

    def is_visible(self, *args, **kwargs):
        # Allow tests to control whether the "Log In" control is visible.
        if 'has-text("Log In")' in self._selector:
            return getattr(self._page, "login_visible", False)
        return False


class _FakePage:
    def __init__(self, html: str, *, login_visible: bool = False):
        self._html = html
        self.login_visible = login_visible
        self.calls: list[tuple] = []

        class _Keyboard:
            def __init__(self, outer):
                self._outer = outer

            def press(self, key: str):
                self._outer.calls.append(("key", key))

        self.keyboard = _Keyboard(self)

    def goto(self, url: str, *args, **kwargs):
        self.calls.append(("goto", url))

    def content(self):
        self.calls.append(("content",))
        return self._html

    def locator(self, selector: str):
        self.calls.append(("locator", selector))
        return _FakeLocator(self, selector)

    def wait_for_selector(self, selector: str, *args, **kwargs):
        self.calls.append(("wait_for_selector", selector))


def test_ensure_logged_in_short_circuits_when_delivery_present():
    from grocery.tools.hyvee import ensure_logged_in

    # When logged in, the "Log In" control should not be visible.
    page = _FakePage(html="logged in", login_visible=False)
    ensure_logged_in(page, email="x", password="y")

    # Should navigate to home and then return without filling login fields.
    assert ("goto", "https://www.hy-vee.com/aisles-online/") in page.calls
    assert not any(c[0] == "fill" for c in page.calls)


def test_ensure_logged_in_raises_when_missing_creds_and_not_logged_in(monkeypatch):
    from grocery.tools.hyvee import ensure_logged_in

    # Ensure env vars are not present for this test.
    monkeypatch.delenv("HYVEE_EMAIL", raising=False)
    monkeypatch.delenv("HYVEE_PASSWORD", raising=False)

    page = _FakePage(html="not logged in", login_visible=True)
    with pytest.raises(RuntimeError, match="credentials missing"):
        ensure_logged_in(page, email=None, password=None)


def test_ensure_logged_in_attempts_login_flow_with_creds(monkeypatch):
    from grocery.tools.hyvee import ensure_logged_in

    # Use env vars to ensure wiring is correct.
    monkeypatch.setenv("HYVEE_EMAIL", "user@example.com")
    monkeypatch.setenv("HYVEE_PASSWORD", "pw")

    page = _FakePage(html="not logged in", login_visible=True)

    original_click = _FakeLocator.click

    def click_and_flip(self, *args, **kwargs):
        original_click(self, *args, **kwargs)
        # Flip to "logged in" when the submit click occurs.
        if 'button:has-text("Log In"), button:has-text("Log in")' in self._selector:
            page.login_visible = False

    monkeypatch.setattr(_FakeLocator, "click", click_and_flip)

    ensure_logged_in(page, email=None, password=None)

    # Verify expected selector interactions happened.
    assert (
        "wait_for_selector",
        'input[type="email"], input[name="email"], input[name*="email"], input[id*="email"]',
    ) in page.calls
    assert any(c[0] == "fill" and c[2] == "user@example.com" for c in page.calls)
    assert any(c[0] == "fill" and c[2] == "pw" for c in page.calls)


