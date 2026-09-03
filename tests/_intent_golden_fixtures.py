"""Golden intent-pipeline outputs, captured before the intent model existed.

These constants were produced by running the custom-field-backed builders on
`develop` and recording what they returned. They are the oracle for the
`ProxmoxVMIntent` cutover: the model-backed builders must reproduce them byte
for byte from equivalent intent rows.

They are transcribed values, never derived from the code under test. A test
whose expectation is computed by the implementation it checks proves nothing --
see the repository review notes on guards built from the thing they guard. Do
not regenerate this file from the current implementation; if a value here has
to change, that is a behaviour change and needs saying out loud in the commit
that changes it.
"""

from __future__ import annotations

from _intent_golden_capture import (  # noqa: F401
    FakeDisk,
    FakeInterface,
    FakeIntent,
    FakeSyncState,
    FakeTag,
    FakeVM,
)

FULL_CF = {
    "proxmox_node": "pve-01",
    "proxmox_storage": "local-lvm",
    "proxmox_iso": "local:iso/debian-12.iso",
    "proxmox_template_vmid": "9000",
    "cloud_init_user": "operator",
    "cloud_init_ssh_keys": "ssh-ed25519 AAAAKEY1 a@b\n\nssh-ed25519 AAAAKEY2 c@d\n",
    "cloud_init_user_data": "#cloud-config\npassword: hunter2\n",
    "cloud_init_network": '{"version": 2, "ethernets": {"eth0": {"dhcp4": true}}}',
    "proxbox_intent_state": "pending",
    "proxbox_last_apply_run_id": "11111111-2222-3333-4444-555555555555",
    "proxmox_swap": "512",
    "proxmox_rootfs": "local-lvm:8",
    "proxmox_ostemplate": "local:vztmpl/debian-12.tar.zst",
}

FULL_INTENT = FakeIntent(
    target_node="pve-01",
    target_storage="local-lvm",
    iso="local:iso/debian-12.iso",
    template_vmid=9000,
    swap=512,
    rootfs="local-lvm:8",
    ostemplate="local:vztmpl/debian-12.tar.zst",
    cloud_init_user="operator",
    cloud_init_ssh_keys="ssh-ed25519 AAAAKEY1 a@b\n\nssh-ed25519 AAAAKEY2 c@d\n",
    cloud_init_user_data="#cloud-config\npassword: hunter2\n",
    cloud_init_network='{"version": 2, "ethernets": {"eth0": {"dhcp4": true}}}',
    intent_state="pending",
    last_apply_run_id="11111111-2222-3333-4444-555555555555",
)

CF_PREFIXED_INTENT = FakeIntent(
    target_node="pve-01",
    target_storage="local-lvm",
    iso="local:iso/debian-12.iso",
    template_vmid=9000,
    swap=512,
    rootfs="local-lvm:8",
    ostemplate="local:vztmpl/debian-12.tar.zst",
)

CASES = {}

CASES["full_qemu"] = FakeVM(
    pk=101,
    name="vm-full",
    vmid=110,
    vcpus=4,
    memory=8192,
    description="a full qemu intent",
    custom_field_data=FULL_CF,
    intent=FULL_INTENT,
    disks=[FakeDisk(20), FakeDisk(30)],
    tags=[FakeTag("prod"), FakeTag("proxbox")],
    interfaces=[FakeInterface("net0", "aa:bb:cc:dd:ee:01", True, 1500, "primary")],
    sync_state=FakeSyncState(vm_id=110, vm_type="qemu", node_name="pve-01"),
)

CASES["full_lxc"] = FakeVM(
    pk=102,
    name="ct-full",
    vmid=210,
    vcpus=2,
    memory=2048,
    description="a full lxc intent",
    custom_field_data=FULL_CF,
    intent=FULL_INTENT,
    disks=[FakeDisk(8)],
    tags=[FakeTag("lxc")],
    sync_state=FakeSyncState(vm_id=210, vm_type="lxc", node_name="pve-02"),
)

