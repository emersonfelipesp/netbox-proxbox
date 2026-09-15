"""Behavior tests for CLI authentication, bounds, and exit statuses."""

from __future__ import annotations

import asyncio
import ast
import json
import stat
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol, cast

import pytest

for module_name in ("aiohttp", "click", "pydantic", "rich", "typer"):
    pytest.importorskip(module_name)

import proxbox_cli  # noqa: E402
import proxbox_cli.client as client_module  # noqa: E402
import proxbox_cli.config as config_module  # noqa: E402
from proxbox_cli import runtime  # noqa: E402
from proxbox_cli.client import ProxboxApiClient  # noqa: E402
from proxbox_cli.config import (  # noqa: E402
    ALLOW_INSECURE_TRANSPORT_ENV_VAR,
    API_KEY_ENV_VAR,
    BASE_URL_ENV_VAR,
    INSECURE_TRANSPORT_WARNING,
    MAX_RESPONSE_BYTES_ENV_VAR,
    TIMEOUT_ENV_VAR,
    Config,
    _is_valid_origin,
    config_path,
    load_config,
    save_config,
)
from proxbox_cli.errors import (  # noqa: E402
    ConfigurationError,
    RedirectRefusedError,
    ResponseTooLargeError,
)


class _Backend(Protocol):
    """Shared interface for the local server and socket-restricted fallback."""

    status: int
    body: bytes
    location: str | None
    received_headers: list[dict[str, str]]

    @property
    def base_url(self) -> str: ...


class _BackendServer(ThreadingHTTPServer):
    """Mutable local HTTP backend used by the transport behavior tests."""

    status = 200
    body = b'{"version":"test"}'
    location: str | None = None
    received_headers: list[dict[str, str]]

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _BackendHandler)
        self.received_headers = []

    @property
    def base_url(self) -> str:
        """Return the loopback origin selected by the operating system."""
        host, port = self.server_address
        return f"http://{host}:{port}"


class _BackendHandler(BaseHTTPRequestHandler):
    """Serve one configurable response and retain request headers."""

    def do_GET(self) -> None:
        """Return the response selected by the current test."""
        server = cast(_BackendServer, self.server)
        server.received_headers.append(dict(self.headers.items()))
        self.send_response(server.status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(server.body)))
        if server.location is not None:
            self.send_header("Location", server.location)
        self.end_headers()
        self.wfile.write(server.body)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the hermetic test server silent."""


class _StalledBackendServer(ThreadingHTTPServer):
    """Accept a request but withhold all response bytes."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _StalledBackendHandler)
        self.request_seen = threading.Event()
        self.release = threading.Event()

    @property
    def base_url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"


class _StalledBackendHandler(BaseHTTPRequestHandler):
    """Hold an accepted request until the fixture releases it."""

    def do_GET(self) -> None:
        server = cast(_StalledBackendServer, self.server)
        server.request_seen.set()
        server.release.wait(timeout=2)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the hermetic stalled server silent."""


class _MemoryBackend:
    """In-memory fallback for runners that prohibit loopback sockets."""

    def __init__(self) -> None:
        self.status = 200
        self.body = b'{"version":"test"}'
        self.location: str | None = None
        self.received_headers: list[dict[str, str]] = []
        self.allow_redirects: list[bool] = []
        self.methods: list[str] = []
        self.timeouts: list[object] = []
        self.request_error: Exception | None = None
        self.request_seen = threading.Event()

    @property
    def base_url(self) -> str:
        """Return a valid inert origin for client URL construction."""
        return "http://127.0.0.1:8765"


class _MemoryContent:
    """Expose a response body through aiohttp's async chunk interface."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    async def iter_chunked(self, size: int):
        """Yield small chunks so bounds are exercised during iteration."""
        chunk_size = min(size, 7)
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start : start + chunk_size]


class _CapOracleContent:
    """Fail if a client keeps consuming after the first over-limit chunk."""

    async def iter_chunked(self, size: int):  # noqa: ARG002
        yield b"x" * 16
        yield b"x"
        raise AssertionError("response stream was consumed past the configured cap")


class _CapOracleResponse:
    """Minimal response carrying the mutation-sensitive cap oracle."""

    charset = "utf-8"
    content = _CapOracleContent()
    url = "http://127.0.0.1:8765/version"


