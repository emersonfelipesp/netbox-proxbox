"""Exercise explicit browser approval against a scripted API under Node.js."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "netbox_proxbox/static/netbox_proxbox/js/connection-authority.js"
HARNESS = r"""
import {initConnectionAuthority} from './authority.mjs';
const scenario = JSON.parse(process.argv[2]);
const nodes = new Map();
function element() {
    return {disabled: false, textContent: '', value: 'csrf-reviewed',
        classList: {add() {}, remove() {}},
        addEventListener(event, fn) {this.handler = fn;}};
}
const panel = {
    dataset: {authorityUrl: '/api/target/connection-authority/',
        endpointEnabled: scenario.enabled === false ? 'false' : 'true',
        canChange: scenario.canChange === false ? 'false' : 'true'},
    querySelector(selector) {
        if (!nodes.has(selector)) nodes.set(selector, element());
        return nodes.get(selector);
    },
};
const requests = [];
let index = 0;
const request = async (url, options) => {
    requests.push({url, ...options});
    const step = scenario.responses[index++];
    if (step.throw) throw new Error('sensitive transport failure');
    if (step.stallFetch) {
        return new Promise(() => {});
    }
    return {
        ok: step.status === 200,
        status: step.status,
        json: async () => {
            if (step.stallBody) {
                return new Promise(() => {});
            }
            return step.body;
        },
    };
};
const initOptions = {};
if (typeof scenario.deadlineMs === 'number') {
    initOptions.requestDeadlineMs = scenario.deadlineMs;
}
initConnectionAuthority(panel, request, initOptions);
const review = panel.querySelector('[data-proxbox-connection-authority-review]');
const approve = panel.querySelector('[data-proxbox-connection-authority-approve]');
const states = [];
async function settle() {for (let i = 0; i < 20; i++) await Promise.resolve();}
async function waitDeadline() {
    const ms = typeof scenario.deadlineMs === 'number' ? scenario.deadlineMs : 15000;
    await new Promise((resolve) => setTimeout(resolve, ms + 50));
    await settle();
}
function recordState() {
    states.push({
        disabled: approve.disabled,
        reviewDisabled: review.disabled,
        requests: requests.length,
    });
}
await settle();
recordState();
for (const action of scenario.actions) {
    const button = action === 'review' ? review : approve;
    button.handler();
    if (scenario.duplicate) button.handler();
    if (scenario.waitDeadlineAfter === action) {
        await waitDeadline();
    } else {
        await settle();
    }
    recordState();
}
console.log(JSON.stringify({requests, states,
    status: panel.querySelector('[data-proxbox-connection-authority-status]').textContent,
    domain: panel.querySelector('[data-proxbox-connection-authority-field="domain"]').textContent}));