CASES["empty_cf"] = FakeVM(
    pk=103,
    name="vm-bare",
    vmid=None,
    vcpus=None,
    memory=None,
    custom_field_data={},
    sync_state=FakeSyncState(vm_id=None, vm_type=None, node_name=None),
)

CASES["cf_prefixed"] = FakeVM(
    pk=104,
    name="vm-legacy",
    vcpus=1,
    memory=512,
    custom_field_data={f"cf_{k}": v for k, v in FULL_CF.items()},
    intent=CF_PREFIXED_INTENT,
    sync_state=FakeSyncState(vm_id=310, vm_type="qemu", node_name="pve-03"),
)

CASES["partial_blank"] = FakeVM(
    pk=105,
    name="vm-partial",
    vcpus=2,
    memory=1024,
    custom_field_data={
        "proxmox_node": "pve-04",
        "proxmox_storage": "",
        "proxmox_iso": None,
        "proxmox_template_vmid": "not-a-number",
        "cloud_init_user": "",
        "cloud_init_ssh_keys": "   \n  \n",
        "cloud_init_user_data": "   ",
        "cloud_init_network": "{not json",
    },
    intent=FakeIntent(
        target_node="pve-04",
        target_storage="",
        iso="",
        template_vmid=None,
        cloud_init_user="",
        cloud_init_ssh_keys="   \n  \n",
        cloud_init_user_data="   ",
        cloud_init_network="{not json",
    ),
    sync_state=FakeSyncState(vm_id=410, vm_type="qemu", node_name="pve-04"),
)

CASES["network_dict"] = FakeVM(
    pk=106,
    name="vm-netdict",
    vcpus=8,
    memory=16384,
    custom_field_data={
        "proxmox_node": "pve-05",
        "cloud_init_network": {"version": 1, "config": []},
        "cloud_init_user": "root",
    },
    intent=FakeIntent(
        target_node="pve-05",
        cloud_init_network='{"version": 1, "config": []}',
        cloud_init_user="root",
    ),
    disks=[FakeDisk("40")],
    interfaces=[FakeInterface("net0"), FakeInterface("net1", "aa:bb:cc:dd:ee:02")],
    sync_state=FakeSyncState(vm_id=510, vm_type="qemu", node_name="pve-05"),
)

PREV_STATES = {
    "full_qemu": {
        "kind": "qemu",
        "name": "vm-full",
        "cores": 2,
        "memory": 8192,
        "disk_gb": 50,
        "storage": "local-lvm",
        "iso": "local:iso/debian-12.iso",
        "template_vmid": 9000,
        "tags": ["prod", "proxbox"],
        "description": "a full qemu intent",
        "cloud_init": {"user": "operator"},
    },
    "full_lxc": {"kind": "lxc", "name": "ct-full", "cores": 2, "memory": 2048},
    "empty_cf": {"kind": "qemu", "name": "vm-bare"},
}