class _MemoryResponse:
    """Async response context manager backed by `_MemoryBackend`."""

    charset = "utf-8"

    def __init__(self, backend: _MemoryBackend, url: str) -> None:
        self.status = backend.status
        self.content = _MemoryContent(backend.body)
        self.url = url
        self.headers = {"Content-Type": "application/json; charset=utf-8"}
        if backend.location is not None:
            self.headers["Location"] = backend.location

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _DelayedErrorResponse:
    """Model a connection attempt that stalls before timing out or failing."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def __aenter__(self):
        await asyncio.sleep(0.01)
        raise self.error

    async def __aexit__(self, *args: object) -> None:
        return None


class _MemorySession:
    """Minimal aiohttp session preserving request behavior for assertions."""

    def __init__(self, backend: _MemoryBackend) -> None:
        self.backend = backend

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def request(
        self, method: str, url: str, **kwargs: object
    ) -> _MemoryResponse | _DelayedErrorResponse:
        """Capture headers and redirect policy, then return the selected response."""
        self.backend.request_seen.set()
        if self.backend.request_error is not None:
            return _DelayedErrorResponse(self.backend.request_error)
        headers = cast(dict[str, str], kwargs["headers"])
        self.backend.received_headers.append(headers)
        self.backend.allow_redirects.append(bool(kwargs["allow_redirects"]))
        self.backend.methods.append(method)
        return _MemoryResponse(self.backend, url)


def _memory_session_factory(backend: _MemoryBackend):
    """Return a drop-in `aiohttp.ClientSession` constructor."""

    def factory(**kwargs: object) -> _MemorySession:
        backend.timeouts.append(kwargs["timeout"])
        return _MemorySession(backend)

    return factory


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Backend]:
    """Run a local HTTP server without external network access."""
    try:
        server = _BackendServer()
    except PermissionError:
        memory_backend = _MemoryBackend()
        monkeypatch.setattr(
            client_module.aiohttp,
            "ClientSession",
            _memory_session_factory(memory_backend),
        )
        yield memory_backend
        return
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _memory_stalled_backend(monkeypatch: pytest.MonkeyPatch) -> _MemoryBackend:
    """Install the timeout fallback used where loopback sockets are prohibited."""
    backend = _MemoryBackend()
    backend.request_error = TimeoutError("read stalled")
    monkeypatch.setattr(
        client_module.aiohttp, "ClientSession", _memory_session_factory(backend)
    )
    return backend


def _stop_stalled_server(
    server: _StalledBackendServer, thread: threading.Thread
) -> None:
    """Release and stop the stalled test server."""
    server.release.set()
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def stalled_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_StalledBackendServer | _MemoryBackend]:
    """Run a stalled backend with a fallback for socket-restricted runners."""
    try:
        server = _StalledBackendServer()
    except PermissionError:
        yield _memory_stalled_backend(monkeypatch)
        return
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        _stop_stalled_server(server, thread)


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep environment and config state isolated for every test."""
    for name in (
        API_KEY_ENV_VAR,
        BASE_URL_ENV_VAR,
        TIMEOUT_ENV_VAR,
        MAX_RESPONSE_BYTES_ENV_VAR,
        ALLOW_INSECURE_TRANSPORT_ENV_VAR,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runtime._CACHED_CONFIG = None
    yield
    runtime._CACHED_CONFIG = None


def _configure_backend(monkeypatch: pytest.MonkeyPatch, backend: _Backend) -> None:
    """Select the local backend and provide a valid API key."""
    monkeypatch.setenv(BASE_URL_ENV_VAR, backend.base_url)
    monkeypatch.setenv(API_KEY_ENV_VAR, "environment-secret")
    runtime._CACHED_CONFIG = None


def _write_config_text(value: str) -> Path:
    """Write raw config text under the isolated test directory."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    return path


def _answer_init_prompts(monkeypatch: pytest.MonkeyPatch, base_url: str) -> None:
    """Supply a backend origin and the default timeout to `pxb init`."""
    answers = iter([base_url, "30"])
    monkeypatch.setattr(
        proxbox_cli.typer, "prompt", lambda *args, **kwargs: next(answers)
    )


def _module_imports_aiohttp(path: Path) -> bool:
    """Return whether one Python module imports aiohttp."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "aiohttp" or alias.name.startswith("aiohttp.")
            for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (
            node.module == "aiohttp" or (node.module or "").startswith("aiohttp.")
        ):
            return True
    return False


def _substitution_writer(
    directory: Path, displaced: Path
) -> Callable[[int, str, str], None]:
    """Return a temp writer that swaps the directory path after writing."""
    real_write = config_module._write_temporary_config

    def write(descriptor: int, name: str, payload: str) -> None:
        real_write(descriptor, name, payload)
        directory.rename(displaced)
        directory.mkdir(mode=0o700)

    return write


def _fail_config_rename(*_: object, **__: object) -> None:
    """Raise the write failure used by the CLI exit-code test."""
    raise OSError("write failed")


def test_api_key_header_is_sent(backend: _Backend) -> None:
    client = ProxboxApiClient(Config(base_url=backend.base_url, api_key="test-secret"))

    response = asyncio.run(client.get("/version"))

    assert response.status == 200
    assert backend.received_headers[-1]["X-Proxbox-API-Key"] == "test-secret"


def test_init_never_persists_environment_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "environment-only-secret")
    _answer_init_prompts(monkeypatch, "http://localhost:8000")

    assert proxbox_cli.main(["init"]) == 0

    persisted = config_path().read_text()
    assert "environment-only-secret" not in persisted
    assert json.loads(persisted)["api_key"] is None


