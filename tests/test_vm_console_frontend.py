"""Static and lightweight runtime contracts for the standalone VM console."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = (
    REPO_ROOT / "netbox_proxbox" / "templates" / "netbox_proxbox" / "vm_console.html"
)
JS_PATH = (
    REPO_ROOT / "netbox_proxbox" / "static" / "netbox_proxbox" / "js" / "vm_console.js"
)
CSS_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "static"
    / "netbox_proxbox"
    / "css"
    / "vm_console.css"
)
NOVNC_PATH = (
    REPO_ROOT / "netbox_proxbox" / "static" / "netbox_proxbox" / "vendor" / "novnc"
)
NOVNC_SOURCE_PATH = NOVNC_PATH / "SOURCE.md"
NOVNC_MANIFEST_PATH = NOVNC_PATH / "RUNTIME_FILES.txt"
RUNTIME_TEST_PATH = REPO_ROOT / "tests" / "js" / "vm_console_runtime.mjs"
ARTIFACT_VERIFIER_PATH = REPO_ROOT / "scripts" / "verify_vm_console_artifacts.py"
GITHUB_CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GITEA_CI_PATH = REPO_ROOT / ".gitea" / "workflows" / "ci.yml"

CORE_FILES = {
    "core/base64.js",
    "core/crypto/aes.js",
    "core/crypto/bigint.js",
    "core/crypto/crypto.js",
    "core/crypto/des.js",
    "core/crypto/dh.js",
    "core/crypto/md5.js",
    "core/crypto/rsa.js",
    "core/decoders/copyrect.js",
    "core/decoders/h264.js",
    "core/decoders/hextile.js",
    "core/decoders/jpeg.js",
    "core/decoders/raw.js",
    "core/decoders/rre.js",
    "core/decoders/tight.js",
    "core/decoders/tightpng.js",
    "core/decoders/zlib.js",
    "core/decoders/zrle.js",
    "core/deflator.js",
    "core/display.js",
    "core/encodings.js",
    "core/inflator.js",
    "core/input/domkeytable.js",
    "core/input/fixedkeys.js",
    "core/input/gesturehandler.js",
    "core/input/keyboard.js",
    "core/input/keysym.js",
    "core/input/keysymdef.js",
    "core/input/util.js",
    "core/input/vkeys.js",
    "core/input/xtscancodes.js",
    "core/ra2.js",
    "core/rfb.js",
    "core/util/browser.js",
    "core/util/cursor.js",
    "core/util/element.js",
    "core/util/events.js",
    "core/util/eventtarget.js",
    "core/util/int.js",
    "core/util/logging.js",
    "core/util/strings.js",
    "core/websock.js",
}
PAKO_FILES = {
    "vendor/pako/LICENSE",
    "vendor/pako/lib/utils/common.js",
    "vendor/pako/lib/zlib/adler32.js",
    "vendor/pako/lib/zlib/constants.js",
    "vendor/pako/lib/zlib/crc32.js",
    "vendor/pako/lib/zlib/deflate.js",
    "vendor/pako/lib/zlib/gzheader.js",
    "vendor/pako/lib/zlib/inffast.js",
    "vendor/pako/lib/zlib/inflate.js",
    "vendor/pako/lib/zlib/inftrees.js",
    "vendor/pako/lib/zlib/messages.js",
    "vendor/pako/lib/zlib/trees.js",
    "vendor/pako/lib/zlib/zstream.js",
}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree_digest(root: Path, files: set[str]) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(files):
        digest.update(relative_path.encode())
        digest.update(b"\0")
        digest.update((root / relative_path).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _regular_file_inventory(root: Path) -> set[str]:
    entries = [
        path for path in root.rglob("*") if path.is_symlink() or not path.is_dir()
    ]
    invalid = [
        path.relative_to(root).as_posix()
        for path in entries
        if path.is_symlink() or not path.is_file()
    ]
    assert invalid == [], f"vendored runtime entries must be regular files: {invalid}"
    return {path.relative_to(root).as_posix() for path in entries}


def test_template_loads_console_assets_and_server_owned_urls() -> None:
    source = _source(TEMPLATE_PATH)

    assert 'id="proxbox-vm-console"' in source
    assert 'data-session-url="{{ session_url }}"' in source
    assert 'data-csrf-token="{{ csrf_token }}"' in source
    assert 'data-vm-type="{{ vm_type }}"' in source
    assert "vendor/xterm/xterm.css" in source
    assert "vendor/xterm/xterm.js" in source
    assert "vendor/novnc/core/rfb.js" in source
    assert "css/vm_console.css" in source
    assert 'type="module"' in source
    assert "js/vm_console.js" in source
    assert "{% url" not in source


def test_template_limits_protocol_selector_by_guest_type() -> None:
    source = _source(TEMPLATE_PATH)
    qemu_start = source.index('{% if vm_type == "qemu" %}')
    qemu_end = source.index("{% endif %}", qemu_start)

    assert 'value="novnc"' in source[qemu_start:qemu_end]
    assert 'value="term"' in source[qemu_end:]
    assert source.count('value="novnc"') == 1
    assert source.count('value="term"') == 1
    assert (
        'data-console-ready="{% if console_ready %}true{% else %}false{% endif %}"'
        in source
    )
    assert "{% if not console_ready %}disabled{% endif %}" in source


def test_unavailable_console_explains_and_offers_authorized_repair() -> None:
    source = _source(TEMPLATE_PATH)

    assert "{{ remediation }}" in source
    assert "{{ error_code }}" in source
    assert "{% if can_quick_fix %}" in source
    assert 'action="{{ quick_fix_url }}"' in source
    assert "Repair all enabled endpoints" in source
    assert "every enabled Proxmox endpoint" in source
    assert "remove stale synchronized NetBox inventory outside this VM" in source
    assert "{% csrf_token %}" in source


def test_session_request_and_response_are_minimal_and_hide_upstream_details() -> None:
    source = _source(JS_PATH)

    assert "this.env.fetch(this.sessionUrl" in source
    assert 'method: "POST"' in source
    assert '"Content-Type": "application/json"' in source
    assert '"X-CSRFToken": this.csrfToken' in source
    assert '"X-Requested-With": "XMLHttpRequest"' in source
    assert "JSON.stringify({ console_type: consoleType })" in source
    assert "payload?.remediation" in source
    assert "payload.remediation.length <= 600" in source
    assert (
        '"websocket_url",\n  "stream_token",\n  "expires_at",\n  "console_type",'
        in source
    )
    assert "Object.keys(payload).filter" in source
    assert "this.createSocket(session.websocket_url, generation)" in source
    assert 'websocketUrl.protocol !== "wss:"' in source
    assert 'websocketUrl.protocol === "ws:"' not in source

    for forbidden in (
        "external-console.example.test",
        '"/api/',
        "proxmox_host",
        "proxmox_port",
        "verify_ssl",
        "vncticket",
        "X-Proxbox-API-Key",
        "Authorization",
    ):
        assert forbidden not in source


def test_novnc_is_dynamic_interactive_and_uses_no_browser_credentials() -> None:
    source = _source(JS_PATH)

    assert "this.env.importRfb(this.novncModuleUrl)" in source
    assert "new RFB(this.elements.novncContainer, session.websocket_url, {" in source
    assert "wsProtocols: protocols" in source
    assert "this.rfb.scaleViewport = true" in source
    assert "this.rfb.resizeSession = true" in source
    assert "this.rfb.viewOnly = false" in source
    assert 'querySelector("canvas")' in source
    assert "focusTarget.focus()" in source
    assert ".credentials =" not in source
    assert "rfb.credentials" not in source


def test_terminal_implements_proxmox_framing_and_raw_input() -> None:
    source = _source(JS_PATH)

    assert "new this.env.WebSocket(url, protocols)" in source
    assert 'this.socket.binaryType = "arraybuffer"' in source
    assert (
        "this.socket.send(`1:${this.terminal.rows}:${this.terminal.cols}:0`)" in source
    )
    assert 'this.socket.send("0")' in source
    assert 'raw.startsWith("d")' in source
    assert "bytes[0] === 100" in source
    assert "this.terminal.write(frame.payload)" in source
    assert "this.terminal.onData((data)" in source
    assert "this.socket.send(data)" in source
    assert "JSON.stringify({ type:" not in source


def test_stream_token_uses_a_separate_subprotocol_and_stays_private() -> None:
    source = _source(JS_PATH)

    assert "const STREAM_TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,256}$/" in source
    assert '["binary", `proxbox-token.${storedToken.value}`]' in source
    assert "websocketUrl.search || websocketUrl.hash" in source
    assert "this.streamToken = null" in source
    assert "this.storeStreamToken(session.stream_token, generation)" in source
    assert "this.clearStreamToken()" in source
    assert "this.clearStreamToken(generation)" in source
    assert 'session.stream_token = ""' in source
    assert 'protocols.fill("")' in source
    assert "protocols.length = 0" in source
    assert "?token=" not in source
    assert "searchParams" not in source
    assert "console.log" not in source
    assert "console.error" not in source
    assert "console.warn" not in source
    assert all(
        not ("streamToken" in line and "textContent" in line)
        for line in source.splitlines()
    )


def test_retry_and_cleanup_are_bounded_and_lifecycle_complete() -> None:
    source = _source(JS_PATH)

    assert "const MAX_AUTO_RETRIES = 2" in source
    assert "this.retryAttempt >= MAX_AUTO_RETRIES" in source
    assert "AUTO_RETRY_DELAYS_MS[this.retryAttempt]" in source
    assert "setInterval" not in source
    assert "this.requestAbort.abort()" in source
    assert "this.rfb.disconnect()" in source
    assert "this.socket.close(1000" in source
    assert "this.terminalInput.dispose()" in source
    assert "this.terminal.dispose()" in source
    assert "this.resizeObserver.disconnect()" in source
    assert "this.env.window.cancelAnimationFrame(this.resizeFrame)" in source
    assert 'this.env.window.addEventListener("pagehide"' in source
    assert 'this.env.window.addEventListener("unload"' in source

    for operator_message in (
        "session expired",
        "session was already used",
        "server error",
        "Automatic retries are exhausted",
    ):
        assert operator_message in source


def test_authored_console_assets_avoid_unsafe_dom_sinks() -> None:
    for path in (TEMPLATE_PATH, JS_PATH, CSS_PATH):
        source = _source(path)
        assert "innerHTML" not in source
        assert "dangerouslySetInnerHTML" not in source
        assert "eval(" not in source
        assert "new Function" not in source

    css_source = _source(CSS_PATH)
    assert "transition: all" not in css_source
    assert "min-height: 40px" in css_source
    assert "transform: scale(0.96)" in css_source


def test_vendored_novnc_170_runtime_tree_is_exact() -> None:
    runtime_files = {"LICENSE.txt", *CORE_FILES, *PAKO_FILES}
    expected_files = {"RUNTIME_FILES.txt", "SOURCE.md", *runtime_files}
    actual_files = _regular_file_inventory(NOVNC_PATH)

    assert actual_files == expected_files
    assert _tree_digest(NOVNC_PATH, runtime_files) == (
        "d17b88afeba9b787b886b73082a7e09cb578bfa670fd14172c53e48d87d5969b"
    )
    assert set(_source(NOVNC_MANIFEST_PATH).splitlines()) == runtime_files


@pytest.mark.parametrize("entry_kind", ["symlink_file", "symlink_directory", "fifo"])
def test_vendored_runtime_inventory_rejects_non_regular_entries(
    tmp_path: Path, entry_kind: str
) -> None:
    runtime_root = tmp_path / "novnc"
    runtime_root.mkdir()
    invalid = runtime_root / "invalid.js"
    if entry_kind.startswith("symlink"):
        target = runtime_root / "target"
        target_is_directory = entry_kind == "symlink_directory"
        if target_is_directory:
            target.mkdir()
        else:
            target.write_text("export const safe = true;", encoding="utf-8")
        invalid.symlink_to(target.name, target_is_directory=target_is_directory)
    else:
        os.mkfifo(invalid)

    with pytest.raises(AssertionError, match="must be regular files"):
        _regular_file_inventory(runtime_root)


def test_vendored_novnc_runtime_is_git_tracked() -> None:
    runtime_files = {"LICENSE.txt", *CORE_FILES, *PAKO_FILES}
    prefix = NOVNC_PATH.relative_to(REPO_ROOT).as_posix()
    expected = {f"{prefix}/{relative_path}" for relative_path in runtime_files}
    result = subprocess.run(
        ["git", "ls-files", "--", prefix],
        cwd=REPO_ROOT,
        text=True,
        check=True,
        capture_output=True,
    )

    assert expected <= set(result.stdout.splitlines())


def test_pako_gitignore_exceptions_are_limited_to_the_runtime_manifest() -> None:
    ignored_examples = [
        "netbox_proxbox/static/netbox_proxbox/vendor/novnc/vendor/pako/lib/extra.js",
        "netbox_proxbox/static/netbox_proxbox/vendor/novnc/vendor/pako/lib/utils/extra.js",
        "netbox_proxbox/static/netbox_proxbox/vendor/novnc/vendor/pako/lib/zlib/extra.js",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", *ignored_examples],
        cwd=REPO_ROOT,
        text=True,
        check=True,
        capture_output=True,
    )

    assert set(result.stdout.splitlines()) == set(ignored_examples)


def test_vendoring_record_pins_source_and_reconstruction() -> None:
    source = _source(NOVNC_SOURCE_PATH)

    assert "noVNC 1.7.0" in source
    assert "`v1.7.0`" in source
    assert "https://registry.npmjs.org/@novnc/novnc/-/novnc-1.7.0.tgz" in source
    assert (
        "sha512-ucEJOx4T2avIRCleodk7YobZj5O2Ga2AeLfQ69A/"
        "yjG9HHba2+PDgwSkN3FttrmG+70ZGx21sElNFouK13RzyA=="
    ) in source
    assert "sha512sum" in source
    assert 'package/core" ./core' in source
    assert 'package/LICENSE.txt" ./LICENSE.txt' in source
    assert "vendor/pako/LICENSE" in source
    assert "vendor/pako/lib/zlib" in source


def _artifact_verifier():
    spec = importlib.util.spec_from_file_location(
        "_vm_console_artifact_verifier", ARTIFACT_VERIFIER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_distributions(dist_dir: Path, files: set[str]) -> None:
    with zipfile.ZipFile(dist_dir / "netbox_proxbox-test.whl", mode="w") as wheel:
        for name in files:
            wheel.writestr(name, b"")
    with tarfile.open(dist_dir / "netbox_proxbox-test.tar.gz", mode="w:gz") as sdist:
        for name in files:
            info = tarfile.TarInfo(f"netbox_proxbox-test/{name}")
            info.size = 0
            sdist.addfile(info, io.BytesIO())


def test_distribution_verifier_accepts_complete_archives(tmp_path: Path) -> None:
    verifier = _artifact_verifier()
    expected = verifier.expected_package_files()
    _fake_distributions(tmp_path, expected)

    wheel, sdist = verifier.verify_distributions(tmp_path)

    assert wheel.suffix == ".whl"
    assert sdist.name.endswith(".tar.gz")


def test_distribution_verifier_rejects_a_missing_runtime_file(tmp_path: Path) -> None:
    verifier = _artifact_verifier()
    expected = verifier.expected_package_files()
    missing = "netbox_proxbox/static/netbox_proxbox/vendor/novnc/core/rfb.js"
    _fake_distributions(tmp_path, expected - {missing})

    with pytest.raises(SystemExit, match="core/rfb.js"):
        verifier.verify_distributions(tmp_path)


def test_package_builds_run_the_distribution_verifier() -> None:
    command = "python scripts/verify_vm_console_artifacts.py dist"

    assert command in _source(GITHUB_CI_PATH)
    assert f".venv/bin/{command}" in _source(GITEA_CI_PATH)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_console_browser_state_machine_at_runtime() -> None:
    subprocess.run(
        [
            "node",
            "--experimental-default-type=module",
            str(RUNTIME_TEST_PATH),
            str(JS_PATH),
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