GOLDEN_VM_PAYLOAD = {
    "cf_prefixed": {
        "cores": 1,
        "description": None,
        "disk_gb": None,
        "iso": "local:iso/debian-12.iso",
        "memory": 512,
        "name": "vm-legacy",
        "node": "pve-01",
        "storage": "local-lvm",
        "tags": [],
        "template_vmid": 9000,
        "vmid": 310,
    },
    "empty_cf": {
        "cores": None,
        "description": None,
        "disk_gb": None,
        "iso": None,
        "memory": None,
        "name": "vm-bare",
        "node": None,
        "storage": None,
        "tags": [],
        "template_vmid": None,
        "vmid": None,
    },
    "full_lxc": {
        "cloud_init": {
            "network": {"ethernets": {"eth0": {"dhcp4": True}}, "version": 2},
            "ssh_keys": ["ssh-ed25519 AAAAKEY1 a@b", "ssh-ed25519 AAAAKEY2 c@d"],
            "user": "operator",
            "user_data": "#cloud-config\npassword: hunter2\n",
        },
        "cores": 2,
        "description": "a full lxc intent",
        "disk_gb": 8,
        "iso": "local:iso/debian-12.iso",
        "memory": 2048,
        "name": "ct-full",
        "node": "pve-01",
        "storage": "local-lvm",
        "tags": ["lxc"],
        "template_vmid": 9000,
        "vmid": 210,
    },
    "full_qemu": {
        "cloud_init": {
            "network": {"ethernets": {"eth0": {"dhcp4": True}}, "version": 2},
            "ssh_keys": ["ssh-ed25519 AAAAKEY1 a@b", "ssh-ed25519 AAAAKEY2 c@d"],
            "user": "operator",
            "user_data": "#cloud-config\npassword: hunter2\n",
        },
        "cores": 4,
        "description": "a full qemu intent",
        "disk_gb": 50,
        "iso": "local:iso/debian-12.iso",
        "memory": 8192,
        "name": "vm-full",
        "node": "pve-01",
        "storage": "local-lvm",
        "tags": ["prod", "proxbox"],
        "template_vmid": 9000,
        "vmid": 110,
    },
    "network_dict": {
        "cloud_init": {"network": {"config": [], "version": 1}, "user": "root"},
        "cores": 8,
        "description": None,
        "disk_gb": 40,
        "iso": None,
        "memory": 16384,
        "name": "vm-netdict",
        "node": "pve-05",
        "storage": None,
        "tags": [],
        "template_vmid": None,
        "vmid": 510,
    },
    "partial_blank": {
        "cores": 2,
        "description": None,
        "disk_gb": None,
        "iso": None,
        "memory": 1024,
        "name": "vm-partial",
        "node": "pve-04",
        "storage": None,
        "tags": [],
        "template_vmid": None,
        "vmid": 410,
    },
}

GOLDEN_LXC_PAYLOAD = {
    "cf_prefixed": {
        "cores": 1,
        "description": None,
        "memory": 512,
        "name": "vm-legacy",
        "node": "pve-01",
        "ostemplate": "local:vztmpl/debian-12.tar.zst",
        "rootfs": "local-lvm:8",
        "storage": "local-lvm",
        "swap": 512,
        "tags": [],
        "vmid": 310,
    },
    "empty_cf": {
        "cores": None,
        "description": None,
        "memory": None,
        "name": "vm-bare",
        "node": None,
        "ostemplate": None,
        "rootfs": None,
        "storage": None,
        "swap": None,
        "tags": [],
        "vmid": None,
    },
    "full_lxc": {
        "cloud_init": {
            "network": {"ethernets": {"eth0": {"dhcp4": True}}, "version": 2},
            "ssh_keys": ["ssh-ed25519 AAAAKEY1 a@b", "ssh-ed25519 AAAAKEY2 c@d"],
            "user": "operator",
            "user_data": "#cloud-config\npassword: hunter2\n",
        },
        "cores": 2,
        "description": "a full lxc intent",
        "memory": 2048,
        "name": "ct-full",
        "node": "pve-01",
        "ostemplate": "local:vztmpl/debian-12.tar.zst",
        "rootfs": "local-lvm:8",
        "storage": "local-lvm",
        "swap": 512,
        "tags": ["lxc"],
        "vmid": 210,
    },
    "full_qemu": {
        "cloud_init": {
            "network": {"ethernets": {"eth0": {"dhcp4": True}}, "version": 2},
            "ssh_keys": ["ssh-ed25519 AAAAKEY1 a@b", "ssh-ed25519 AAAAKEY2 c@d"],
            "user": "operator",
            "user_data": "#cloud-config\npassword: hunter2\n",
        },
        "cores": 4,
        "description": "a full qemu intent",
        "memory": 8192,
        "name": "vm-full",
        "node": "pve-01",
        "ostemplate": "local:vztmpl/debian-12.tar.zst",
        "rootfs": "local-lvm:8",
        "storage": "local-lvm",
        "swap": 512,
        "tags": ["prod", "proxbox"],
        "vmid": 110,
    },
    "network_dict": {
        "cloud_init": {"network": {"config": [], "version": 1}, "user": "root"},
        "cores": 8,
        "description": None,
        "memory": 16384,
        "name": "vm-netdict",
        "node": "pve-05",
        "ostemplate": None,
        "rootfs": None,
        "storage": None,
        "swap": None,
        "tags": [],
        "vmid": 510,
    },
    "partial_blank": {
        "cores": 2,
        "description": None,
        "memory": 1024,
        "name": "vm-partial",
        "node": "pve-04",
        "ostemplate": None,
        "rootfs": None,
        "storage": None,
        "swap": None,
        "tags": [],
        "vmid": 410,
    },
}

