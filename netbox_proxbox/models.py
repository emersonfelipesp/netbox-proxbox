from django.urls import reverse
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator 

from netbox.models import NetBoxModel

from .choices import ProxmoxModeChoices

class ProxmoxEndpoint(NetBoxModel):
    name = models.CharField(
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
        help_text=_('IP Address of the Proxmox Endpoint/Cluster. It will try using the DNS name provided in IP Address if it is not empty.'),
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
        default=True,
        verbose_name=_('Verify SSL'),
        help_text=_('Choose or not to verify SSL certificate of the Proxmox Endpoint'),
    )

    class Meta:
        verbose_name_plural: str = "Proxmox Endpoints"
        unique_together = ['name', 'ip_address']
        ordering = ('name',)
        
    def __str__(self):
        return f"{self.name} ({self.host})"
    
    def get_absolute_url(self):
        return reverse('plugins:netbox_proxbox:proxmoxendpoint', args=[self.pk])


class NetboxEndpoint(NetBoxModel):
    name = models.CharField(max_length=255)
    ip_address = models.ForeignKey(
        to='ipam.IPAddress',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name=_('IP Address'),
        null=True,
        help_text=_('IP Address of the Netbox. It will try using the DNS name provided in IP Address if it is not empty.'),
    )
    port = models.PositiveIntegerField(
        default=443,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        verbose_name=_('HTTP Port'),
    )
    token = models.CharField(max_length=255)
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name=_('Verify SSL'),
        help_text=_('Choose or not to verify SSL certificate of the Netbox Endpoint'),
    )

    class Meta:
        verbose_name_plural: str = 'Netbox Endpoints'
        unique_together = ['name', 'ip_address']
        
    def __str__(self):
        return f"{self.name} ({self.host})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:netboxendpoints", args=[self.pk])
        

class FastAPIEndpoint(NetBoxModel):
    name = models.CharField(max_length=255)
    ip_address = models.ForeignKey(
        to='ipam.IPAddress',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name=_('IP Address'),
        null=True,
        help_text=_('IP Address of the FastAPI. It will try using the DNS name provided in IP Address if it is not empty.'),
    )
    port = models.PositiveIntegerField(
        default=8800,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        verbose_name=_('HTTP Port'),
    )
    verify_ssl = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural: str = 'FastAPI Endpoints'
        unique_together = ['name', 'ip_address']
    
    def __str__(self):
        return f"{self.name} ({self.host})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:fastapiendpoints", args=[self.pk])
    