def test_init_same_origin_preserves_only_existing_file_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_config(Config(api_key="persisted-secret"))
    monkeypatch.setenv(API_KEY_ENV_VAR, "environment-only-secret")
    _answer_init_prompts(monkeypatch, "HTTP://LOCALHOST.:8000/")

    assert proxbox_cli.main(["init"]) == 0

    persisted = config_path().read_text()
    assert json.loads(persisted)["api_key"] == "persisted-secret"
    assert "environment-only-secret" not in persisted


def test_init_changed_origin_drops_existing_file_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_config(Config(base_url="https://old.example", api_key="persisted-secret"))
    _answer_init_prompts(monkeypatch, "https://new.example")

    assert proxbox_cli.main(["init"]) == 0

    persisted = json.loads(config_path().read_text())
    assert persisted["base_url"] == "https://new.example"
    assert persisted["api_key"] is None


def test_init_keep_api_key_allows_changed_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_config(Config(base_url="https://old.example", api_key="persisted-secret"))
    _answer_init_prompts(monkeypatch, "https://new.example")

    assert proxbox_cli.main(["init", "--keep-api-key"]) == 0

    persisted = json.loads(config_path().read_text())
    assert persisted["base_url"] == "https://new.example"
    assert persisted["api_key"] == "persisted-secret"