GOLDEN_UPDATE_DELTA = {
    "empty_cf": {"node": None, "tags": [], "vmid": None},
    "full_lxc": {
        "cloud_init": {
            "network": {"ethernets": {"eth0": {"dhcp4": True}}, "version": 2},
            "ssh_keys": ["ssh-ed25519 AAAAKEY1 a@b", "ssh-ed25519 AAAAKEY2 c@d"],
            "user": "operator",
            "user_data": "#cloud-config\npassword: hunter2\n",
        },
        "description": "a full lxc intent",
        "node": "pve-01",
        "ostemplate": "local:vztmpl/debian-12.tar.zst",
        "rootfs": "local-lvm:8",
        "storage": "local-lvm",
        "swap": 512,
        "tags": ["lxc"],
        "vmid": 210,
    },
    "full_qemu": {
        "cloud_init": {
            "network": {"ethernets": {"eth0": {"dhcp4": True}}, "version": 2},
            "ssh_keys": ["ssh-ed25519 AAAAKEY1 a@b", "ssh-ed25519 AAAAKEY2 c@d"],
            "user": "operator",
            "user_data": "#cloud-config\npassword: hunter2\n",
        },
        "cores": 4,
        "node": "pve-01",
        "vmid": 110,
    },
}

GOLDEN_METADATA_SNAPSHOT = {
    "cf_prefixed": {
        "cores": 1,
        "custom_field_data": {
            "cf_cloud_init_network": '{"version": 2, '
            '"ethernets": {"eth0": '
            '{"dhcp4": true}}}',
            "cf_cloud_init_ssh_keys": "ssh-ed25519 AAAAKEY1 "
            "a@b\n"
            "\n"
            "ssh-ed25519 AAAAKEY2 "
            "c@d\n",
            "cf_cloud_init_user": "operator",
            "cf_cloud_init_user_data": "#cloud-config\npassword: hunter2\n",
            "cf_proxbox_intent_state": "pending",
            "cf_proxbox_last_apply_run_id": "11111111-2222-3333-4444-555555555555",
            "cf_proxmox_iso": "local:iso/debian-12.iso",
            "cf_proxmox_node": "pve-01",
            "cf_proxmox_ostemplate": "local:vztmpl/debian-12.tar.zst",
            "cf_proxmox_rootfs": "local-lvm:8",
            "cf_proxmox_storage": "local-lvm",
            "cf_proxmox_swap": "512",
            "cf_proxmox_template_vmid": "9000",
        },
        "disk_gb": None,
        "interfaces": [],
        "ipv4": None,
        "ipv6": None,
        "memory": 512,
        "name": "vm-legacy",
        "node": "pve-01",
        "tags": [],
        "vmid": 310,
    },
    "empty_cf": {
        "cores": None,
        "custom_field_data": {},
        "disk_gb": None,
        "interfaces": [],
        "ipv4": None,
        "ipv6": None,
        "memory": None,
        "name": "vm-bare",
        "node": None,
        "tags": [],
        "vmid": None,
    },
    "full_lxc": {
        "cores": 2,
        "custom_field_data": {
            "cloud_init_network": '{"version": 2, "ethernets": '
            '{"eth0": {"dhcp4": true}}}',
            "cloud_init_ssh_keys": "ssh-ed25519 AAAAKEY1 a@b\n"
            "\n"
            "ssh-ed25519 AAAAKEY2 c@d\n",
            "cloud_init_user": "operator",
            "cloud_init_user_data": "#cloud-config\npassword: hunter2\n",
            "proxbox_intent_state": "pending",
            "proxbox_last_apply_run_id": "11111111-2222-3333-4444-555555555555",
            "proxmox_iso": "local:iso/debian-12.iso",
            "proxmox_node": "pve-01",
            "proxmox_ostemplate": "local:vztmpl/debian-12.tar.zst",
            "proxmox_rootfs": "local-lvm:8",
            "proxmox_storage": "local-lvm",
            "proxmox_swap": "512",
            "proxmox_template_vmid": "9000",
        },
        "disk_gb": 8,
        "interfaces": [],
        "ipv4": None,
        "ipv6": None,
        "memory": 2048,
        "name": "ct-full",
        "node": "pve-01",
        "tags": ["lxc"],
        "vmid": 210,
    },
    "full_qemu": {
        "cores": 4,
        "custom_field_data": {
            "cloud_init_network": '{"version": 2, '
            '"ethernets": {"eth0": '
            '{"dhcp4": true}}}',
            "cloud_init_ssh_keys": "ssh-ed25519 AAAAKEY1 a@b\n"
            "\n"
            "ssh-ed25519 AAAAKEY2 "
            "c@d\n",
            "cloud_init_user": "operator",
            "cloud_init_user_data": "#cloud-config\npassword: hunter2\n",
            "proxbox_intent_state": "pending",
            "proxbox_last_apply_run_id": "11111111-2222-3333-4444-555555555555",
            "proxmox_iso": "local:iso/debian-12.iso",
            "proxmox_node": "pve-01",
            "proxmox_ostemplate": "local:vztmpl/debian-12.tar.zst",
            "proxmox_rootfs": "local-lvm:8",
            "proxmox_storage": "local-lvm",
            "proxmox_swap": "512",
            "proxmox_template_vmid": "9000",
        },
        "disk_gb": 50,
        "interfaces": [
            {
                "description": "primary",
                "enabled": True,
                "mac_address": "aa:bb:cc:dd:ee:01",
                "mtu": 1500,
                "name": "net0",
            }
        ],
        "ipv4": None,
        "ipv6": None,
        "memory": 8192,
        "name": "vm-full",
        "node": "pve-01",
        "tags": ["prod", "proxbox"],
        "vmid": 110,
    },
    "network_dict": {
        "cores": 8,
        "custom_field_data": {
            "cloud_init_network": {"config": [], "version": 1},
            "cloud_init_user": "root",
            "proxmox_node": "pve-05",
        },
        "disk_gb": 40,
        "interfaces": [
            {
                "description": None,
                "enabled": True,
                "mac_address": None,
                "mtu": None,
                "name": "net0",
            },
            {
                "description": None,
                "enabled": True,
                "mac_address": "aa:bb:cc:dd:ee:02",
                "mtu": None,
                "name": "net1",
            },
        ],
        "ipv4": None,
        "ipv6": None,
        "memory": 16384,
        "name": "vm-netdict",
        "node": "pve-05",
        "tags": [],
        "vmid": 510,
    },
    "partial_blank": {
        "cores": 2,
        "custom_field_data": {
            "cloud_init_network": "{not json",
            "cloud_init_ssh_keys": "   \n  \n",
            "cloud_init_user": "",
            "cloud_init_user_data": "   ",
            "proxmox_iso": None,
            "proxmox_node": "pve-04",
            "proxmox_storage": "",
            "proxmox_template_vmid": "not-a-number",
        },
        "disk_gb": None,
        "interfaces": [],
        "ipv4": None,
        "ipv6": None,
        "memory": 1024,
        "name": "vm-partial",
        "node": "pve-04",
        "tags": [],
        "vmid": 410,
    },
}

