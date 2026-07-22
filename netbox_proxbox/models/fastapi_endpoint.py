"""ProxBox FastAPI (proxbox-api) backend endpoint configuration."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, router, transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.fields import DomainField
from netbox_proxbox.models.base import PORT_VALIDATORS, EndpointBase
from netbox_proxbox.models.primary_secrets import (
    decrypt_primary_secret,
    encrypt_primary_secret,
)

_BACKEND_KEY_PERSISTED_FIELDS = frozenset(
    {
        "enabled",
        "domain",
        "ip_address_id",
        "port",
        "use_https",
        "verify_ssl",
        "use_websocket",
        "websocket_domain",
        "websocket_port",
        "server_side_websocket",
        "token_enc",
        "backend_key_target_fingerprint",
    }
)


@dataclass(frozen=True, slots=True)
class _EffectiveBackendKeyEndpoint:
    """Immutable next-state target used for one bounded authentication check."""

    pk: object | None
    enabled: bool
    domain: str | None
    ip_address: object | None
    port: int
    use_https: bool
    verify_ssl: bool
    use_websocket: bool
    websocket_domain: str | None
    websocket_port: int | None
    server_side_websocket: bool


class FastAPIEndpoint(EndpointBase):
    """HTTP/WebSocket reachability and optional auth for the ProxBox backend."""

    name = models.CharField(
        default="ProxBox Endpoint",
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Name of the ProxBox backend endpoint."),
    )
    ip_address = models.ForeignKey(
        to="ipam.IPAddress",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("IP address"),
        null=True,
        blank=True,
        help_text=_("Fallback backend address when no domain name is configured."),
    )
    domain = DomainField(
        blank=True,
        null=True,
        verbose_name=_("Domain"),
        help_text=_("Domain name of the ProxBox backend service."),
    )
    port = models.PositiveIntegerField(
        default=8800,
        validators=PORT_VALIDATORS,
        verbose_name=_("HTTP port"),
    )
    use_https = models.BooleanField(
        default=False,
        verbose_name=_("Use HTTPS"),
        help_text=_(
            "Use the HTTPS scheme to reach the ProxBox backend. "
            "Enable this when the backend is served over TLS, e.g. the "
            "proxbox-api '*-nginx' image. Certificate verification is "
            "controlled separately by 'Verify SSL'."
        ),
    )
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name=_("Verify SSL"),
        help_text=_(
            "Verify the TLS certificate presented by the ProxBox backend. "
            "Disable this when 'Use HTTPS' is enabled but the backend "
            "presents a self-signed certificate (e.g. the bundled mkcert "
            "cert in the proxbox-api '*-nginx' image)."
        ),
    )
    token_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted token"),
        help_text=_(
            "Fernet-encrypted backend token used by the ProxBox service. Internal."
        ),
    )
    backend_key_target_fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        editable=False,
        verbose_name=_("Adopted backend-key target fingerprint"),
        help_text=_(
            "Internal fingerprint binding the encrypted key to its reviewed "
            "backend authority and server WebSocket policy."
        ),
    )
    use_websocket = models.BooleanField(
        default=False,
        verbose_name=_("Use WebSocket"),
        help_text=_("Use WebSocket connectivity for browser updates."),
    )
    websocket_domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("WebSocket domain"),
        help_text=_("Domain name used for browser WebSocket connections."),
    )
    websocket_port = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        validators=PORT_VALIDATORS,
        verbose_name=_("WebSocket port"),
        help_text=_(
            "Port used for WebSocket connectivity. "
            "Leave blank to use the same port as the HTTP endpoint."
        ),
    )
    server_side_websocket = models.BooleanField(
        default=False,
        verbose_name=_("Server-side WebSocket"),
        help_text=_(
            "Use server-side WebSocket connectivity when supported by the backend."
        ),
    )

    class Meta(EndpointBase.Meta):
        verbose_name = _("FastAPI endpoint")
        verbose_name_plural = _("FastAPI endpoints")
        constraints = (
            models.UniqueConstraint(
                fields=("name", "ip_address"),
                name="netbox_proxbox_fastapiendpoint_identity",
            ),
        )

    @property
    def token(self) -> str:
        """Decrypt and return the proxbox-api backend token."""
        return decrypt_primary_secret(str(self.token_enc or ""))

    @token.setter
    def token(self, value: object | None) -> None:
        self._backend_key_token_explicitly_assigned = True
        self.token_enc = encrypt_primary_secret(value)

    @property
    def url(self) -> str:
        """Synthetic ``http(s)://`` base URL using domain or IP and the model port.

        Overrides :class:`CommonProperties.url` so the scheme is driven by
        ``use_https`` rather than ``verify_ssl`` (which only governs cert
        verification on the resulting connection).
        """
        from netbox_proxbox.utils import get_fastapi_url

        detail = get_fastapi_url(self) or {}
        if not isinstance(detail, dict):
            return ""
        return str(detail.get("http_url", ""))

    @property
    def websocket_url(self) -> str:
        """``ws(s)://`` URL for browser or server WebSocket clients."""
        from netbox_proxbox.utils import get_fastapi_url

        detail = get_fastapi_url(self) or {}
        if not isinstance(detail, dict):
            return ""
        return str(detail.get("websocket_url", ""))

    @classmethod
    def from_db(
        cls,
        db: str,
        field_names: list[str],
        values: list[object],
    ) -> FastAPIEndpoint:
        """Capture an optimistic-lock snapshot for the backend trust boundary."""
        instance = super().from_db(db, field_names, values)
        if _BACKEND_KEY_PERSISTED_FIELDS.issubset(instance.__dict__):
            instance._backend_key_loaded_signature = (
                instance._backend_key_persisted_signature()
            )
        return instance

    def refresh_from_db(self, *args: object, **kwargs: object) -> None:
        """Refresh the optimistic-lock snapshot alongside Django model fields."""
        super().refresh_from_db(*args, **kwargs)
        if _BACKEND_KEY_PERSISTED_FIELDS.issubset(self.__dict__):
            self._backend_key_loaded_signature = self._backend_key_persisted_signature()
            self.__dict__.pop("_backend_key_token_explicitly_assigned", None)

    def save(self, *args: object, **kwargs: object) -> None:
        """Persist only candidates authenticated by the shared fail-closed gate."""
        using_value = kwargs.get("using")
        using = (
            using_value
            if isinstance(using_value, str)
            else router.db_for_write(type(self), instance=self)
        )
        update_fields = self._normalize_update_fields(kwargs.get("update_fields"))
        if update_fields is not None:
            kwargs["update_fields"] = update_fields
        if (
            self.pk is not None
            and update_fields is not None
            and not self._updates_backend_key_state(update_fields)
        ):
            self._save_nonsecurity_only(*args, **kwargs)
            return

        saved = False
        try:
            with transaction.atomic(using=using):
                self.prepare_backend_key_transition(
                    update_fields=update_fields,
                    using=using,
                )
                if update_fields is not None:
                    kwargs["update_fields"] = frozenset(
                        {*update_fields, "backend_key_target_fingerprint"}
                    )
                super().save(*args, **kwargs)
                persisted = self._persisted_backend_key_state(using=using)
                if persisted is None:  # pragma: no cover - defensive ORM invariant
                    raise ValidationError(
                        {"token": "The saved backend endpoint could not be reloaded."}
                    )
                next_signature = persisted._backend_key_persisted_signature()
            saved = True
        finally:
            self.__dict__.pop("_backend_key_adoption_proof", None)
            self.__dict__.pop("_pending_backend_key", None)
            self.__dict__.pop("_backend_key_token_changed", None)

        if saved:
            self.__dict__.pop("_backend_key_token_explicitly_assigned", None)
            self._backend_key_loaded_signature = next_signature

    def _save_nonsecurity_only(
        self,
        *args: object,
        **kwargs: object,
    ) -> None:
        """Save explicitly nonsecurity fields without locks or backend traffic."""
        loaded_signature = getattr(self, "_backend_key_loaded_signature", None)
        explicitly_assigned = bool(
            getattr(self, "_backend_key_token_explicitly_assigned", False)
        )
        if loaded_signature is not None:
            loaded_ciphertext = str(loaded_signature[-1] or "")
            if explicitly_assigned:
                previous_token = decrypt_primary_secret(loaded_ciphertext).strip()
                candidate = (self.token or "").strip()
                if candidate != previous_token:
                    raise ValidationError(
                        {
                            "update_fields": (
                                "A replacement backend key cannot be supplied when "
                                "token_enc is excluded from update_fields."
                            )
                        }
                    )
                self.token_enc = loaded_ciphertext
            elif self.token_enc != loaded_ciphertext:
                raise ValidationError(
                    {
                        "token": (
                            "Assign backend keys through the token property; direct "
                            "encrypted-field changes are not accepted."
                        )
                    }
                )
        elif explicitly_assigned:
            raise ValidationError(
                {
                    "token": (
                        "Reload the complete backend endpoint before assigning a key."
                    )
                }
            )

        super().save(*args, **kwargs)
        if explicitly_assigned:
            self.__dict__.pop("_backend_key_token_explicitly_assigned", None)

    @staticmethod
    def _updates_backend_key_state(update_fields: frozenset[str]) -> bool:
        """Return whether a partial save includes a trust-boundary field."""
        return bool(update_fields & (_BACKEND_KEY_PERSISTED_FIELDS | {"ip_address"}))

    @staticmethod
    def _normalize_update_fields(value: object) -> frozenset[str] | None:
        """Return Django ``update_fields`` as a stable set without widening it."""
        if value is None:
            return None
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            raise ValidationError({"update_fields": "Expected an iterable of fields."})
        normalized = frozenset(str(item) for item in value)
        if "token" in normalized:
            raise ValidationError(
                {
                    "update_fields": (
                        "Use token_enc, not the virtual token property, in "
                        "update_fields."
                    )
                }
            )
        return normalized

    def _backend_connection_identity(self) -> tuple[object, ...]:
        """Return fields that bind a key proof to one backend trust boundary."""
        return (
            str(self.domain or "").strip().lower(),
            getattr(self, "ip_address_id", None),
            int(cast(int, self.port)),
            bool(self.use_https),
            bool(self.verify_ssl),
            bool(self.use_websocket),
            str(self.websocket_domain or "").strip().lower(),
            int(self.websocket_port) if self.websocket_port is not None else None,
            bool(self.server_side_websocket),
        )

    def _backend_key_persisted_signature(self) -> tuple[object, ...]:
        """Return ciphertext plus target state used for optimistic locking."""
        return (
            bool(self.enabled),
            *self._backend_connection_identity(),
            self.backend_key_target_fingerprint,
            self.token_enc,
        )

    def backend_key_ip_address_for_trust(self) -> object | None:
        """Read the current IPAddress value without trusting a cached FK object."""
        if self.ip_address_id is None:
            return None
        related_model = self._meta.get_field("ip_address").remote_field.model
        try:
            current = related_model.objects.only("address").get(pk=self.ip_address_id)
        except ObjectDoesNotExist:
            return None
        return current.address

    def _persisted_backend_key_state(
        self,
        *,
        using: str,
    ) -> FastAPIEndpoint | None:
        """Load the prior encrypted key and connection identity, if this row exists."""
        if self.pk is None:
            return None
        try:
            return (
                type(self)
                .objects.using(using)
                .select_for_update()
                .only(
                    "token_enc",
                    "enabled",
                    "domain",
                    "ip_address",
                    "port",
                    "use_https",
                    "verify_ssl",
                    "use_websocket",
                    "websocket_domain",
                    "websocket_port",
                    "server_side_websocket",
                    "backend_key_target_fingerprint",
                )
                .get(pk=self.pk)
            )
        except ObjectDoesNotExist:
            return None

    def prepare_backend_key_transition(
        self,
        candidate: object | None = None,
        *,
        update_fields: frozenset[str] | None = None,
        using: str | None = None,
    ) -> None:
        """Validate a prospective key/target transition before database persistence.

        Form, import, API, and direct-model paths converge here from :meth:`save`;
        a matching in-memory proof prevents any duplicate network attempt.
        """
        from netbox_proxbox.services.backend_key_adoption import (
            BackendKeyAdoptionError,
            adopt_rotated_backend_key,
            backend_key_proof_matches,
            backend_key_target_fingerprint,
            canonical_backend_authority,
            plan_backend_key_transition,
        )

        database = using or router.db_for_write(type(self), instance=self)
        previous = self._persisted_backend_key_state(using=database)
        loaded_signature = getattr(self, "_backend_key_loaded_signature", None)
        if previous is not None:
            if loaded_signature is None:
                raise ValidationError(
                    {
                        "token": (
                            "Reload the complete backend endpoint before saving it; "
                            "concurrency state is unavailable."
                        )
                    }
                )
            if previous._backend_key_persisted_signature() != loaded_signature:
                raise ValidationError(
                    {
                        "token": (
                            "This backend endpoint changed concurrently. Reload it "
                            "before adopting a key or changing its connection."
                        )
                    }
                )

        previous_token = (previous.token or "").strip() if previous else ""
        candidate_was_supplied = candidate is not None or bool(
            getattr(self, "_backend_key_token_explicitly_assigned", False)
        )
        explicit_candidate = (
            str(candidate).strip()
            if candidate is not None
            else (self.token or "").strip()
            if candidate_was_supplied
            else ""
        )
        if (
            previous is not None
            and not candidate_was_supplied
            and self.token_enc != cast(tuple[object, ...], loaded_signature)[-1]
        ):
            raise ValidationError(
                {
                    "token": (
                        "Assign backend keys through the token property; direct "
                        "encrypted-field changes are not accepted."
                    )
                }
            )

        token_field_selected = (
            previous is None or update_fields is None or "token_enc" in update_fields
        )
        if (
            previous is not None
            and candidate_was_supplied
            and explicit_candidate != previous_token
            and not token_field_selected
        ):
            raise ValidationError(
                {
                    "update_fields": (
                        "A replacement backend key cannot be supplied when token_enc "
                        "is excluded from update_fields."
                    )
                }
            )

        current_candidate = (
            explicit_candidate if candidate_was_supplied else previous_token
        )
        token_changed = current_candidate != previous_token
        self._backend_key_token_changed = token_changed

        effective = self._effective_backend_key_endpoint(previous, update_fields)
        if effective.server_side_websocket and not effective.use_websocket:
            raise ValidationError(
                {
                    "server_side_websocket": (
                        "Enable WebSocket before enabling the server-side "
                        "WebSocket client."
                    )
                }
            )
        if effective.websocket_domain:
            try:
                canonical_backend_authority(effective.websocket_domain)
            except BackendKeyAdoptionError as exc:
                raise ValidationError({"websocket_domain": exc.user_message}) from None
        if effective.websocket_port is not None and not (
            1 <= effective.websocket_port <= 65535
        ):
            raise ValidationError(
                {"websocket_port": "Configure a valid WebSocket port."}
            )

        persisted_target_drift = False
        if previous is not None:
            try:
                current_persisted_target = backend_key_target_fingerprint(previous)
            except BackendKeyAdoptionError:
                current_persisted_target = ""
            persisted_target_drift = (
                not previous.backend_key_target_fingerprint
                or previous.backend_key_target_fingerprint != current_persisted_target
            )
        connection_changed = (
            previous is not None
            and (
                (
                    str(effective.domain or "").strip().lower(),
                    getattr(effective.ip_address, "pk", None),
                    effective.port,
                    effective.use_https,
                    effective.verify_ssl,
                    effective.use_websocket,
                    str(effective.websocket_domain or "").strip().lower(),
                    effective.websocket_port,
                    effective.server_side_websocket,
                )
                != previous._backend_connection_identity()
            )
            or persisted_target_drift
        )

        transition = plan_backend_key_transition(
            exists=previous is not None,
            current_enabled=effective.enabled,
            previous_enabled=bool(getattr(previous, "enabled", False)),
            token_changed=token_changed,
            connection_changed=connection_changed,
        )
        if (
            previous is None
            and not effective.enabled
            and candidate_was_supplied
            and bool(explicit_candidate)
        ):
            raise ValidationError(
                {
                    "token": (
                        "Do not stage a backend key on a disabled new endpoint; "
                        "resubmit it explicitly when enabling the endpoint."
                    )
                }
            )
        if transition == "reject_disabled_change":
            raise ValidationError(
                {
                    "token": (
                        "Enable the backend endpoint and validate the replacement "
                        "key before changing its stored value."
                    )
                }
            )
        if transition == "no_remote_check":
            if previous is None:
                self.token_enc = ""
                self.backend_key_target_fingerprint = ""
                self.__dict__.pop("_backend_key_token_explicitly_assigned", None)
            else:
                self.token_enc = previous.token_enc
                self.backend_key_target_fingerprint = (
                    previous.backend_key_target_fingerprint
                )
            self._pending_backend_key = current_candidate
            return

        if not candidate_was_supplied or not explicit_candidate:
            raise ValidationError(
                {
                    "token": (
                        "Explicitly resubmit a non-empty backend API key when "
                        "creating or enabling an endpoint, or changing its target."
                    )
                }
            )

        proof = getattr(self, "_backend_key_adoption_proof", None)
        if not backend_key_proof_matches(proof, effective, current_candidate):
            try:
                proof = adopt_rotated_backend_key(
                    effective,
                    current_candidate,
                    bootstrap_if_needed=True,
                )
            except BackendKeyAdoptionError as exc:
                raise ValidationError({"token": exc.user_message}) from None
            self._backend_key_adoption_proof = proof

        if previous is not None and current_candidate == previous_token:
            self.token_enc = previous.token_enc
        elif token_field_selected:
            self.token_enc = encrypt_primary_secret(current_candidate)
        self.backend_key_target_fingerprint = proof.target_fingerprint
        self._pending_backend_key = current_candidate

    def _effective_backend_key_endpoint(
        self,
        previous: FastAPIEndpoint | None,
        update_fields: frozenset[str] | None,
    ) -> _EffectiveBackendKeyEndpoint:
        """Build next state from the locked row plus only selected partial fields."""

        def selected(field: str) -> bool:
            if previous is None or update_fields is None:
                return True
            if field == "ip_address":
                return field in update_fields or "ip_address_id" in update_fields
            return field in update_fields

        def value(field: str) -> object:
            source = self if selected(field) or previous is None else previous
            return getattr(source, field)

        domain_value = value("domain")
        return _EffectiveBackendKeyEndpoint(
            pk=self.pk,
            enabled=bool(value("enabled")),
            domain=str(domain_value) if domain_value else None,
            ip_address=value("ip_address"),
            port=int(str(value("port"))),
            use_https=bool(value("use_https")),
            verify_ssl=bool(value("verify_ssl")),
            use_websocket=bool(value("use_websocket")),
            websocket_domain=(
                str(value("websocket_domain")) if value("websocket_domain") else None
            ),
            websocket_port=(
                int(str(value("websocket_port")))
                if value("websocket_port") is not None
                else None
            ),
            server_side_websocket=bool(value("server_side_websocket")),
        )

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this FastAPI endpoint detail view."""
        return reverse("plugins:netbox_proxbox:fastapiendpoint", args=[self.pk])