def test_changed_environment_origin_does_not_reuse_file_key(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    save_config(Config(base_url="https://file.example", api_key="file-secret"))
    backend.status = 401
    monkeypatch.setenv(BASE_URL_ENV_VAR, backend.base_url)

    assert proxbox_cli.main(["version"]) == 2

    captured = capsys.readouterr()
    assert "X-Proxbox-API-Key" not in backend.received_headers[-1]
    assert "selected PROXBOX_URL" in " ".join(captured.err.split())


def test_same_environment_origin_keeps_file_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_config(Config(base_url="https://file.example", api_key="file-secret"))
    monkeypatch.setenv(BASE_URL_ENV_VAR, "HTTPS://FILE.EXAMPLE.:443/")

    config = load_config()

    assert config.base_url == "https://file.example:443"
    assert config.api_key == "file-secret"


@pytest.mark.parametrize(
    ("file_origin", "environment_origin"),
    [
        ("https://backend.example", "http://backend.example"),
        ("https://backend.example:8443", "https://backend.example:9443"),
    ],
)
def test_same_hostname_transport_change_drops_file_key(
    file_origin: str,
    environment_origin: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_config(Config(base_url=file_origin, api_key="file-secret"))
    monkeypatch.setenv(BASE_URL_ENV_VAR, environment_origin)

    config = load_config()

    assert config.base_url == environment_origin
    assert config.api_key is None


def test_missing_api_key_is_actionable_exit_2(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend.status = 401
    backend.body = b'{"detail":"API key required."}'
    monkeypatch.setenv(BASE_URL_ENV_VAR, backend.base_url)

    exit_code = proxbox_cli.main(["version", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "PROXBOX_API_KEY" in captured.err
    assert "config file" in captured.err
    assert "X-Proxbox-API-Key" not in backend.received_headers[-1]


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [(200, 0), (401, 1), (404, 1), (500, 1)],
)
def test_main_maps_backend_status_to_exit_code_and_keeps_json_body(
    status: int,
    expected_exit: int,
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend.status = status
    backend.body = b'{"detail":"backend detail"}'
    _configure_backend(monkeypatch, backend)

    exit_code = proxbox_cli.main(["version", "--json"])

    captured = capsys.readouterr()
    assert exit_code == expected_exit
    assert "backend detail" in captured.out


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "600.1"])
def test_invalid_timeout_is_configuration_exit_2(
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(TIMEOUT_ENV_VAR, value)

    exit_code = proxbox_cli.main(["config"])

    assert exit_code == 2
    assert "timeout" in capsys.readouterr().err


@pytest.mark.parametrize(
    "value",
    [
        "ftp://backend.example",
        "http://user:secret@backend.example",
        "http://x/a",
        "http://backend.example:0",
        "http://",
        "http://.",
    ],
)
def test_invalid_base_url_is_configuration_exit_2(
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(BASE_URL_ENV_VAR, value)

    exit_code = proxbox_cli.main(["config"])

    assert exit_code == 2
    assert "base_url" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("backend.example", "http://backend.example"),
        ("HTTP://Backend.Example./", "http://backend.example"),
        ("https://Backend.Example.:8443/", "https://backend.example:8443"),
        ("http://127.0.0.1:8000/", "http://127.0.0.1:8000"),
        ("https://[2001:DB8::1]:443/", "https://[2001:db8::1]:443"),
    ],
)
def test_base_url_canonical_forms(value: str, expected: str) -> None:
    assert Config(base_url=value).base_url == expected


@pytest.mark.parametrize(
    ("attribute", "value", "raw"),
    [
        ("scheme", "ftp", "https://backend.example"),
        ("hostname", None, "https://backend.example"),
        ("hostname", ".", "https://backend.example"),
        ("hostname", "*", "https://backend.example"),
        ("username", "user", "https://backend.example"),
        ("password", "secret", "https://backend.example"),
        ("path", "/private", "https://backend.example"),
        ("query", "key=value", "https://backend.example"),
        ("fragment", "private", "https://backend.example"),
        ("port", 65536, "https://backend.example"),
        ("scheme", "https", "https://backend .example"),
    ],
)
def test_is_valid_origin_rejects_each_predicate(
    attribute: str, value: object, raw: str
) -> None:
    fields: dict[str, object] = {
        "scheme": "https",
        "hostname": "backend.example",
        "username": None,
        "password": None,
        "path": "",
        "query": "",
        "fragment": "",
        "port": 443,
    }
    fields[attribute] = value
    assert _is_valid_origin(cast(Any, SimpleNamespace(**fields)), raw) is False


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:8000",
        "http://localhost.:8000",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
    ],
)
def test_keyed_loopback_http_is_allowed(base_url: str) -> None:
    assert Config(base_url=base_url, api_key="secret").api_key == "secret"


def test_keyed_remote_http_is_configuration_exit_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(BASE_URL_ENV_VAR, "http://backend.example:8000")
    monkeypatch.setenv(API_KEY_ENV_VAR, "secret")

    assert proxbox_cli.main(["config"]) == 2
    rendered_error = " ".join(capsys.readouterr().err.split())
    assert "requires https://" in rendered_error


def test_dns_loopback_address_does_not_make_hostname_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: pytest.fail("base URL validation resolved DNS"),
    )
    monkeypatch.setenv(BASE_URL_ENV_VAR, "http://loopback.example:8000")
    monkeypatch.setenv(API_KEY_ENV_VAR, "secret")

    assert proxbox_cli.main(["config"]) == 2


def test_insecure_transport_opt_in_must_equal_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BASE_URL_ENV_VAR, "http://backend.example:8000")
    monkeypatch.setenv(API_KEY_ENV_VAR, "secret")
    monkeypatch.setenv(ALLOW_INSECURE_TRANSPORT_ENV_VAR, "true")

    assert proxbox_cli.main(["config"]) == 2