# These model-only cases are intentionally separate from the captured
# equivalence constants above. Their expected values were transcribed from the
# ProxmoxVMIntent contract, and their legacy custom-field values are either
# absent or contradictory so an old custom-field reader cannot satisfy them.
INTENT_MODEL_CASES = {
    "conflicting_custom_fields": FakeVM(
        pk=202,
        name="vm-conflicting-intent",
        vcpus=5,
        memory=5120,
        description="intent wins conflicts",
        custom_field_data={
            "proxmox_node": "legacy-node",
            "proxmox_storage": "legacy-storage",
            "proxmox_iso": "legacy-iso",
            "proxmox_template_vmid": "9999",
            "proxmox_swap": "999",
            "proxmox_rootfs": "legacy-rootfs",
            "proxmox_ostemplate": "legacy-template",
            "cloud_init_user": "legacy-user",
            "cloud_init_ssh_keys": "ssh-rsa LEGACY",
            "cloud_init_user_data": "#cloud-config\nhostname: legacy\n",
            "cloud_init_network": '{"legacy": true}',
        },
        intent=FakeIntent(
            target_node="intent-node-b",
            target_storage="intent-storage-b",
            iso="intent-iso-b",
            template_vmid=9602,
            swap=768,
            rootfs="intent-storage-b:32",
            ostemplate="intent-template-b",
            cloud_init_user="desired-user",
            cloud_init_ssh_keys="ssh-ed25519 DESIRED",
            cloud_init_user_data="#cloud-config\nhostname: desired\n",
            cloud_init_network='{"version": 1, "config": []}',
        ),
        disks=[FakeDisk(32)],
        tags=[FakeTag("desired")],
        sync_state=FakeSyncState(vm_id=620, vm_type="lxc", node_name="current-node-b"),
    ),
    "empty_custom_fields": FakeVM(
        pk=201,
        name="vm-intent-only",
        vcpus=3,
        memory=3072,
        description="intent only values",
        custom_field_data={},
        intent=FakeIntent(
            target_node="intent-node-a",
            target_storage="intent-storage-a",
            iso="intent-iso-a",
            template_vmid=9601,
            swap=256,
            rootfs="intent-storage-a:24",
            ostemplate="intent-template-a",
            cloud_init_user="intent-user-a",
            cloud_init_ssh_keys="ssh-ed25519 INTENT-A\nssh-rsa INTENT-B\n",
            cloud_init_user_data=("#cloud-config\npackages:\n  - qemu-guest-agent\n"),
            cloud_init_network=(
                '{"version": 2, "ethernets": {"ens18": {"dhcp4": true}}}'
            ),
        ),
        disks=[FakeDisk(24)],
        tags=[FakeTag("intent-only")],
        sync_state=FakeSyncState(vm_id=610, vm_type="qemu", node_name="current-node-a"),
    ),
}