"""


def payload(*, approved=False, fingerprint="a" * 64):
    return {
        "target_fingerprint": fingerprint,
        "approved": approved,
        "target": {
            "kind": "proxmoxendpoint",
            "domain": "pve.example.test",
            "ip_address": "",
            "port": 443,
            "verify_ssl": True,
            "username": "root@pam",
            "token_name": "plugin",
            "token_version": "",
        },
    }


@pytest.fixture
def browser(tmp_path):
    node = shutil.which("node")
    assert node, "Node.js is required for browser approval regression tests"
    shutil.copy(SCRIPT, tmp_path / "authority.mjs")
    harness = tmp_path / "harness.mjs"
    harness.write_text(HARNESS)

    def run(**scenario):
        result = subprocess.run(
            [node, str(harness), json.dumps(scenario)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return json.loads(result.stdout)

    return run


def test_explicit_review_then_approval_sends_only_reviewed_fingerprint(browser):
    result = browser(
        responses=[
            {"status": 200, "body": payload()},
            {"status": 200, "body": payload(approved=True)},
        ],
        actions=["approve", "review", "approve"],
        duplicate=True,
    )
    assert result["states"][0] == {
        "disabled": True,
        "reviewDisabled": False,
        "requests": 0,
    }
    assert result["states"][1]["requests"] == 0
    assert [r["method"] for r in result["requests"]] == ["GET", "PUT"]
    approval = result["requests"][1]
    assert json.loads(approval["body"]) == {"target_fingerprint": "a" * 64}
    assert approval["headers"]["X-CSRFToken"] == "csrf-reviewed"
    assert approval["credentials"] == "same-origin"
    assert approval["redirect"] == "error"
    assert approval["cache"] == "no-store"
    assert result["states"][-1]["disabled"] is True


@pytest.mark.parametrize("enabled,can_change", [(False, True), (True, False)])
def test_disabled_or_read_only_panel_never_submits_approval(
    browser, enabled, can_change
):
    result = browser(
        responses=[{"status": 200, "body": payload()}],
        actions=["review", "approve"],
        enabled=enabled,
        canChange=can_change,
    )
    assert [r["method"] for r in result["requests"]] == ["GET"]
    assert result["states"][-1]["disabled"] is True


@pytest.mark.parametrize(
    "failure",
    [
        {"status": 409, "body": {}},
        {"status": 403, "body": {}},
        {"status": 500, "body": {}},
        {"throw": True},
        {"status": 200, "body": payload(approved=False)},
        {"status": 200, "body": payload(approved=True, fingerprint="b" * 64)},
    ],
)
def test_failed_approval_requires_a_new_review(browser, failure):
    result = browser(
        responses=[{"status": 200, "body": payload()}, failure],
        actions=["review", "approve", "approve"],
    )
    assert len(result["requests"]) == 2
    assert result["states"][-1]["disabled"] is True
    assert "sensitive transport failure" not in result["status"]


@pytest.mark.parametrize(
    "body", [{}, payload(fingerprint="wrong"), {**payload(), "target": {}}]
)
def test_malformed_review_never_enables_approval(browser, body):
    result = browser(
        responses=[{"status": 200, "body": body}], actions=["review", "approve"]
    )
    assert len(result["requests"]) == 1
    assert result["states"][-1]["disabled"] is True


def test_stale_target_is_reviewed_again_before_new_approval(browser):
    result = browser(
        responses=[
            {"status": 200, "body": payload()},
            {"status": 409, "body": {}},
            {"status": 200, "body": payload(fingerprint="b" * 64)},
            {"status": 200, "body": payload(approved=True, fingerprint="b" * 64)},
        ],
        actions=["review", "approve", "approve", "review", "approve"],
    )
    assert [r["method"] for r in result["requests"]] == ["GET", "PUT", "GET", "PUT"]
    assert json.loads(result["requests"][-1]["body"])["target_fingerprint"] == "b" * 64


@pytest.mark.parametrize(
    ("method", "stall_field", "actions", "wait_after"),
    [
        ("GET", "stallFetch", ["review"], "review"),
        ("GET", "stallBody", ["review"], "review"),
        (
            "PUT",
            "stallFetch",
            ["review", "approve", "approve"],
            "approve",
        ),
        (
            "PUT",
            "stallBody",
            ["review", "approve", "approve"],
            "approve",
        ),
    ],
)
def test_stalled_authority_request_restores_controls_without_retry(
    browser, method, stall_field, actions, wait_after
):
    review_step = {"status": 200, "body": payload()}
    approve_step = {"status": 200, "body": payload(approved=True)}
    if method == "GET":
        review_step[stall_field] = True
    else:
        approve_step[stall_field] = True
    result = browser(
        deadlineMs=50,
        waitDeadlineAfter=wait_after,
        responses=[review_step, approve_step],
        actions=actions,
    )
    expected_methods = ["GET"] if method == "GET" else ["GET", "PUT"]
    assert [r["method"] for r in result["requests"]] == expected_methods
    assert result["states"][-1]["disabled"] is True
    assert result["states"][-1]["reviewDisabled"] is False
    assert "connection-authority-deadline" not in result["status"]
    if method == "PUT":
        assert result["domain"] == "—"
