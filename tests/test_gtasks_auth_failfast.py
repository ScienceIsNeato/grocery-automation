import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def test_build_tasks_service_fails_fast_when_refresh_fails(tmp_path: Path, monkeypatch):
    from grocery.tools import gtasks

    # Create token.json so code takes the "token exists" path.
    (tmp_path / "token.json").write_text(
        json.dumps(
            {
                "token": "t",
                "refresh_token": "rt",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "cid",
                "client_secret": "cs",
                "scopes": gtasks.DEFAULT_SCOPES_READONLY,
            }
        ),
        encoding="utf-8",
    )

    # Fake google modules injected into sys.modules so inner-imports resolve.
    google_oauth2_credentials = ModuleType("google.oauth2.credentials")

    class _FakeCreds:
        valid = False
        expired = True
        refresh_token = "rt"

        def refresh(self, req):
            raise RuntimeError("refresh boom")

        def to_json(self):
            return "{}"

    class _FakeCredentials:
        @staticmethod
        def from_authorized_user_file(path: str, scopes: list[str]):
            return _FakeCreds()

    google_oauth2_credentials.Credentials = _FakeCredentials

    google_auth_oauthlib_flow = ModuleType("google_auth_oauthlib.flow")

    class _FakeFlow:
        @staticmethod
        def from_client_secrets_file(path: str, scopes: list[str]):
            raise AssertionError("Interactive flow should not be invoked when token exists")

    google_auth_oauthlib_flow.InstalledAppFlow = _FakeFlow

    google_auth_transport_requests = ModuleType("google.auth.transport.requests")

    class _Req:
        pass

    google_auth_transport_requests.Request = _Req

    googleapiclient_discovery = ModuleType("googleapiclient.discovery")

    def _build(*args, **kwargs):
        return object()

    googleapiclient_discovery.build = _build

    monkeypatch.setitem(sys.modules, "google.oauth2.credentials", google_oauth2_credentials)
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", google_auth_oauthlib_flow)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", google_auth_transport_requests)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", googleapiclient_discovery)

    with pytest.raises(RuntimeError, match="Token refresh failed"):
        gtasks._build_tasks_service(repo_root=tmp_path, scopes=gtasks.DEFAULT_SCOPES_READONLY)


