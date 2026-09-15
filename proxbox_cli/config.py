"""Configuration model and persistence for the Proxbox CLI."""

from __future__ import annotations

import json
import os
import secrets
import stat
import sys
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from proxbox_cli.errors import ConfigurationError

DEFAULT_CONFIG_DIR = "proxbox-cli"
DEFAULT_CONFIG_FILENAME = "config.json"
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 600.0
DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
BASE_URL_ENV_VAR = "PROXBOX_URL"
API_KEY_ENV_VAR = "PROXBOX_API_KEY"
TIMEOUT_ENV_VAR = "PROXBOX_CLI_TIMEOUT"
MAX_RESPONSE_BYTES_ENV_VAR = "PROXBOX_CLI_MAX_RESPONSE_BYTES"
ALLOW_INSECURE_TRANSPORT_ENV_VAR = "PROXBOX_CLI_ALLOW_INSECURE_TRANSPORT"
NETBOX_PATH_ENV_VAR = "NETBOX_PATH"
INSECURE_TRANSPORT_WARNING = (
    "Warning: PROXBOX_CLI_ALLOW_INSECURE_TRANSPORT=1 permits the configured "
    "API key to cross cleartext HTTP."
)

_NON_CREDENTIAL_ENV_FIELDS = (
    (TIMEOUT_ENV_VAR, "timeout"),
    (MAX_RESPONSE_BYTES_ENV_VAR, "max_response_bytes"),
)


class Config(BaseModel):
    """Config implementation."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = DEFAULT_BASE_URL
    api_key: str | None = None
    timeout: float = Field(
        default=DEFAULT_TIMEOUT,
        gt=0,
        le=MAX_TIMEOUT,
        allow_inf_nan=False,
    )
    max_response_bytes: int = Field(default=DEFAULT_MAX_RESPONSE_BYTES, gt=0)
    netbox_manage_py: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        """Require one credential-free HTTP(S) origin."""
        normalized = normalize_base_url(value)
        parsed = _split_base_url(normalized)
        if not _is_valid_origin(parsed, normalized):
            raise ValueError(
                "must be an http:// or https:// origin without credentials, "
                "a path, query, or fragment"
            )
        return _canonical_origin(parsed)

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str | None) -> str | None:
        """Treat an empty API key as absent without exposing its value."""
        if value is None:
            return None
        normalized = value.strip()
        if any(
            ord(character) < 32 or ord(character) == 127 for character in normalized
        ):
            raise ValueError("must not contain control characters")
        return normalized or None

    @model_validator(mode="after")
    def validate_key_transport(self) -> Config:
        """Keep configured credentials off remote cleartext transports."""
        if not self.api_key or self.base_url.startswith("https://"):
            return self
        if _is_loopback_host(str(urlsplit(self.base_url).hostname)):
            return self
        if os.environ.get(ALLOW_INSECURE_TRANSPORT_ENV_VAR) == "1":
            sys.stderr.write(f"{INSECURE_TRANSPORT_WARNING}\n")
            return self
        raise ValueError(
            "api_key requires https:// for non-loopback hosts; set "
            "PROXBOX_CLI_ALLOW_INSECURE_TRANSPORT=1 to opt in to cleartext HTTP"
        )


def config_dir() -> Path:
    """Handle config dir."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg).expanduser() if xdg else Path("~/.config").expanduser()
    return base / DEFAULT_CONFIG_DIR


def config_path() -> Path:
    """Handle config path."""
    return config_dir() / DEFAULT_CONFIG_FILENAME


def normalize_base_url(raw: str) -> str:
    """Strip trailing slashes; auto-prefix http:// if no scheme is present."""
    raw = raw.strip()
    if raw and "://" not in raw:
        raw = f"http://{raw}"
    separator = raw.find("://")
    return raw.rstrip("/") if len(raw) > separator + 3 else raw


def _split_base_url(value: str) -> SplitResult:
    """Parse a base URL and convert invalid ports into validation failures."""
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        return SplitResult("", "", "", "", "")
    return parsed


def _is_valid_origin(parsed: SplitResult, raw: str) -> bool:
    """Return whether a parsed URL is a safe backend origin."""
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and parsed.hostname.rstrip(".")
        and parsed.hostname != "*"
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
        and (parsed.port is None or 1 <= parsed.port <= 65535)
        and not any(character.isspace() for character in raw)
    )


