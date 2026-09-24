from __future__ import annotations

import json
from pathlib import Path


def test_node_network_responses_use_proxmox_list_envelopes() -> None:
    fixture_path = Path(__file__).parent / "e2e" / "proxmox_openapi_mock_data.json"
    fixture = json.loads(fixture_path.read_text())

    for node in ("pve01", "pve02", "pve03"):
        response = fixture[f"/api2/json/nodes/{node}/network"]

        assert isinstance(response["data"], list)
        assert response["data"][0] == {
            "iface": "eno1",
            "type": "eth",
            "active": 1,
            "autostart": 1,
        }
        assert response["data"][1] == {
            "iface": "vmbr0",
            "type": "bridge",
            "active": 1,
            "autostart": 1,
            "bridge_ports": "eno1",
        }
