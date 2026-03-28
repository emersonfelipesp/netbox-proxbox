from __future__ import annotations

from tests.conftest import ResponseStub, load_plugin_module


def test_get_proxmox_card_merges_cluster_and_version_payloads(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.cards",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )

    def fake_get(url, timeout=None):
        if "/proxmox/version" in url:
            return ResponseStub([{"CLUSTER-A": {"version": "8.3.0", "release": "8.3"}}])
        if "/proxmox/sessions" in url:
            return ResponseStub(
                [
                    {
                        "domain": "10.0.0.30",
                        "http_port": 8006,
                        "user": "root@pam",
                        "name": "CLUSTER-A",
                        "mode": "cluster",
                    }
                ]
            )
        raise AssertionError(url)

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.get_proxmox_card(None, 1)
    cluster_data = response.payload["cluster_data"]
    assert cluster_data["name"] == "CLUSTER-A"
    assert cluster_data["version"] == "8.3.0"
    assert response.payload["object"]["name"] == "pve01"