def _canonical_origin(parsed: SplitResult) -> str:
    """Return a normalized origin after validation succeeds."""
    hostname = str(parsed.hostname).lower().rstrip(".")
    authority = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        authority = f"{authority}:{parsed.port}"
    return f"{parsed.scheme.lower()}://{authority}"


def _is_loopback_host(hostname: str) -> bool:
    """Return whether a hostname is an explicit loopback target."""
    hostname = hostname.lower().rstrip(".")
    if hostname == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _read_config_data(path: Path) -> dict[str, object]:
    """Read an existing JSON config object without falling open on errors."""
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        raise ConfigurationError(f"Malformed JSON in CLI config file: {path}") from None
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError):
        raise ConfigurationError(f"Could not read CLI config file: {path}") from None
    if not isinstance(data, dict):
        raise ConfigurationError(f"CLI config file must contain a JSON object: {path}")
    return data


def _read_existing_config() -> dict[str, object]:
    """Read the config file when present, including dangling symlinks."""
    path = config_path()
    try:
        return _read_config_data(path)
    except FileNotFoundError:
        if path.is_symlink():
            raise ConfigurationError(
                f"Could not read CLI config file: {path}"
            ) from None
        return {}


def _origin_identity(value: object) -> tuple[str, str, int] | None:
    """Return a comparable origin identity without resolving its hostname."""
    if not isinstance(value, str):
        return None
    normalized = normalize_base_url(value)
    parsed = _split_base_url(normalized)
    if not _is_valid_origin(parsed, normalized):
        return None
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    return (
        parsed.scheme.lower(),
        str(parsed.hostname).lower().rstrip("."),
        parsed.port or default_port,
    )


def same_origin(left: object, right: object) -> bool:
    """Return whether two valid backend values identify the same origin."""
    identity = _origin_identity(left)
    return identity is not None and identity == _origin_identity(right)


def _apply_environment(data: dict[str, object]) -> None:
    """Apply environment values without moving a file key to another origin."""
    file_origin = data.get("base_url", DEFAULT_BASE_URL)
    environment_origin = os.environ.get(BASE_URL_ENV_VAR)
    if environment_origin is not None:
        data["base_url"] = environment_origin
        if API_KEY_ENV_VAR not in os.environ and not same_origin(
            file_origin, environment_origin
        ):
            data["api_key"] = None
    if API_KEY_ENV_VAR in os.environ:
        data["api_key"] = os.environ[API_KEY_ENV_VAR]
    for environment_name, field_name in _NON_CREDENTIAL_ENV_FIELDS:
        if environment_name in os.environ:
            data[field_name] = os.environ[environment_name]


def config_validation_message(exc: ValidationError) -> str:
    """Return a concise validation error without echoing configured values."""
    first_error = exc.errors(include_input=False)[0]
    location = ".".join(str(part) for part in first_error["loc"]) or "transport"
    return f"Invalid CLI configuration for {location}: {first_error['msg']}"


def _validate_config(data: dict[str, object]) -> Config:
    """Validate configuration without exposing rejected input values."""
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(config_validation_message(exc)) from None


def load_file_config() -> Config:
    """Load only persisted values, without applying environment overrides."""
    return _validate_config(_read_existing_config())


def load_config() -> Config:
    """Load config with environment values overriding file values and defaults."""
    data = _read_existing_config()
    _apply_environment(data)
    return _validate_config(data)


def load_netbox_manage_py() -> str | None:
    """Read only the local management-command path from persisted config."""
    value = _read_existing_config().get("netbox_manage_py")
    if value is not None and not isinstance(value, str):
        raise ConfigurationError(
            "Invalid CLI configuration for netbox_manage_py: Input should be a string"
        )
    return value


def _temporary_config_name(filename: str) -> str:
    """Return an unpredictable same-directory temporary filename."""
    suffix = secrets.token_hex(16)
    return f".{filename}.{suffix}.tmp"