INTENT_MODEL_PREV_STATES = {
    "conflicting_custom_fields": {
        "kind": "lxc",
        "name": "vm-conflicting-intent",
    },
    "empty_custom_fields": {"kind": "qemu", "name": "vm-intent-only"},
}

GOLDEN_INTENT_MODEL_VM_PAYLOADS = {
    "conflicting_custom_fields": {
        "cloud_init": {
            "network": {"config": [], "version": 1},
            "ssh_keys": ["ssh-ed25519 DESIRED"],
            "user": "desired-user",
            "user_data": "#cloud-config\nhostname: desired\n",
        },
        "cores": 5,
        "description": "intent wins conflicts",
        "disk_gb": 32,
        "iso": "intent-iso-b",
        "memory": 5120,
        "name": "vm-conflicting-intent",
        "node": "intent-node-b",
        "storage": "intent-storage-b",
        "tags": ["desired"],
        "template_vmid": 9602,
        "vmid": 620,
    },
    "empty_custom_fields": {
        "cloud_init": {
            "network": {
                "ethernets": {"ens18": {"dhcp4": True}},
                "version": 2,
            },
            "ssh_keys": ["ssh-ed25519 INTENT-A", "ssh-rsa INTENT-B"],
            "user": "intent-user-a",
            "user_data": "#cloud-config\npackages:\n  - qemu-guest-agent\n",
        },
        "cores": 3,
        "description": "intent only values",
        "disk_gb": 24,
        "iso": "intent-iso-a",
        "memory": 3072,
        "name": "vm-intent-only",
        "node": "intent-node-a",
        "storage": "intent-storage-a",
        "tags": ["intent-only"],
        "template_vmid": 9601,
        "vmid": 610,
    },
}

