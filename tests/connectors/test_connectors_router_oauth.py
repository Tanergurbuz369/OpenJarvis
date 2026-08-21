"""Regression tests for the connectors-router OAuth flow (issue #512).

These tests reproduce the three coupled defects that prevented Google Drive
(and its Google siblings) from ever completing OAuth and appearing in Data
Sources, and assert the fixed behaviour:

(A/B) ``POST /connect`` with a pasted ``client_id:client_secret`` pair must
      persist the client credentials and return an ``oauth_required`` directive
      pointing at ``/oauth/start`` — NOT silently spawn a background browser
      thread and report a perpetual ``pending`` state.
(C-1) ``GET /oauth/start`` must return a redirect to the provider's consent
      page (regression: HTTP 422 because ``request: Request`` was mis-bound as
      a query param under ``from __future__ import annotations`` + a local
      ``Request`` import).
(C-2) ``GET /oauth/callback`` must read ``request.base_url`` and exchange the
      code for tokens without crashing (regression: ``request`` defaulted to
      ``None`` → ``AttributeError``), persisting the access token to every
      Google credential file and flipping ``is_connected()`` to True.

All tests are hermetic: the connectors directory, the shared Google
credentials path, and every Google connector's default credentials path are
redirected to ``tmp_path`` so the suite neither depends on nor pollutes
``~/.openjarvis/connectors`` (a real source of spurious failures — see the
verifier note on ``resolve_google_credentials`` silently substituting the
shared file when the caller-supplied path does not yet exist on disk).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

fastapi = pytest.importorskip("fastapi", reason="requires the 'server' extra")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_CLIENT_PAIR = "myid-123.apps.googleusercontent.com:GOCSPX-secret"
_CLIENT_ID = "myid-123.apps.googleusercontent.com"

_ALL_GOOGLE_FILES = (
    "google.json",
    "gdrive.json",
    "gcalendar.json",
    "gcontacts.json",
    "gmail.json",
    "google_tasks.json",
)


@pytest.fixture()
def hermetic_connectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all Google credential paths into *tmp_path*.

    Ensures connector instances created by the router's ``_get_or_create``
    resolve to the same directory the OAuth callback writes to, and that the
    test leaves ``~/.openjarvis`` untouched.

    Why this is more than a one-line monkeypatch: the autouse registry-clear
    fixture causes ``_ensure_connectors_registered()`` to ``importlib.reload``
    each connector module on the first router call, which re-executes the
    module body. To survive that reload we patch ``DEFAULT_CONFIG_DIR`` at its
    *source* (``openjarvis.core.config``) — every connector re-derives
    ``_DEFAULT_CREDENTIALS_PATH`` from it on reload, so the tmp dir sticks.
    We also pre-register + pre-reload the connectors inside the fixture so the
    reload happens while the patch is live, then reset module state on
    teardown so a later test that imports these modules fresh is unaffected.
    """
    import importlib
    import sys

    import openjarvis.connectors.oauth as oauth_mod
    import openjarvis.core.config as config_mod
    import openjarvis.server.connectors_router as router_mod
    from openjarvis.core.registry import ConnectorRegistry

    conn_dir = tmp_path / "connectors"
    conn_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config_mod, "DEFAULT_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(oauth_mod, "_CONNECTORS_DIR", conn_dir)
    monkeypatch.setattr(
        oauth_mod,
        "_GOOGLE_ACCOUNTS_DIR",
        conn_dir / "google" / "accounts",
    )
    monkeypatch.setattr(
        oauth_mod, "_SHARED_GOOGLE_CREDENTIALS_PATH", str(conn_dir / "google.json")
    )

    # Force the connector modules to re-derive their default paths from the
    # patched DEFAULT_CONFIG_DIR now, before any request, and register them so
    # the router's lazy reload-on-empty-registry path is a no-op.
    google_mods = [
        "openjarvis.connectors.gdrive",
        "openjarvis.connectors.gcalendar",
        "openjarvis.connectors.gcontacts",
        "openjarvis.connectors.gmail",
        "openjarvis.connectors.google_tasks",
        # Non-Google OAuth providers (Spotify, Strava) derive their default
        # credentials path from DEFAULT_CONFIG_DIR the same way -- reload
        # them too so the client-pair-detection tests below are hermetic.
        "openjarvis.connectors.spotify",
        "openjarvis.connectors.strava",
    ]
    ConnectorRegistry.clear()
    for name in google_mods:
        module = importlib.import_module(name)
        # Always execute each decorator under the patched config root. Merely
        # reloading modules that happen to be cached made this fixture depend
        # on collection order and could leave the registry empty.
        importlib.reload(module)

    router_mod._instances.clear()
    yield conn_dir
    router_mod._instances.clear()
    ConnectorRegistry.clear()
    # Restore the config root before reloading. Fixture finalizers otherwise
    # run in dependency order (this teardown before monkeypatch's), which used
    # to bake the temporary directory back into module-level defaults.
    monkeypatch.undo()
    for name in google_mods:
        module = sys.modules.get(name)
        if module is not None:
            importlib.reload(module)