def test_keyed_remote_http_opt_in_warns(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(BASE_URL_ENV_VAR, "http://backend.example:8000")
    monkeypatch.setenv(API_KEY_ENV_VAR, "secret")
    monkeypatch.setenv(ALLOW_INSECURE_TRANSPORT_ENV_VAR, "1")

    assert load_config().base_url == "http://backend.example:8000"
    captured = capsys.readouterr()
    assert INSECURE_TRANSPORT_WARNING in captured.err
    assert "secret" not in captured.err


@pytest.mark.parametrize(
    "contents",
    [
        '{"base_url":',
        '{"unknown_setting": true}',
    ],
)
def test_bad_config_file_exits_2_without_http_dispatch(
    contents: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config_text(contents)
    monkeypatch.setattr(
        client_module.aiohttp,
        "ClientSession",
        lambda **kwargs: pytest.fail("HTTP dispatch occurred"),
    )

    assert proxbox_cli.main(["version"]) == 2


def test_insecure_transport_opt_in_is_not_a_config_field(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config_text(json.dumps({"allow_insecure_transport": True}))

    assert proxbox_cli.main(["config"]) == 2
    assert "allow_insecure_transport" in capsys.readouterr().err


def test_unreadable_config_file_exits_2_without_http_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.mkdir()
    monkeypatch.setattr(
        client_module.aiohttp,
        "ClientSession",
        lambda **kwargs: pytest.fail("HTTP dispatch occurred"),
    )

    assert proxbox_cli.main(["version"]) == 2


def test_invalid_timeout_in_config_file_is_exit_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_dir = tmp_path / "proxbox-cli"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(json.dumps({"timeout": 601}))

    assert proxbox_cli.main(["config"]) == 2
    assert "timeout" in capsys.readouterr().err


def test_initial_config_file_mode_is_owner_only() -> None:
    save_config(Config())

    assert stat.S_IMODE(config_path().parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(config_path().stat().st_mode) == 0o600


def test_config_directory_mode_is_fixed_without_path_chmod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = config_path().parent
    directory.mkdir()
    directory.chmod(0o755)
    monkeypatch.setattr(
        config_module.os,
        "chmod",
        lambda *args: pytest.fail("path-based chmod was used"),
    )

    save_config(Config())

    assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_config_save_refuses_symlink_destination(tmp_path: Path) -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    target = tmp_path / "target.json"
    target.write_text("untouched")
    path.symlink_to(target)

    with pytest.raises(ConfigurationError, match="symlink"):
        save_config(Config(timeout=45))

    assert target.read_text() == "untouched"


def test_config_save_refuses_symlinked_directory(tmp_path: Path) -> None:
    directory = config_path().parent
    target = tmp_path / "target-directory"
    target.mkdir(mode=0o700)
    directory.symlink_to(target, target_is_directory=True)

    with pytest.raises(ConfigurationError, match="config directory"):
        save_config(Config(timeout=45))

    assert not (target / "config.json").exists()


def test_config_save_refuses_directory_substitution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = config_path().parent
    displaced = tmp_path / "displaced"
    directory.mkdir(mode=0o700)
    writer = _substitution_writer(directory, displaced)
    monkeypatch.setattr(config_module, "_write_temporary_config", writer)
    with pytest.raises(ConfigurationError, match="changed during write"):
        save_config(Config(timeout=45))
    assert not config_path().exists()
    assert list(displaced.glob("*.tmp")) == []


def test_config_save_refuses_directory_destination(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = config_path()
    path.parent.mkdir(mode=0o700)
    path.mkdir()
    monkeypatch.setattr(proxbox_cli, "load_file_config", Config)
    monkeypatch.setattr(proxbox_cli, "_prompt_for_config", lambda *_: Config())

    assert proxbox_cli.main(["init"]) == 2

    rendered = " ".join(capsys.readouterr().err.split())
    assert "non-file CLI config destination" in rendered


def test_interrupted_config_write_leaves_no_partial_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt_fsync(descriptor: int) -> None:
        raise InterruptedError("simulated interruption")

    monkeypatch.setattr(config_module.os, "fsync", interrupt_fsync)
    with pytest.raises(ConfigurationError, match="Could not write CLI config file"):
        save_config(Config(timeout=45))

    assert not config_path().exists()
    assert list(config_path().parent.glob("*.tmp")) == []


def test_config_write_failure_is_cli_exit_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config_module.os, "rename", _fail_config_rename)
    _answer_init_prompts(monkeypatch, "http://localhost:8000")

    assert proxbox_cli.main(["init"]) == 2
    assert not config_path().exists()
    assert list(config_path().parent.glob("*.tmp")) == []


def test_temporary_name_collision_is_not_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = config_path().parent
    directory.mkdir(mode=0o700)
    collision = directory / ".config.json.collision.tmp"
    collision.write_text("not-owned-by-this-write")
    monkeypatch.setattr(
        config_module, "_temporary_config_name", lambda _: collision.name
    )

    with pytest.raises(ConfigurationError):
        save_config(Config())

    assert collision.read_text() == "not-owned-by-this-write"


def test_show_config_never_prints_api_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "secret-that-must-not-be-rendered")

    assert proxbox_cli.main(["config"]) == 0
    output = capsys.readouterr().out
    assert "API key  : configured" in output
    assert "secret-that-must-not-be-rendered" not in output


def test_response_body_cap_is_enforced_while_streaming() -> None:
    client = ProxboxApiClient(
        Config(base_url="http://127.0.0.1:8765", api_key="key", max_response_bytes=16)
    )

    with pytest.raises(ResponseTooLargeError, match="16 bytes"):
        asyncio.run(client._read_text(cast(Any, _CapOracleResponse())))


def test_every_http_method_disables_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _MemoryBackend()
    monkeypatch.setattr(
        client_module.aiohttp, "ClientSession", _memory_session_factory(backend)
    )
    client = ProxboxApiClient(Config(base_url=backend.base_url, api_key="key"))

    async def call_every_method() -> None:
        await client.get("/get")
        await client.post("/post", payload={"value": 1})
        await client.put("/put", payload={"value": 1})
        await client.delete("/delete")

    asyncio.run(call_every_method())
    assert backend.methods == ["GET", "POST", "PUT", "DELETE"]
    assert backend.allow_redirects == [False, False, False, False]


def test_client_bounds_connect_and_read_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _MemoryBackend()
    monkeypatch.setattr(
        client_module.aiohttp, "ClientSession", _memory_session_factory(backend)
    )
    client = ProxboxApiClient(Config(base_url=backend.base_url, timeout=0.05))

    assert asyncio.run(client.get("/version")).status == 200
    timeout = cast(Any, backend.timeouts[-1])
    assert timeout.total == 0.05
    assert timeout.sock_connect == 0.05
    assert timeout.sock_read == 0.05


def test_stalled_connect_timeout_returns_synthetic_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _MemoryBackend()
    backend.request_error = TimeoutError("connect stalled")
    monkeypatch.setattr(
        client_module.aiohttp, "ClientSession", _memory_session_factory(backend)
    )
    client = ProxboxApiClient(Config(base_url=backend.base_url, timeout=0.05))

    response = asyncio.run(client.get("/version"))

    assert response.status == 503
    assert response.text == "Connection error: connect stalled"


def test_stalled_read_returns_synthetic_503(
    stalled_backend: _StalledBackendServer | _MemoryBackend,
) -> None:
    client = ProxboxApiClient(
        Config(base_url=stalled_backend.base_url, api_key="key", timeout=0.05)
    )

    response = asyncio.run(client.get("/version"))

    assert stalled_backend.request_seen.wait(timeout=1)
    assert response.status == 503
    assert response.text.startswith("Connection error:")


def test_redirect_is_refused_without_disclosing_its_target(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend.status = 302
    backend.location = "https://redirect.example/private?token=secret"
    client = ProxboxApiClient(Config(base_url=backend.base_url, api_key="key"))

    with pytest.raises(RedirectRefusedError) as caught:
        asyncio.run(client.get("/version"))

    message = str(caught.value)
    assert "127.0.0.1" in message
    assert "redirect.example" not in message
    assert "/version" not in message
    _configure_backend(monkeypatch, backend)
    assert proxbox_cli.main(["version"]) == 1
    rendered_error = " ".join(capsys.readouterr().err.split())
    assert "redirects are not permitted" in rendered_error


@pytest.mark.parametrize(
    ("status", "body", "arguments", "expected_exit"),
    [
        (200, b'{"detail":"environment-secret"}', ["version", "--json"], 0),
        (500, b'{"detail":"environment-secret"}', ["version", "--json"], 1),
        (200, b'{"detail":"environment-secret"}', ["version"], 0),
        (200, b"malformed environment-secret body", ["version"], 0),
    ],
)
def test_response_output_redacts_configured_key(
    status: int,
    body: bytes,
    arguments: list[str],
    expected_exit: int,
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend.status = status
    backend.body = body
    _configure_backend(monkeypatch, backend)

    assert proxbox_cli.main(arguments) == expected_exit
    captured = capsys.readouterr()
    assert "environment-secret" not in captured.out
    assert "environment-secret" not in captured.err
    assert "[REDACTED]" in captured.out


def test_viewer_pydantic_prints_plain_text_success(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend.body = b"class GeneratedModel:\n    pass\n"
    _configure_backend(monkeypatch, backend)

    assert proxbox_cli.main(["proxmox", "viewer", "pydantic"]) == 0
    output = capsys.readouterr().out
    assert "Status: 200" in output
    assert "class GeneratedModel:" in output


def test_viewer_pydantic_non_2xx_exits_1(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend.status = 500
    backend.body = b"generation failed"
    _configure_backend(monkeypatch, backend)

    assert proxbox_cli.main(["proxmox", "viewer", "pydantic"]) == 1
    assert "generation failed" in capsys.readouterr().out


def test_viewer_pydantic_redacts_configured_key(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend.body = b'environment-secret = "credential"'
    _configure_backend(monkeypatch, backend)

    assert proxbox_cli.main(["proxmox", "viewer", "pydantic"]) == 0
    output = capsys.readouterr().out
    assert "environment-secret" not in output
    assert "[REDACTED]" in output


def test_json_escape_decoding_cannot_bypass_key_redaction(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = 'quote"secret'
    backend.body = json.dumps({"detail": secret}).encode()
    monkeypatch.setenv(BASE_URL_ENV_VAR, backend.base_url)
    monkeypatch.setenv(API_KEY_ENV_VAR, secret)

    assert proxbox_cli.main(["version", "--json"]) == 0
    output = capsys.readouterr().out
    assert "[REDACTED]" in output
    assert "quote" not in output


def test_connection_error_output_redacts_configured_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend = _MemoryBackend()
    backend.request_error = client_module.aiohttp.ClientConnectionError(
        "connection echoed environment-secret"
    )
    monkeypatch.setattr(
        client_module.aiohttp, "ClientSession", _memory_session_factory(backend)
    )
    monkeypatch.setenv(BASE_URL_ENV_VAR, backend.base_url)
    monkeypatch.setenv(API_KEY_ENV_VAR, "environment-secret")

    assert proxbox_cli.main(["version"]) == 1
    captured = capsys.readouterr()
    assert "environment-secret" not in captured.out
    assert "[REDACTED]" in captured.out


def test_transport_exception_stderr_redacts_configured_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend = _MemoryBackend()
    backend.request_error = RedirectRefusedError("echoed environment-secret")
    monkeypatch.setattr(
        client_module.aiohttp, "ClientSession", _memory_session_factory(backend)
    )
    monkeypatch.setenv(BASE_URL_ENV_VAR, backend.base_url)
    monkeypatch.setenv(API_KEY_ENV_VAR, "environment-secret")

    assert proxbox_cli.main(["version"]) == 1
    captured = capsys.readouterr()
    assert "environment-secret" not in captured.err
    assert "[REDACTED]" in captured.err


def test_environment_overrides_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "proxbox-cli"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "base_url": "http://file.example:8000",
                "api_key": "file-secret",
                "timeout": 12,
                "max_response_bytes": 1024,
            }
        )
    )
    monkeypatch.setenv(BASE_URL_ENV_VAR, "https://env.example:8443")
    monkeypatch.setenv(API_KEY_ENV_VAR, "environment-secret")
    monkeypatch.setenv(TIMEOUT_ENV_VAR, "45")
    monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV_VAR, "2048")

    config = load_config()

    assert config.base_url == "https://env.example:8443"
    assert config.api_key == "environment-secret"
    assert config.timeout == 45
    assert config.max_response_bytes == 2048


def test_aiohttp_is_imported_only_in_client_module() -> None:
    package = Path(proxbox_cli.__file__).parent
    imports = {
        path.relative_to(package)
        for path in package.rglob("*.py")
        if _module_imports_aiohttp(path)
    }
    assert imports == {Path("client.py")}


def test_keyboard_interrupt_returns_130(monkeypatch: pytest.MonkeyPatch) -> None:
    class InterruptingClient:
        def get(self, path: str) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(proxbox_cli, "_get_client", InterruptingClient)

    assert proxbox_cli.main(["version"]) == 130
