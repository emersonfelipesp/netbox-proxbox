"""Choice sets for read-only Ceph inventory models."""

from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet


class CephHealthChoices(ChoiceSet):
    """Ceph cluster/check health states."""

    key = "Ceph.health"

    HEALTH_OK = "HEALTH_OK"
    HEALTH_WARN = "HEALTH_WARN"
    HEALTH_ERR = "HEALTH_ERR"
    HEALTH_UNKNOWN = "unknown"

    CHOICES = [
        (HEALTH_OK, _("OK"), "green"),
        (HEALTH_WARN, _("Warning"), "yellow"),
        (HEALTH_ERR, _("Error"), "red"),
        (HEALTH_UNKNOWN, _("Unknown"), "gray"),
    ]


class CephDaemonTypeChoices(ChoiceSet):
    """Ceph daemon families mirrored in v1."""

    key = "CephDaemon.daemon_type"

    TYPE_MON = "mon"
    TYPE_MGR = "mgr"
    TYPE_MDS = "mds"
    TYPE_OSD = "osd"
    TYPE_UNKNOWN = "unknown"

    CHOICES = [
        (TYPE_MON, _("Monitor"), "blue"),
        (TYPE_MGR, _("Manager"), "purple"),
        (TYPE_MDS, _("Metadata server"), "cyan"),
        (TYPE_OSD, _("OSD"), "orange"),
        (TYPE_UNKNOWN, _("Unknown"), "gray"),
    ]


class CephDaemonStateChoices(ChoiceSet):
    """Common daemon state labels across PVE/Ceph payloads."""

    key = "CephDaemon.state"

    STATE_UNKNOWN = "unknown"
    STATE_ACTIVE = "active"
    STATE_STANDBY = "standby"
    STATE_RUNNING = "running"
    STATE_STOPPED = "stopped"
    STATE_ERROR = "error"

    CHOICES = [
        (STATE_UNKNOWN, _("Unknown"), "gray"),
        (STATE_ACTIVE, _("Active"), "green"),
        (STATE_STANDBY, _("Standby"), "blue"),
        (STATE_RUNNING, _("Running"), "green"),
        (STATE_STOPPED, _("Stopped"), "gray"),
        (STATE_ERROR, _("Error"), "red"),
    ]