GOLDEN_INTENT_MODEL_LXC_PAYLOADS = {
    "conflicting_custom_fields": {
        "cloud_init": {
            "network": {"config": [], "version": 1},
            "ssh_keys": ["ssh-ed25519 DESIRED"],
            "user": "desired-user",
            "user_data": "#cloud-config\nhostname: desired\n",
        },
        "cores": 5,
        "description": "intent wins conflicts",
        "memory": 5120,
        "name": "vm-conflicting-intent",
        "node": "intent-node-b",
        "ostemplate": "intent-template-b",
        "rootfs": "intent-storage-b:32",
        "storage": "intent-storage-b",
        "swap": 768,
        "tags": ["desired"],
        "vmid": 620,
    },
    "empty_custom_fields": {
        "cloud_init": {
            "network": {
                "ethernets": {"ens18": {"dhcp4": True}},
                "version": 2,
            },
            "ssh_keys": ["ssh-ed25519 INTENT-A", "ssh-rsa INTENT-B"],
            "user": "intent-user-a",
            "user_data": "#cloud-config\npackages:\n  - qemu-guest-agent\n",
        },
        "cores": 3,
        "description": "intent only values",
        "memory": 3072,
        "name": "vm-intent-only",
        "node": "intent-node-a",
        "ostemplate": "intent-template-a",
        "rootfs": "intent-storage-a:24",
        "storage": "intent-storage-a",
        "swap": 256,
        "tags": ["intent-only"],
        "vmid": 610,
    },
}

GOLDEN_INTENT_MODEL_UPDATE_DELTAS = {
    "conflicting_custom_fields": {
        "cloud_init": {
            "network": {"config": [], "version": 1},
            "ssh_keys": ["ssh-ed25519 DESIRED"],
            "user": "desired-user",
            "user_data": "#cloud-config\nhostname: desired\n",
        },
        "cores": 5,
        "description": "intent wins conflicts",
        "memory": 5120,
        "node": "intent-node-b",
        "ostemplate": "intent-template-b",
        "rootfs": "intent-storage-b:32",
        "storage": "intent-storage-b",
        "swap": 768,
        "tags": ["desired"],
        "vmid": 620,
    },
    "empty_custom_fields": {
        "cloud_init": {
            "network": {
                "ethernets": {"ens18": {"dhcp4": True}},
                "version": 2,
            },
            "ssh_keys": ["ssh-ed25519 INTENT-A", "ssh-rsa INTENT-B"],
            "user": "intent-user-a",
            "user_data": "#cloud-config\npackages:\n  - qemu-guest-agent\n",
        },
        "cores": 3,
        "description": "intent only values",
        "disk_gb": 24,
        "iso": "intent-iso-a",
        "memory": 3072,
        "node": "intent-node-a",
        "storage": "intent-storage-a",
        "tags": ["intent-only"],
        "template_vmid": 9601,
        "vmid": 610,
    },
}

__all__ = (
    "CASES",
    "FULL_CF",
    "GOLDEN_INTENT_MODEL_LXC_PAYLOADS",
    "GOLDEN_INTENT_MODEL_UPDATE_DELTAS",
    "GOLDEN_INTENT_MODEL_VM_PAYLOADS",
    "GOLDEN_LXC_PAYLOAD",
    "GOLDEN_METADATA_SNAPSHOT",
    "GOLDEN_UPDATE_DELTA",
    "GOLDEN_VM_PAYLOAD",
    "INTENT_MODEL_CASES",
    "INTENT_MODEL_PREV_STATES",
    "PREV_STATES",
)
