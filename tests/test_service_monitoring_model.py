"""Isolated tests for ProxmoxEndpoint service-monitoring eligibility."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "netbox_proxbox" / "models" / "proxmox_endpoint.py"
SERIALIZER_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "serializers" / "endpoints.py"
FORM_PATH = REPO_ROOT / "netbox_proxbox" / "forms" / "proxmox.py"


def _stub_proxmox_endpoint_dependencies(monkeypatch):
    django = types.ModuleType("django")
    core = types.ModuleType("django.core")
    core_exceptions = types.ModuleType("django.core.exceptions")

    class _ValidationError(Exception):
        def __init__(self, message):
            super().__init__(message)
            self.message = message
            self.message_dict = (
                message if isinstance(message, dict) else {"__all__": [message]}
            )

    core_exceptions.ValidationError = _ValidationError

    core_validators = types.ModuleType("django.core.validators")
    core_validators.MaxValueValidator = lambda value: ("max", value)
    core_validators.MinValueValidator = lambda value: ("min", value)

    db = types.ModuleType("django.db")
    db_models = types.ModuleType("django.db.models")

    class _Field:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    for name in (
        "BooleanField",
        "CharField",
        "DateTimeField",
        "DecimalField",
        "ForeignKey",
        "JSONField",
        "ManyToManyField",
        "PositiveIntegerField",
        "PositiveSmallIntegerField",
        "TextField",
    ):
        setattr(db_models, name, _Field)
    db_models.PROTECT = object()
    db_models.SET_NULL = object()
    db_models.UniqueConstraint = _Field
    db.models = db_models

    urls = types.ModuleType("django.urls")
    urls.reverse = lambda *args, **kwargs: "/dummy/"

    utils = types.ModuleType("django.utils")
    utils_translation = types.ModuleType("django.utils.translation")
    utils_translation.gettext_lazy = lambda value: value
    utils.translation = utils_translation

    np_pkg = types.ModuleType("netbox_proxbox")
    np_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.ProxmoxAccessMethodChoices = types.SimpleNamespace(
        API="api",
        API_SSH="api_ssh",
    )
    choices.ProxmoxEndpointEnvironmentChoices = []
    choices.ProxmoxModeChoices = types.SimpleNamespace(
        PROXMOX_MODE_UNDEFINED="undefined"
    )
    choices.SyncModeChoices = types.SimpleNamespace(
        ALWAYS="always",
        DISABLED="disabled",
    )

    constants = types.ModuleType("netbox_proxbox.constants")
    constants.OVERWRITE_FIELDS = ()
    constants.SYNC_MODE_RESOURCE_TYPES = {"vm"}

    fields = types.ModuleType("netbox_proxbox.fields")
    fields.DomainField = _Field

    base = types.ModuleType("netbox_proxbox.models.base")
    base.PORT_VALIDATORS = []

    class _EndpointBase:
        class Meta:
            pass

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        @property
        def ip(self):
            return ""

        def clean(self):
            return None

    base.EndpointBase = _EndpointBase

    ssh_credential = types.ModuleType("netbox_proxbox.models.ssh_credential")
    ssh_credential.AUTH_METHOD_CHOICES = (("key", "Key"), ("password", "Password"))
    ssh_credential.AUTH_METHOD_KEY = "key"
    ssh_credential.AUTH_METHOD_PASSWORD = "password"
    ssh_credential.SSH_CRED_SOURCE_CHOICES = (
        ("dedicated", "Dedicated"),
        ("reuse_endpoint", "Reuse"),
    )
    ssh_credential.SSH_CRED_SOURCE_DEDICATED = "dedicated"
    ssh_credential.SSH_CRED_SOURCE_REUSE = "reuse_endpoint"
    ssh_credential.normalize_fingerprint = lambda value: value.strip()

    primary_secrets = types.ModuleType("netbox_proxbox.models.primary_secrets")
    primary_secrets.decrypt_primary_secret = lambda value: value or ""
    primary_secrets.encrypt_primary_secret = lambda value: value or ""

    enc_mod = types.ModuleType("netbox_proxbox.utils.encryption")
    enc_mod.encrypt = lambda value, key: f"enc:{value}"
    enc_mod.decrypt = lambda value, key: value.removeprefix("enc:")
    utils_pkg = types.ModuleType("netbox_proxbox.utils")
    utils_pkg.encryption = enc_mod

    for name, mod in [
        ("django", django),
        ("django.core", core),
        ("django.core.exceptions", core_exceptions),
        ("django.core.validators", core_validators),
        ("django.db", db),
        ("django.db.models", db_models),
        ("django.urls", urls),
        ("django.utils", utils),
        ("django.utils.translation", utils_translation),
        ("netbox_proxbox", np_pkg),
        ("netbox_proxbox.choices", choices),
        ("netbox_proxbox.constants", constants),
        ("netbox_proxbox.fields", fields),
        ("netbox_proxbox.models.base", base),
        ("netbox_proxbox.models.ssh_credential", ssh_credential),
        ("netbox_proxbox.models.primary_secrets", primary_secrets),
        ("netbox_proxbox.utils", utils_pkg),
        ("netbox_proxbox.utils.encryption", enc_mod),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


def _stub_netbox_rpc(monkeypatch, *, enabled: bool = True) -> None:
    rpc_pkg = types.ModuleType("netbox_rpc")
    rpc_pkg.__path__ = []
    rpc_models = types.ModuleType("netbox_rpc.models")

    class _RpcPluginSettings:
        @classmethod
        def get_solo(cls):
            return types.SimpleNamespace(enabled=enabled)

    rpc_models.RpcPluginSettings = _RpcPluginSettings
    monkeypatch.setitem(sys.modules, "netbox_rpc", rpc_pkg)
    monkeypatch.setitem(sys.modules, "netbox_rpc.models", rpc_models)


def _block_netbox_rpc(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "netbox_rpc.models", raising=False)
    monkeypatch.setitem(sys.modules, "netbox_rpc", None)


def _stub_saved_service_monitoring(
    module,
    monkeypatch,
    *,
    enabled: bool = True,
) -> None:
    class _ValuesList:
        def first(self):
            return enabled

    class _QuerySet:
        def values_list(self, *args, **kwargs):
            return _ValuesList()

    class _Manager:
        def filter(self, **kwargs):
            return _QuerySet()

    monkeypatch.setattr(
        module.ProxmoxEndpoint,
        "_default_manager",
        _Manager(),
        raising=False,
    )


def _load_proxmox_endpoint(monkeypatch):
    _stub_proxmox_endpoint_dependencies(monkeypatch)
    spec = importlib.util.spec_from_file_location(
        "_prox_endpoint_under_test", MODEL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stub_endpoint_serializer_dependencies(monkeypatch):
    django = types.ModuleType("django")
    django_utils = types.ModuleType("django.utils")
    django_translation = types.ModuleType("django.utils.translation")
    django_translation.gettext = lambda value: value
    django_utils.translation = django_translation

    class _Field:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _BaseSerializer:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def validate(self, attrs):
            return attrs

    rest_framework = types.ModuleType("rest_framework")
    serializers = types.ModuleType("rest_framework.serializers")
    for name in (
        "BooleanField",
        "CharField",
        "DateTimeField",
        "HyperlinkedIdentityField",
        "SerializerMethodField",
    ):
        setattr(serializers, name, _Field)

    class _ValidationError(Exception):
        pass

    serializers.ValidationError = _ValidationError
    rest_framework.serializers = serializers

    netbox_api_fields = types.ModuleType("netbox.api.fields")
    netbox_api_fields.ChoiceField = _Field
    netbox_api_serializers = types.ModuleType("netbox.api.serializers")
    netbox_api_serializers.NetBoxModelSerializer = _BaseSerializer
    netbox_api_serializers.WritableNestedSerializer = _BaseSerializer

    site_serializers = types.ModuleType("dcim.api.serializers_.sites")
    site_serializers.SiteSerializer = _Field
    ipam_serializers = types.ModuleType("ipam.api.serializers_.nested")
    ipam_serializers.NestedIPAddressSerializer = _Field
    tenant_serializers = types.ModuleType("tenancy.api.serializers_.tenants")
    tenant_serializers.TenantSerializer = _Field

    users_models = types.ModuleType("users.models")
    users_models.Token = type("Token", (), {})

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.NetBoxTokenVersionChoices = types.SimpleNamespace(V1="v1", V2="v2")
    choices.ProxmoxEndpointEnvironmentChoices = []
    choices.ProxmoxModeChoices = []

    constants = types.ModuleType("netbox_proxbox.constants")
    constants.OVERWRITE_FIELDS = ()
    constants.SYNC_MODE_FIELDS = ()

    class _Endpoint:
        def __init__(self, **kwargs):
            self.pk = kwargs.pop("pk", None)
            self.allow_writes = False
            self.access_methods = "api"
            self.service_monitoring_enabled = False
            self.rpc_enabled = True
            for key, value in kwargs.items():
                setattr(self, key, value)

        @property
        def tags(self):
            return ()

        @tags.setter
        def tags(self, value):
            raise TypeError("tags manager cannot be assigned directly")

        @property
        def service_monitoring_eligible(self):
            return False

        def _should_auto_disable_service_monitoring_for_rpc(self):
            return False

    models = types.ModuleType("netbox_proxbox.models")
    models.FastAPIEndpoint = type("FastAPIEndpoint", (), {})
    models.NetBoxEndpoint = type("NetBoxEndpoint", (), {})
    models.ProxmoxEndpoint = _Endpoint

    proxmox_endpoint = types.ModuleType("netbox_proxbox.models.proxmox_endpoint")
    proxmox_endpoint.SERVICE_MONITORING_INELIGIBLE_MESSAGE = "ineligible"

    np_pkg = types.ModuleType("netbox_proxbox")
    np_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    api_pkg = types.ModuleType("netbox_proxbox.api")
    api_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "api")]
    serializers_pkg = types.ModuleType("netbox_proxbox.api.serializers")
    serializers_pkg.__path__ = [
        str(REPO_ROOT / "netbox_proxbox" / "api" / "serializers")
    ]

    for name, mod in [
        ("django", django),
        ("django.utils", django_utils),
        ("django.utils.translation", django_translation),
        ("rest_framework", rest_framework),
        ("rest_framework.serializers", serializers),
        ("netbox.api.fields", netbox_api_fields),
        ("netbox.api.serializers", netbox_api_serializers),
        ("dcim.api.serializers_.sites", site_serializers),
        ("ipam.api.serializers_.nested", ipam_serializers),
        ("tenancy.api.serializers_.tenants", tenant_serializers),
        ("users.models", users_models),
        ("netbox_proxbox", np_pkg),
        ("netbox_proxbox.api", api_pkg),
        ("netbox_proxbox.api.serializers", serializers_pkg),
        ("netbox_proxbox.choices", choices),
        ("netbox_proxbox.constants", constants),
        ("netbox_proxbox.models", models),
        ("netbox_proxbox.models.proxmox_endpoint", proxmox_endpoint),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


def _load_endpoint_serializer(monkeypatch):
    _stub_endpoint_serializer_dependencies(monkeypatch)
    module_name = "netbox_proxbox.api.serializers.endpoints"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, SERIALIZER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _stub_proxmox_form_dependencies(monkeypatch):
    django = types.ModuleType("django")
    forms = types.ModuleType("django.forms")

    class _Field:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _BaseForm:
        def clean(self):
            return getattr(self, "cleaned_data", {})

        def add_error(self, field, error):
            self.errors.append((field, str(error)))

    for name in (
        "BooleanField",
        "CharField",
        "ChoiceField",
        "ModelMultipleChoiceField",
        "MultipleChoiceField",
        "NullBooleanField",
        "PasswordInput",
        "Textarea",
    ):
        setattr(forms, name, _Field)
    forms.Form = _BaseForm
    forms.NullBooleanSelect = _Field
    django.forms = forms

    django_utils = types.ModuleType("django.utils")
    django_translation = types.ModuleType("django.utils.translation")
    django_translation.gettext = lambda value: value
    django_utils.translation = django_translation

    netbox_forms = types.ModuleType("netbox.forms")
    netbox_forms.NetBoxModelFilterSetForm = _BaseForm
    netbox_forms.NetBoxModelForm = _BaseForm
    netbox_forms.NetBoxModelImportForm = _BaseForm

    utilities_fields = types.ModuleType("utilities.forms.fields")
    for name in (
        "CommentField",
        "CSVChoiceField",
        "CSVModelChoiceField",
        "DynamicModelChoiceField",
        "DynamicModelMultipleChoiceField",
    ):
        setattr(utilities_fields, name, _Field)
    utilities_rendering = types.ModuleType("utilities.forms.rendering")
    utilities_rendering.FieldSet = _Field

    class _Manager:
        def all(self):
            return []

    def _model_class(name):
        return type(name, (), {"objects": _Manager()})

    dcim_models = types.ModuleType("dcim.models")
    dcim_models.DeviceRole = _model_class("DeviceRole")
    dcim_models.Site = _model_class("Site")
    ipam_models = types.ModuleType("ipam.models")
    ipam_models.IPAddress = _model_class("IPAddress")
    tenancy_models = types.ModuleType("tenancy.models")
    tenancy_models.Tenant = _model_class("Tenant")

    constants = types.ModuleType("netbox_proxbox.constants")
    constants.OVERWRITE_FIELDS = ()
    constants.RPC_FIELDS = ("rpc_enabled",)
    constants.SYNC_MODE_FIELDS = ()

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.ProxmoxAccessMethodChoices = types.SimpleNamespace(
        API="api",
        API_SSH="api_ssh",
    )
    choices.ProxmoxEndpointEnvironmentChoices = []
    choices.ProxmoxModeChoices = []

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxEndpoint = type("ProxmoxEndpoint", (), {})

    class _Settings:
        @classmethod
        def get_solo(cls):
            return types.SimpleNamespace(encryption_key="")

    models.ProxboxPluginSettings = _Settings

    forms_settings = types.ModuleType("netbox_proxbox.forms.settings")
    forms_settings._parse_tenant_regex_rules = lambda value, allow_none: None
    forms_settings._sync_mode_choice_options = lambda include_inherit=False: []

    import_utils = types.ModuleType("netbox_proxbox.forms.import_utils")
    import_utils.validate_endpoint_import_headers = lambda *args, **kwargs: None

    ssh_credential = types.ModuleType("netbox_proxbox.models.ssh_credential")
    ssh_credential.AUTH_METHOD_KEY = "key"
    ssh_credential.AUTH_METHOD_PASSWORD = "password"
    ssh_credential.SSH_CRED_SOURCE_CHOICES = (
        ("dedicated", "Dedicated"),
        ("reuse_endpoint", "Reuse"),
    )
    ssh_credential.SSH_CRED_SOURCE_DEDICATED = "dedicated"
    ssh_credential.SSH_CRED_SOURCE_REUSE = "reuse_endpoint"

    np_pkg = types.ModuleType("netbox_proxbox")
    np_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    forms_pkg = types.ModuleType("netbox_proxbox.forms")
    forms_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "forms")]

    for name, mod in [
        ("django", django),
        ("django.forms", forms),
        ("django.utils", django_utils),
        ("django.utils.translation", django_translation),
        ("netbox.forms", netbox_forms),
        ("utilities.forms.fields", utilities_fields),
        ("utilities.forms.rendering", utilities_rendering),
        ("dcim.models", dcim_models),
        ("ipam.models", ipam_models),
        ("tenancy.models", tenancy_models),
        ("netbox_proxbox", np_pkg),
        ("netbox_proxbox.forms", forms_pkg),
        ("netbox_proxbox.constants", constants),
        ("netbox_proxbox.choices", choices),
        ("netbox_proxbox.models", models),
        ("netbox_proxbox.forms.settings", forms_settings),
        ("netbox_proxbox.forms.import_utils", import_utils),
        ("netbox_proxbox.models.ssh_credential", ssh_credential),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


def _load_proxmox_forms(monkeypatch):
    _stub_proxmox_form_dependencies(monkeypatch)
    module_name = "netbox_proxbox.forms.proxmox"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, FORM_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _eligible_endpoint(module):
    return module.ProxmoxEndpoint(
        allow_writes=True,
        access_methods="api_ssh",
        ssh_credential_source="dedicated",
        domain="pve.example.test",
        ssh_username="root",
        ssh_known_host_fingerprint="SHA256:" + "A" * 43,
        ssh_auth_method="key",
        ssh_private_key_enc="ciphertext",
        ssh_password_enc="",
        service_monitoring_enabled=True,
        rpc_enabled=True,
    )


def test_service_monitoring_eligible_requires_writes_ssh_and_credentials(monkeypatch):
    module = _load_proxmox_endpoint(monkeypatch)
    _stub_netbox_rpc(monkeypatch, enabled=True)
    endpoint = _eligible_endpoint(module)

    assert endpoint.service_monitoring_eligible is True

    endpoint.allow_writes = False
    assert endpoint.service_monitoring_eligible is False
    endpoint.allow_writes = True

    endpoint.access_methods = "api"
    assert endpoint.service_monitoring_eligible is False
    endpoint.access_methods = "api_ssh"

    endpoint.ssh_private_key_enc = ""
    assert endpoint.service_monitoring_eligible is False
    endpoint.ssh_private_key_enc = "ciphertext"

    # netbox-rpc must be effectively enabled: monitoring dispatches an RPC
    # execution each tick that the backend rejects with 403 while RPC is
    # disabled, so an RPC-disabled endpoint is never eligible.
    endpoint.rpc_enabled = False
    assert endpoint.service_monitoring_eligible is False
    endpoint.rpc_enabled = True
    assert endpoint.service_monitoring_eligible is True


def test_effective_rpc_enabled_tri_state_requires_netbox_rpc_install(monkeypatch):
    module = _load_proxmox_endpoint(monkeypatch)
    endpoint = _eligible_endpoint(module)

    _block_netbox_rpc(monkeypatch)
    endpoint.rpc_enabled = True
    assert endpoint.effective_rpc_enabled() is False
    assert endpoint.service_monitoring_eligible is False

    _stub_netbox_rpc(monkeypatch, enabled=False)
    assert endpoint.effective_rpc_enabled() is True
    endpoint.rpc_enabled = False
    assert endpoint.effective_rpc_enabled() is False
    endpoint.rpc_enabled = None
    assert endpoint.effective_rpc_enabled() is False

    _stub_netbox_rpc(monkeypatch, enabled=True)
    assert endpoint.effective_rpc_enabled() is True


def test_clean_rejects_enabled_service_monitoring_when_rpc_disabled(monkeypatch):
    module = _load_proxmox_endpoint(monkeypatch)
    _stub_netbox_rpc(monkeypatch, enabled=True)
    endpoint = _eligible_endpoint(module)
    endpoint.rpc_enabled = False

    ValidationError = sys.modules["django.core.exceptions"].ValidationError
    with pytest.raises(ValidationError) as exc:
        endpoint.clean()

    assert "__all__" in exc.value.message_dict
    assert "netbox-rpc" in exc.value.message_dict["__all__"]


def test_clean_auto_disables_existing_monitoring_when_rpc_disabled(
    monkeypatch,
    caplog,
):
    module = _load_proxmox_endpoint(monkeypatch)
    _stub_netbox_rpc(monkeypatch, enabled=True)
    _stub_saved_service_monitoring(module, monkeypatch, enabled=True)
    endpoint = _eligible_endpoint(module)
    endpoint.pk = 207
    endpoint.rpc_enabled = False

    with caplog.at_level("WARNING"):
        endpoint.clean()

    assert endpoint.service_monitoring_enabled is False
    assert "Auto-disabled service monitoring" in caplog.text


def test_clean_rejects_enabled_service_monitoring_when_ineligible(monkeypatch):
    module = _load_proxmox_endpoint(monkeypatch)
    _stub_netbox_rpc(monkeypatch, enabled=True)
    endpoint = _eligible_endpoint(module)
    endpoint.allow_writes = False

    ValidationError = sys.modules["django.core.exceptions"].ValidationError
    with pytest.raises(ValidationError) as exc:
        endpoint.clean()

    assert "__all__" in exc.value.message_dict
    assert "allow_writes" in exc.value.message_dict["__all__"]


def test_clean_accepts_enabled_service_monitoring_when_eligible(monkeypatch):
    module = _load_proxmox_endpoint(monkeypatch)
    _stub_netbox_rpc(monkeypatch, enabled=True)
    endpoint = _eligible_endpoint(module)

    endpoint.clean()
    assert endpoint.ssh_known_host_fingerprint.startswith("SHA256:")


def test_serializer_service_monitoring_validation_ignores_tags_patch_field(
    monkeypatch,
):
    module = _load_endpoint_serializer(monkeypatch)
    serializer = module.ProxmoxEndpointSerializer.__new__(
        module.ProxmoxEndpointSerializer
    )
    serializer.instance = module.ProxmoxEndpoint(service_monitoring_enabled=False)
    attrs = {"tags": ["proxbox"], "service_monitoring_interval_minutes": 10}

    serializer._validate_service_monitoring(attrs)

    assert attrs["tags"] == ["proxbox"]


def test_main_form_allows_existing_monitoring_rpc_only_auto_disable(
    monkeypatch,
    caplog,
):
    form_module = _load_proxmox_forms(monkeypatch)
    endpoint = types.SimpleNamespace(
        pk=207,
        service_monitoring_enabled=True,
        domain="pve.example.test",
        ip_address=None,
        ssh_private_key_enc="ciphertext",
        ssh_password_enc="",
        effective_rpc_enabled=lambda: False,
    )
    form = form_module.ProxmoxEndpointForm.__new__(form_module.ProxmoxEndpointForm)
    form.instance = endpoint
    form.errors = []
    form.cleaned_data = {
        "service_monitoring_enabled": True,
        "allow_writes": True,
        "access_methods": "api_ssh",
        "ssh_credential_source": "dedicated",
        "domain": "pve.example.test",
        "ip_address": None,
        "ssh_known_host_fingerprint": "SHA256:" + "A" * 43,
        "ssh_username": "root",
        "ssh_auth_method": "key",
        "ssh_password": "",
        "ssh_private_key": "",
        "clear_ssh_password": False,
        "clear_ssh_private_key": False,
    }

    form._clean_service_monitoring()

    assert form.errors == []

    model_module = _load_proxmox_endpoint(monkeypatch)
    _stub_netbox_rpc(monkeypatch, enabled=True)
    _stub_saved_service_monitoring(model_module, monkeypatch, enabled=True)
    model_endpoint = _eligible_endpoint(model_module)
    model_endpoint.pk = 207
    model_endpoint.rpc_enabled = False

    with caplog.at_level("WARNING"):
        model_endpoint.clean()

    assert model_endpoint.service_monitoring_enabled is False
    assert "Auto-disabled service monitoring" in caplog.text


def test_settings_form_path_relies_on_model_clean_for_rpc_only_auto_disable():
    source = FORM_PATH.read_text(encoding="utf-8")
    settings_form_source = source.split("class ProxmoxEndpointSettingsForm", 1)[
        1
    ].split("class ProxmoxEndpointSSHSettingsForm", 1)[0]

    assert "_clean_service_monitoring" not in settings_form_source
    assert "service_monitoring_enabled" not in settings_form_source