def _secure_config_directory(descriptor: int, directory: Path) -> None:
    """Require an owned directory descriptor and set its mode securely."""
    details = os.fstat(descriptor)
    if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid():
        raise ConfigurationError(
            f"CLI config directory is not owned by the current user: {directory}"
        )
    if stat.S_IMODE(details.st_mode) != 0o700:
        os.fchmod(descriptor, 0o700)
    if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o700:
        raise ConfigurationError(f"Could not secure CLI config directory: {directory}")


def _config_directory_error(directory: Path) -> ConfigurationError:
    """Return the stable config-directory access failure."""
    return ConfigurationError(f"Could not open CLI config directory: {directory}")


def _open_config_directory(directory: Path) -> int:
    """Create and open the config directory without following its final link."""
    descriptor: int | None = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open(directory, flags)
        _secure_config_directory(descriptor, directory)
        return descriptor
    except (OSError, ConfigurationError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        if isinstance(exc, ConfigurationError):
            raise
        raise _config_directory_error(directory) from None


def _validate_destination(descriptor: int, path: Path) -> None:
    """Refuse a symlink, directory, or special-file config destination."""
    try:
        details = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        raise ConfigurationError(f"Could not inspect CLI config file: {path}") from None
    if stat.S_ISLNK(details.st_mode):
        message = f"Refusing to write CLI config through symlink: {path}"
        raise ConfigurationError(message)
    if not stat.S_ISREG(details.st_mode):
        message = f"Refusing to replace non-file CLI config destination: {path}"
        raise ConfigurationError(message)


def _open_temporary_config(descriptor: int, name: str) -> int:
    """Create one new temporary config file relative to the directory."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    return os.open(name, flags, 0o600, dir_fd=descriptor)


def _write_config_descriptor(output_descriptor: int, payload: str) -> None:
    """Write and sync a temporary config descriptor, then close it."""
    try:
        os.fchmod(output_descriptor, 0o600)
    except BaseException:
        os.close(output_descriptor)
        raise
    with os.fdopen(output_descriptor, "w", encoding="utf-8") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def _write_temporary_config(descriptor: int, name: str, payload: str) -> None:
    """Create, write, and clean a temporary file on write failure."""
    output_descriptor = _open_temporary_config(descriptor, name)
    try:
        _write_config_descriptor(output_descriptor, payload)
    except BaseException:
        _cleanup_temporary(descriptor, name)
        raise


def _directory_is_pinned(descriptor: int, directory: Path) -> bool:
    """Return whether the path still identifies the opened directory."""
    try:
        current = os.stat(directory, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except OSError:
        return False
    return stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == (
        opened.st_dev,
        opened.st_ino,
    )


def _replace_config(
    descriptor: int, directory: Path, temporary: str, path: Path
) -> None:
    """Replace the destination relative to the still-pinned directory."""
    if not _directory_is_pinned(descriptor, directory):
        raise ConfigurationError(
            f"CLI config directory changed during write: {directory}"
        )
    _validate_destination(descriptor, path)
    os.rename(temporary, path.name, src_dir_fd=descriptor, dst_dir_fd=descriptor)
    os.fsync(descriptor)


def _cleanup_temporary(descriptor: int, temporary: str) -> None:
    """Best-effort remove an owned temporary file through the directory."""
    try:
        os.unlink(temporary, dir_fd=descriptor)
    except OSError:
        pass


def _close_config_write(descriptor: int, temporary: str, created: bool) -> None:
    """Clean the temporary file and always close the directory descriptor."""
    try:
        if created:
            _cleanup_temporary(descriptor, temporary)
    finally:
        os.close(descriptor)


def _atomic_write(directory: Path, path: Path, payload: str) -> None:
    """Write and replace one config file through a pinned directory descriptor."""
    descriptor = _open_config_directory(directory)
    temporary = _temporary_config_name(path.name)
    created = False
    try:
        _validate_destination(descriptor, path)
        _write_temporary_config(descriptor, temporary, payload)
        created = True
        _replace_config(descriptor, directory, temporary, path)
    except OSError:
        raise ConfigurationError(f"Could not write CLI config file: {path}") from None
    finally:
        _close_config_write(descriptor, temporary, created)


def save_config(cfg: Config) -> None:
    """Persist config with restricted permissions and an atomic replacement."""
    directory = config_dir()
    path = config_path()
    _atomic_write(directory, path, json.dumps(cfg.model_dump(), indent=2))
