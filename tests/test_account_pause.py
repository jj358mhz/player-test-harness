"""Pausing an Uplynk account: not synced, checked or signed for, and left out of lists."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import AdminEvent, Channel, UplynkAccount, db


@pytest.fixture
def paused_and_live(make_account, make_channel):
    """A paused account and a live one, with one channel each."""
    paused = make_account(label="paused_acct", workspace_id="owner123", is_paused=True)
    live = make_account(label="live_acct", workspace_id="owner456")
    return (
        make_channel(paused, "chan0001", description="Paused Channel", slicer_id="slicer01"),
        make_channel(live, "chan0002", description="Live Channel", slicer_id="slicer02"),
    )


def test_accounts_are_not_paused_by_default(make_account):
    assert make_account().is_paused is False


def test_pause_and_resume_are_recorded(auth_client, make_account):
    acct = make_account()

    auth_client.post(f"/admin/uplynk-accounts/{acct.id}/pause")
    assert db.session.get(UplynkAccount, acct.id).is_paused is True
    body = auth_client.get("/admin/uplynk-accounts").get_data(as_text=True)
    assert "badge--paused" in body
    assert "Resume this account to sync it" in body

    auth_client.post(f"/admin/uplynk-accounts/{acct.id}/resume")
    db.session.expire_all()
    assert db.session.get(UplynkAccount, acct.id).is_paused is False
    assert "badge--paused" not in auth_client.get("/admin/uplynk-accounts").get_data(as_text=True)

    actions = [e.action for e in db.session.query(AdminEvent).order_by(AdminEvent.id)]
    assert actions[-2:] == ["pause", "resume"]


def test_pausing_keeps_channels_and_pins(auth_client, make_account, make_channel):
    acct = make_account()
    channel = make_channel(acct, is_favorite=True)
    auth_client.post(f"/admin/uplynk-accounts/{acct.id}/pause")
    auth_client.post(f"/admin/uplynk-accounts/{acct.id}/resume")
    db.session.expire_all()
    channel = db.session.get(Channel, channel.id)
    assert channel.is_active and channel.is_favorite


def test_a_paused_account_is_not_synced(app, make_account, monkeypatch):
    from app.uplynk import sync

    monkeypatch.setattr(sync, "build_client", lambda a: pytest.fail("synced a paused account"))
    result = sync.sync_account(make_account(is_paused=True))
    assert "paused" in result.error


def test_sync_all_and_autosync_skip_paused_accounts(app, auth_client, paused_and_live, monkeypatch):
    from app import autosync
    from app.admin import routes

    synced = []
    monkeypatch.setattr(routes, "sync_account", lambda a: synced.append(a.label) or _ok(a))
    auth_client.post("/admin/uplynk-accounts/sync-all")
    assert synced == ["live_acct"]

    due = autosync.due_accounts(timedelta(minutes=5), datetime.now(UTC), {})
    assert [a.label for a in due] == ["live_acct"]


def _ok(account):
    from app.uplynk.sync import SyncResult

    return SyncResult(account_id=account.id, account_label=account.label)


def test_health_check_skips_paused_accounts(app, paused_and_live, monkeypatch):
    from app import autosync
    from app.api import service

    checked = []
    monkeypatch.setattr(service, "check_health", lambda cs: checked.extend(cs) or [])
    app.config["CHANNEL_HEALTH_INTERVAL"] = 5
    autosync.run_health(app, None)
    assert [c.channel_id for c in checked] == ["chan0002"]


@pytest.mark.parametrize("url", ["/", "/player", "/compare", "/api/channels", "/sign"])
def test_lists_leave_out_paused_accounts(auth_client, paused_and_live, url):
    body = auth_client.get(url).get_data(as_text=True)
    assert "Paused Channel" not in body
    assert "paused_acct" not in body
    assert "live_acct" in body


def test_dashboard_says_when_every_account_is_paused(auth_client, make_account):
    make_account(is_paused=True)
    assert "Every Uplynk account is paused" in auth_client.get("/").get_data(as_text=True)


def test_a_paused_channel_is_not_signed(auth_client, paused_and_live, probe_calls):
    paused, _ = paused_and_live
    response = auth_client.post("/api/playback", json={"channel_id": paused.id})
    assert response.status_code == 400
    assert "paused" in response.get_json()["error"]
    response = auth_client.post(
        "/api/playback",
        json={"account_id": paused.uplynk_account_id, "content_id": "chan0001"},
    )
    assert response.status_code == 400
    assert probe_calls == []


def test_slicer_link_skips_paused_channels(auth_client, paused_and_live):
    response = auth_client.get("/channels/by-slicer/slicer01")
    assert "/player" not in response.headers["Location"]


def test_slicer_health_api_leaves_out_paused_channels(client, app, paused_and_live):
    app.config["CSL_API_TOKEN"] = "token"
    items = client.get("/api/health/slicers", headers={"Authorization": "Bearer token"}).get_json()[
        "items"
    ]
    assert [i["slicer_id"] for i in items] == ["slicer02"]
