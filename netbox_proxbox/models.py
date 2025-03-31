from django.urls import reverse
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator 

from netbox.models import NetBoxModel

from .fields import DomainField
from .choices import ProxmoxModeChoices, SyncTypeChoices, SyncStatusChoices

class ProxmoxEndpoint(NetBoxModel):
    name = models.CharField(
        default='Proxmox Endpoint',
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Name of the Proxmox Endpoint/Cluster. It will be filled automatically by API.'),
    )
    ip_address = models.ForeignKey(
        to='ipam.IPAddress',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name=_('IP Address'),
        null=True,
        blank=True,
        help_text=_('IP Address of the Proxmox Endpoint (Cluster). Fallback if domain name is not provided.'),
    )
    domain = DomainField(
        verbose_name=_('Domain'),
        help_text=_('Domain name of the Proxmox Endpoint (Cluster).'),
        blank=True,
        null=True,
    )
    port = models.PositiveIntegerField(
        default=8006,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        verbose_name=_('HTTP Port'),
    )
    mode = models.CharField(
        max_length=255,
        choices=ProxmoxModeChoices,
        default=ProxmoxModeChoices.PROXMOX_MODE_UNDEFINED,

    )
    version = models.CharField(max_length=20, blank=True, null=True)
    repoid = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        verbose_name=_('Repository ID'),
    )
    username = models.CharField(
        default='root@pam',
        max_length=255,
        verbose_name=_('Username'),
        help_text=_("Username must be in the format of 'user@realm'. Default is 'root@pam'.")
    )
    password = models.CharField(
        max_length=255,
        verbose_name=_('Password'),
        help_text=_('Password of the Proxmox Endpoint. It is not needed if you use Token.'),
        blank=True,
        null=True,
    )
    token_name = models.CharField(
        max_length=255,
        verbose_name=_('Token Name'),
    )
    token_value = models.CharField(
        max_length=255,
        verbose_name=_('Token Value'),
    )
    verify_ssl = models.BooleanField(
        default=False,
        verbose_name=_('Verify SSL'),
        help_text=_('Choose or not to verify SSL certificate of the Proxmox Endpoint'),
    )

    class Meta:
        verbose_name_plural: str = "Proxmox Endpoints"
        unique_together = ['name', 'ip_address', 'domain']
        ordering = ('name',)
        
    def __str__(self):
        return f"{self.name} ({self.ip_address})"
    
    def get_absolute_url(self):
        return reverse('plugins:netbox_proxbox:proxmoxendpoint', args=[self.pk])


class NetBoxEndpoint(NetBoxModel):
    name = models.CharField(
        default='NetBox Endpoint',
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Name of the NetBox Endpoint.'),
    )
    ip_address = models.ForeignKey(
        to='ipam.IPAddress',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name=_('IP Address'),
        null=True,
        blank=True,
        help_text=_('IP Address of the NetBox API. Fallback if domain name is not provided.'),
    )
    domain = DomainField(
        default='localhost',
        verbose_name=_('Domain'),
        help_text=_('Domain name of the NetBox API. Default is "localhost".'),
    )
    port = models.PositiveIntegerField(
        default=443,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        verbose_name=_('HTTP Port'),
    )
    token = models.ForeignKey(
        to='users.Token',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name=_('API Token'),
        null=True,
        blank=True,
        help_text=_('API Token for the NetBox API. Needed for Proxbox Backend Service to communicate with NetBox.'),
    )
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name=_('Verify SSL'),
        help_text=_('Choose or not to verify SSL certificate of the Netbox Endpoint'),
    )

    class Meta:
        verbose_name_plural: str = 'Netbox Endpoints'
        unique_together = ['name', 'ip_address']
        
    def __str__(self):
        return f"{self.name} ({self.ip_address})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:netboxendpoint", args=[self.pk])
        

class FastAPIEndpoint(NetBoxModel):
    name = models.CharField(
        default='ProxBox Endpoint',
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Name of the ProxBox Endpoint.'),
    )
    ip_address = models.ForeignKey(
        to='ipam.IPAddress',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name=_('IP Address'),
        null=True,
        blank=True,
        help_text=_('IP Address of the Proxbox API (Backend Service). Fallback if domain name is not provided.'),
    )
    domain = DomainField(
        default='localhost',
        verbose_name=_('Domain'),
        help_text=_('Domain name of the Proxbox API (Backend Service). Default is "localhost".'),
    )
    port = models.PositiveIntegerField(
        default=8800,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        verbose_name=_('HTTP Port'),
    )
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name=_('Verify SSL'),
        help_text=_('Choose or not to verify SSL certificate of the Proxbox Endpoint'),
    )
    token = models.CharField(
        blank=True,
        null=True,
        max_length=255,
        verbose_name=_('Token'),
        help_text=_('Token for the Proxbox Endpoint. If not provided, the Proxbox Endpoint will not be able to send messages to the client (user) browser.'),
    )
    use_websocket = models.BooleanField(
        default=False,
        verbose_name=_('Use WebSocket'),
        help_text=_('Choose or not to use WebSocket for the Proxbox Endpoint. If enabled, the Proxbox Endpoint will use WebSocket connection to send messages to the client (user) browser.'),
    )
    websocket_domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_('WebSocket Domain'),
        help_text=_('Domain name of the WebSocket for the Proxbox Endpoint'),
    )
    websocket_port = models.PositiveIntegerField(
        default=8800,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        verbose_name=_('WebSocket Port'),
        help_text=_('Port of the WebSocket for the Proxbox Endpoint (the same as HTTP port)'),
    )
    server_side_websocket = models.BooleanField(
        default=False,
        verbose_name=_('[BETA] Server Side WebSocket'),
        help_text=_('Choose or not to use server side WebSocket connection for the Proxbox Endpoint. This is experimental feature and may not work as expected. This way, client (user) browser will not be able to send messages to the Proxbox Endpoint.'),
    )

    class Meta:
        verbose_name_plural: str = 'FastAPI Endpoints'
        unique_together = ['name', 'ip_address']
    
    def __str__(self):
        return f"{self.name} ({self.domain})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:fastapiendpoint", args=[self.pk])


class SyncProcess(NetBoxModel):
    name = models.CharField(max_length=255, unique=True)
    sync_type = models.CharField(
        max_length=20,
        choices=SyncTypeChoices,
        default=SyncTypeChoices.ALL,
    )
    status = models.CharField(
        max_length=20,
        choices=SyncStatusChoices,
        default=SyncStatusChoices.NOT_STARTED,
    )  
    started_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text=_('When the sync process started. Format: YYYY-MM-DD HH:MM:SS')
    )
    completed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text=_('When the sync process completed. Format: YYYY-MM-DD HH:MM:SS')
    )
    runtime = models.FloatField(
        null=True,
        blank=True,
        help_text=_('Time elapsed for the sync process. Format: seconds')
    )

    def __str__(self):
        return f'{self.name} ({self.sync_type})'
    
    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:syncprocess", args=[self.pk])