@pytest.fixture()
def client(hermetic_connectors: Path) -> Iterator[TestClient]:
    from openjarvis.server.connectors_router import create_connectors_router

    app = FastAPI()
    app.include_router(create_connectors_router())
    with TestClient(app) as c:
        yield c


def _start_state(
    client: TestClient,
    connector_id: str,
    *,
    account: str = "",
) -> str:
    """Start OAuth and return the one-time state from its provider URL."""
    suffix = f"?account={account}" if account else ""
    response = client.get(
        f"/v1/connectors/{connector_id}/oauth/start{suffix}",
        follow_redirects=False,
    )
    assert response.status_code in (302, 307), response.text
    state = parse_qs(urlparse(response.headers["location"]).query).get("state")
    assert state and len(state) == 1
    return state[0]


# ---------------------------------------------------------------------------
# Defect A/B — POST /connect must not silently spawn a background OAuth thread
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "connector_id", ["gdrive", "gcalendar", "gcontacts", "gmail", "google_tasks"]
)
def test_connect_client_pair_returns_oauth_required_no_browser(
    client: TestClient, hermetic_connectors: Path, connector_id: str
) -> None:
    """Pasting client_id:secret persists creds + asks the UI to run the flow.

    Covers every Google connector that shares the OAuth provider, proving the
    sibling connectors are fixed too (not just gdrive).
    """
    with patch("openjarvis.core.open_browser") as mock_browser:
        resp = client.post(
            f"/v1/connectors/{connector_id}/connect", json={"code": _CLIENT_PAIR}
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "oauth_required"
    assert body["oauth_start"] == f"/v1/connectors/{connector_id}/oauth/start"
    assert body["connected"] is False
    # No fire-and-forget browser thread (the root cause of "nothing happens").
    mock_browser.assert_not_called()

    # Client credentials persisted to EVERY Google credential file so a single
    # consent covers all Google connectors.
    for filename in _ALL_GOOGLE_FILES:
        path = hermetic_connectors / filename
        assert path.exists(), f"{filename} not written"
        assert json.loads(path.read_text())["client_id"] == _CLIENT_ID


def test_connect_malformed_client_pair_raises_400(
    client: TestClient,
) -> None:
    """A blank secret surfaces an actionable 400 — not a silent pending state."""
    resp = client.post(
        "/v1/connectors/gdrive/connect",
        json={"code": "myid-123.apps.googleusercontent.com:"},
    )
    assert resp.status_code == 400
    assert "CLIENT_ID:CLIENT_SECRET" in resp.json()["detail"]


def test_connect_raw_token_still_handled(
    client: TestClient, hermetic_connectors: Path
) -> None:
    """A raw token (not a client pair) still flows through handle_callback."""
    resp = client.post(
        "/v1/connectors/gdrive/connect", json={"token": "ya29.raw-access-token"}
    )
    assert resp.status_code == 200, resp.text
    saved = json.loads((hermetic_connectors / "gdrive.json").read_text())
    assert saved.get("token") == "ya29.raw-access-token"


# ---------------------------------------------------------------------------
# Non-Google OAuth providers (Spotify, Strava) — the client-pair detection
# only recognized Google's client ID format (`.apps.googleusercontent.com`),
# so pasting a Spotify or Strava client_id:client_secret pair silently fell
# through to the raw-token path instead of registering credentials and
# returning oauth_required. The UI's "connect this account" flow for any
# non-Google OAuth connector was unreachable as a result.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "connector_id,credentials_file",
    [("spotify", "spotify.json"), ("strava", "strava.json")],
)
def test_connect_client_pair_returns_oauth_required_for_non_google_providers(
    client: TestClient,
    hermetic_connectors: Path,
    connector_id: str,
    credentials_file: str,
) -> None:
    pair = f"{connector_id}-client-id:{connector_id}-client-secret"

    with patch("openjarvis.core.open_browser") as mock_browser:
        resp = client.post(
            f"/v1/connectors/{connector_id}/connect", json={"code": pair}
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "oauth_required"
    assert body["oauth_start"] == f"/v1/connectors/{connector_id}/oauth/start"
    assert body["connected"] is False
    mock_browser.assert_not_called()

    saved = json.loads((hermetic_connectors / credentials_file).read_text())
    assert saved["client_id"] == f"{connector_id}-client-id"
    assert saved["client_secret"] == f"{connector_id}-client-secret"


def test_connect_malformed_client_pair_raises_400_for_spotify(
    client: TestClient,
) -> None:
    """A blank secret surfaces an actionable 400 for non-Google providers too."""
    resp = client.post(
        "/v1/connectors/spotify/connect", json={"code": "some-client-id:"}
    )
    assert resp.status_code == 400
    assert "CLIENT_ID:CLIENT_SECRET" in resp.json()["detail"]


def test_google_client_pair_detection_unaffected_by_generalization(
    client: TestClient, hermetic_connectors: Path
) -> None:
    """Guard against regressing defect A/B: Google's pair must still only be
    recognized via its distinctive client ID suffix, not just any colon."""
    resp = client.post("/v1/connectors/gdrive/connect", json={"code": _CLIENT_PAIR})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "oauth_required"
    saved = json.loads((hermetic_connectors / "gdrive.json").read_text())
    assert saved["client_id"] == _CLIENT_ID


# ---------------------------------------------------------------------------
# Defect C-1 — GET /oauth/start must redirect (was HTTP 422)
# ---------------------------------------------------------------------------


def test_oauth_start_redirects_to_consent(
    client: TestClient,
) -> None:
    # First save client creds via the connect call.
    client.post("/v1/connectors/gdrive/connect", json={"code": _CLIENT_PAIR})

    resp = client.get("/v1/connectors/gdrive/oauth/start", follow_redirects=False)
    # FastAPI's RedirectResponse defaults to 307; any 3xx is a pass (was 422).
    assert resp.status_code in (302, 307), resp.text
    location = resp.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert _CLIENT_ID in location
    # redirect_uri must point back at OUR in-process callback.
    assert "oauth%2Fcallback" in location or "oauth/callback" in location


def test_oauth_start_can_return_provider_url_for_authenticated_frontend(
    client: TestClient,
) -> None:
    client.post("/v1/connectors/gdrive/connect", json={"code": _CLIENT_PAIR})

    response = client.get(
        "/v1/connectors/gdrive/oauth/start",
        params={"response_mode": "json"},
    )

    assert response.status_code == 200
    authorization_url = response.json()["authorization_url"]
    assert authorization_url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert parse_qs(urlparse(authorization_url).query)["state"][0]


def test_oauth_start_without_creds_returns_400(client: TestClient) -> None:
    resp = client.get("/v1/connectors/gdrive/oauth/start", follow_redirects=False)
    assert resp.status_code == 400
    assert "client credentials" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Defect C-2 — GET /oauth/callback must exchange + persist (was 500 on None)
# ---------------------------------------------------------------------------


def test_oauth_callback_exchanges_and_connects(
    client: TestClient, hermetic_connectors: Path
) -> None:
    import openjarvis.connectors.oauth as oauth_mod

    client.post("/v1/connectors/gdrive/connect", json={"code": _CLIENT_PAIR})
    state = _start_state(client, "gdrive")

    fake_tokens = {
        "access_token": "ya29.REAL",
        "refresh_token": "1//REAL",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    with patch.object(oauth_mod, "_exchange_token", return_value=fake_tokens) as ex:
        resp = client.get(
            "/v1/connectors/gdrive/oauth/callback",
            params={"code": "authcode123", "state": state},
        )

    assert resp.status_code == 200, resp.text
    assert "Connected!" in resp.text
    ex.assert_called_once()

    # Access token written to ALL Google credential files.
    for filename in _ALL_GOOGLE_FILES:
        saved = json.loads((hermetic_connectors / filename).read_text())
        assert saved["access_token"] == "ya29.REAL"
        assert saved["refresh_token"] == "1//REAL"

    # The connector now reports connected, and GET /connectors agrees.
    from openjarvis.connectors.gdrive import GDriveConnector

    assert GDriveConnector().is_connected() is True

    listing = client.get("/v1/connectors").json()["connectors"]
    gdrive = next(c for c in listing if c["connector_id"] == "gdrive")
    assert gdrive["connected"] is True


def test_oauth_callback_error_param_renders_failure(client: TestClient) -> None:
    client.post("/v1/connectors/gdrive/connect", json={"code": _CLIENT_PAIR})
    state = _start_state(client, "gdrive")
    resp = client.get(
        "/v1/connectors/gdrive/oauth/callback",
        params={"error": "access_denied", "state": state},
    )
    assert resp.status_code == 400
    assert "access_denied" in resp.text


def test_oauth_callback_exchange_failure_renders_error(
    client: TestClient,
) -> None:
    import openjarvis.connectors.oauth as oauth_mod

    client.post("/v1/connectors/gdrive/connect", json={"code": _CLIENT_PAIR})
    state = _start_state(client, "gdrive")

    def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise RuntimeError("token endpoint 400")

    with patch.object(oauth_mod, "_exchange_token", side_effect=_boom):
        resp = client.get(
            "/v1/connectors/gdrive/oauth/callback",
            params={"code": "bad", "state": state},
        )

    assert resp.status_code == 500
    assert "Token Exchange Failed" in resp.text


def test_oauth_callback_rejects_missing_access_token_without_false_success(
    client: TestClient,
    hermetic_connectors: Path,
) -> None:
    """Client credentials alone must not complete the consent flow."""
    import openjarvis.connectors.oauth as oauth_mod

    client.post("/v1/connectors/spotify/connect", json={"code": "id:secret"})
    state = _start_state(client, "spotify")
    with patch.object(
        oauth_mod,
        "_exchange_token",
        return_value={"refresh_token": "refresh-only"},
    ):
        resp = client.get(
            "/v1/connectors/spotify/oauth/callback",
            params={"code": "bad-payload", "state": state},
        )

    assert resp.status_code == 500
    assert "Token Exchange Failed" in resp.text
    assert "Connected!" not in resp.text
    saved = json.loads((hermetic_connectors / "spotify.json").read_text())
    assert "access_token" not in saved

    from openjarvis.connectors.spotify import SpotifyConnector

    assert SpotifyConnector().is_connected() is False


def test_named_account_oauth_state_binds_segmented_token(
    client: TestClient,
    hermetic_connectors: Path,
) -> None:
    """The callback account comes from one-time state, not caller input."""
    import openjarvis.connectors.oauth as oauth_mod

    response = client.post(
        "/v1/connectors/gdrive/connect",
        json={"code": _CLIENT_PAIR, "account": "work"},
    )
    assert response.status_code == 200
    assert response.json()["oauth_start"].endswith("?account=work")
    # Cache a sibling before tokens exist. The callback must invalidate every
    # Google primitive that shares this named grant, not only gdrive.
    assert (
        client.get("/v1/connectors/gmail", params={"account": "work"}).json()[
            "connected"
        ]
        is False
    )
    state = _start_state(client, "gdrive", account="work")

    with patch.object(
        oauth_mod,
        "_exchange_token",
        return_value={"access_token": "ya29.WORK", "refresh_token": "refresh"},
    ):
        callback = client.get(
            "/v1/connectors/gdrive/oauth/callback",
            params={"code": "work-code", "state": state, "account": "personal"},
        )

    assert callback.status_code == 200
    account_file = hermetic_connectors / "google" / "accounts" / "work.json"
    assert json.loads(account_file.read_text(encoding="utf-8"))["access_token"] == (
        "ya29.WORK"
    )
    assert not (hermetic_connectors / "google" / "accounts" / "personal.json").exists()

    detail = client.get("/v1/connectors/gdrive", params={"account": "work"})
    assert detail.status_code == 200
    assert detail.json()["account"] == "work"
    assert detail.json()["connected"] is True
    assert (
        client.get("/v1/connectors/gmail", params={"account": "work"}).json()[
            "connected"
        ]
        is True
    )

    listing = client.get("/v1/connectors").json()["connectors"]
    gdrive = next(item for item in listing if item["connector_id"] == "gdrive")
    assert gdrive["accounts"] == [
        {"account": "work", "connected": True, "source_email": ""}
    ]

    disconnected = client.post(
        "/v1/connectors/gdrive/disconnect",
        params={"account": "work"},
    )
    assert disconnected.status_code == 200, disconnected.text
    assert set(disconnected.json()["disconnected_connectors"]) == {
        "gcalendar",
        "gcontacts",
        "gdrive",
        "gmail",
        "google_tasks",
    }
    assert not account_file.exists()
    for connector_id in ("gdrive", "gmail", "gcalendar"):
        response = client.get(
            f"/v1/connectors/{connector_id}",
            params={"account": "work"},
        )
        assert response.status_code == 200
        assert response.json()["connected"] is False


def test_named_account_rejected_for_non_google_connector(client: TestClient) -> None:
    response = client.get("/v1/connectors/spotify", params={"account": "work"})

    assert response.status_code == 400
    assert "supported only for Google connectors" in response.json()["detail"]


def test_connect_rejects_conflicting_account_and_profile(client: TestClient) -> None:
    response = client.post(
        "/v1/connectors/gdrive/connect",
        json={"code": _CLIENT_PAIR, "account": "work", "profile": "personal"},
    )

    assert response.status_code == 400
    assert "must name the same alias" in response.json()["detail"]


def test_reauth_rejected_while_sibling_account_sync_is_active(
    client: TestClient,
) -> None:
    import openjarvis.connectors.oauth as oauth_mod
    import openjarvis.server.connectors_router as router_mod

    client.post(
        "/v1/connectors/gdrive/connect",
        json={"code": _CLIENT_PAIR, "account": "work"},
    )
    state = _start_state(client, "gdrive", account="work")
    started = threading.Event()
    release = threading.Event()

    class _BlockingGmail:
        connector_id = "gmail"
        _account = "work"

        @staticmethod
        def is_connected() -> bool:
            return True

        @staticmethod
        def sync(*, since=None, cursor=None):
            del since, cursor
            started.set()
            release.wait(timeout=5)
            if False:
                yield None

    router_mod._instances["gmail:work"] = _BlockingGmail()
    try:
        sync_response = client.post(
            "/v1/connectors/gmail/sync", params={"account": "work"}
        )
        assert sync_response.status_code == 200
        assert started.wait(timeout=2)

        with patch.object(oauth_mod, "_exchange_token") as exchange:
            callback = client.get(
                "/v1/connectors/gdrive/oauth/callback",
                params={"code": "new-identity", "state": state},
            )

        assert callback.status_code == 409
        assert "sync is active" in callback.json()["detail"]
        exchange.assert_not_called()
    finally:
        release.set()


def test_oauth_state_is_required_and_single_use(
    client: TestClient,
) -> None:
    """Missing, forged, or replayed state never reaches token exchange."""
    import openjarvis.connectors.oauth as oauth_mod

    client.post("/v1/connectors/gdrive/connect", json={"code": _CLIENT_PAIR})
    state = _start_state(client, "gdrive")

    with patch.object(
        oauth_mod,
        "_exchange_token",
        return_value={"access_token": "ya29.ONCE"},
    ) as exchange:
        missing = client.get(
            "/v1/connectors/gdrive/oauth/callback",
            params={"code": "missing"},
        )
        forged = client.get(
            "/v1/connectors/gdrive/oauth/callback",
            params={"code": "forged", "state": "not-issued"},
        )
        first = client.get(
            "/v1/connectors/gdrive/oauth/callback",
            params={"code": "valid", "state": state},
        )
        replay = client.get(
            "/v1/connectors/gdrive/oauth/callback",
            params={"code": "again", "state": state},
        )

    assert missing.status_code == 400
    assert forged.status_code == 400
    assert first.status_code == 200
    assert replay.status_code == 400
    exchange.assert_called_once()


def test_oauth_error_is_html_escaped(client: TestClient) -> None:
    """Provider error text cannot inject markup into the callback page."""
    client.post("/v1/connectors/gdrive/connect", json={"code": _CLIENT_PAIR})
    state = _start_state(client, "gdrive")

    response = client.get(
        "/v1/connectors/gdrive/oauth/callback",
        params={"error": "<script>alert(1)</script>", "state": state},
    )

    assert response.status_code == 400
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
