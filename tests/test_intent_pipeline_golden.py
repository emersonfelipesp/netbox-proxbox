"""Pin the intent pipeline's output against the pre-cutover golden values.

This is the equivalence evidence the intent-model cutover requires. The values
in `_intent_golden_fixtures` were captured from the custom-field-backed builders
before any of this work started, so they cannot drift with the implementation.
Once the builders read `ProxmoxVMIntent`, an equivalent intent row must produce
exactly the same payloads.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _intent_golden_capture import load_intent_module  # noqa: E402
from _intent_golden_fixtures import (  # noqa: E402
    CASES,
    GOLDEN_INTENT_MODEL_LXC_PAYLOADS,
    GOLDEN_INTENT_MODEL_UPDATE_DELTAS,
    GOLDEN_INTENT_MODEL_VM_PAYLOADS,
    GOLDEN_LXC_PAYLOAD,
    GOLDEN_METADATA_SNAPSHOT,
    GOLDEN_UPDATE_DELTA,
    GOLDEN_VM_PAYLOAD,
    INTENT_MODEL_CASES,
    INTENT_MODEL_PREV_STATES,
    PREV_STATES,
)


@pytest.fixture(scope="module")
def payload():
    return load_intent_module("payload")


@pytest.fixture(scope="module")
def snapshot():
    return load_intent_module("snapshot")


@pytest.mark.parametrize("case", sorted(GOLDEN_VM_PAYLOAD))
def test_vm_payload_matches_golden(payload, case):
    assert payload.build_vm_payload(CASES[case]) == GOLDEN_VM_PAYLOAD[case]


@pytest.mark.parametrize("case", sorted(GOLDEN_LXC_PAYLOAD))
def test_lxc_payload_matches_golden(payload, case):
    assert payload.build_lxc_payload(CASES[case]) == GOLDEN_LXC_PAYLOAD[case]


@pytest.mark.parametrize("case", sorted(GOLDEN_UPDATE_DELTA))
def test_update_delta_matches_golden(payload, case):
    assert (
        payload.build_update_delta(CASES[case], PREV_STATES[case])
        == GOLDEN_UPDATE_DELTA[case]
    )


@pytest.mark.parametrize("case", sorted(GOLDEN_INTENT_MODEL_VM_PAYLOADS))
def test_vm_payload_uses_intent_when_custom_fields_do_not_match(payload, case):
    assert (
        payload.build_vm_payload(INTENT_MODEL_CASES[case])
        == GOLDEN_INTENT_MODEL_VM_PAYLOADS[case]
    )


@pytest.mark.parametrize("case", sorted(GOLDEN_INTENT_MODEL_LXC_PAYLOADS))
def test_lxc_payload_uses_intent_when_custom_fields_do_not_match(payload, case):
    assert (
        payload.build_lxc_payload(INTENT_MODEL_CASES[case])
        == GOLDEN_INTENT_MODEL_LXC_PAYLOADS[case]
    )


@pytest.mark.parametrize("case", sorted(GOLDEN_INTENT_MODEL_UPDATE_DELTAS))
def test_update_delta_uses_intent_when_custom_fields_do_not_match(payload, case):
    assert (
        payload.build_update_delta(
            INTENT_MODEL_CASES[case], INTENT_MODEL_PREV_STATES[case]
        )
        == GOLDEN_INTENT_MODEL_UPDATE_DELTAS[case]
    )


@pytest.mark.parametrize("case", sorted(GOLDEN_METADATA_SNAPSHOT))
def test_metadata_snapshot_matches_golden(snapshot, case):
    actual = snapshot.build_metadata_snapshot(CASES[case])
    intent = actual.pop("intent")
    expected = dict(GOLDEN_METADATA_SNAPSHOT[case])
    expected["node"] = {
        "cf_prefixed": "pve-03",
        "empty_cf": None,
        "full_lxc": "pve-02",
        "full_qemu": "pve-01",
        "network_dict": "pve-05",
        "partial_blank": "pve-04",
    }[case]
    assert actual == expected
    assert intent == EXPECTED_INTENT_SNAPSHOTS[case]


def test_deleted_vm_snapshot_uses_recorded_identity(snapshot):
    row = type(
        "DeletedVMChangeDiff",
        (),
        {
            "object_id": 919,
            "object_repr": "deleted-vm",
            "original": {
                "name": "recorded-name",
                "vcpus": 6,
                "memory": 12288,
                "vmid": "9190",
                "node": "pve-recorded",
            },
            "current": {"name": "current-name"},
        },
    )()

    assert snapshot.build_deleted_metadata_snapshot(row) == {
        "vmid": 9190,
        "node": "pve-recorded",
        "name": "recorded-name",
        "tags": [],
        "cores": 6,
        "memory": 12288,
        "disk_gb": None,
        "interfaces": [],
        "ipv4": None,
        "ipv6": None,
        "custom_field_data": {},
        "intent": {},
        "change_diff": {
            "object_id": 919,
            "object_repr": "deleted-vm",
            "original": {
                "name": "recorded-name",
                "vcpus": 6,
                "memory": 12288,
                "vmid": "9190",
                "node": "pve-recorded",
            },
            "current": {"name": "current-name"},
        },
    }


def test_deleted_vm_snapshot_never_fabricates_vmid_from_object_id(snapshot):
    row = type(
        "DeletedVMChangeDiff",
        (),
        {
            "object_id": 920,
            "object_repr": "identity-missing",
            "original": {"name": "identity-missing", "node": "pve-a"},
            "current": None,
        },
    )()

    with pytest.raises(ValueError, match="Proxmox VMID"):
        snapshot.build_deleted_metadata_snapshot(row)


FULL_INTENT_SNAPSHOT = {
    "target_node": "pve-01",
    "target_storage": "local-lvm",
    "iso": "local:iso/debian-12.iso",
    "template_vmid": 9000,
    "swap": 512,
    "rootfs": "local-lvm:8",
    "ostemplate": "local:vztmpl/debian-12.tar.zst",
    "cloud_init_user": "operator",
    "cloud_init_ssh_keys": "ssh-ed25519 AAAAKEY1 a@b\n\nssh-ed25519 AAAAKEY2 c@d\n",
    "cloud_init_user_data": "#cloud-config\npassword: hunter2\n",
    "cloud_init_network": '{"version": 2, "ethernets": {"eth0": {"dhcp4": true}}}',
    "intent_state": "pending",
    "last_apply_run_id": "11111111-2222-3333-4444-555555555555",
}

EXPECTED_INTENT_SNAPSHOTS = {
    "cf_prefixed": {
        "target_node": "pve-01",
        "target_storage": "local-lvm",
        "iso": "local:iso/debian-12.iso",
        "template_vmid": 9000,
        "swap": 512,
        "rootfs": "local-lvm:8",
        "ostemplate": "local:vztmpl/debian-12.tar.zst",
        "cloud_init_user": "",
        "cloud_init_ssh_keys": "",
        "cloud_init_user_data": "",
        "cloud_init_network": "",
        "intent_state": "",
        "last_apply_run_id": "",
    },
    "empty_cf": {},
    "full_lxc": FULL_INTENT_SNAPSHOT,
    "full_qemu": FULL_INTENT_SNAPSHOT,
    "network_dict": {
        "target_node": "pve-05",
        "target_storage": "",
        "iso": "",
        "template_vmid": None,
        "swap": None,
        "rootfs": "",
        "ostemplate": "",
        "cloud_init_user": "root",
        "cloud_init_ssh_keys": "",
        "cloud_init_user_data": "",
        "cloud_init_network": '{"version": 1, "config": []}',
        "intent_state": "",
        "last_apply_run_id": "",
    },
    "partial_blank": {
        "target_node": "pve-04",
        "target_storage": "",
        "iso": "",
        "template_vmid": None,
        "swap": None,
        "rootfs": "",
        "ostemplate": "",
        "cloud_init_user": "",
        "cloud_init_ssh_keys": "   \n  \n",
        "cloud_init_user_data": "   ",
        "cloud_init_network": "{not json",
        "intent_state": "",
        "last_apply_run_id": "",
    },
}


def test_the_golden_set_covers_the_shapes_that_matter():
    """A shrinking fixture set would quietly weaken this oracle."""
    assert set(CASES) == {
        "full_qemu",
        "full_lxc",
        "empty_cf",
        "cf_prefixed",
        "partial_blank",
        "network_dict",
    }
