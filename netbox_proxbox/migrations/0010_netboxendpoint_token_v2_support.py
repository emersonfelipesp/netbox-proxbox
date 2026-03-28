from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_proxbox', '0009_vmbackup'),
    ]

    operations = [
        migrations.AddField(
            model_name='netboxendpoint',
            name='token_key',
            field=models.CharField(
                blank=True,
                help_text='Key portion of a NetBox v2 API token.',
                max_length=255,
                verbose_name='Token Key',
            ),
        ),
        migrations.AddField(
            model_name='netboxendpoint',
            name='token_secret',
            field=models.CharField(
                blank=True,
                help_text='Secret portion of a NetBox v2 API token.',
                max_length=255,
                verbose_name='Token Secret',
            ),
        ),
        migrations.AddField(
            model_name='netboxendpoint',
            name='token_version',
            field=models.CharField(
                choices=[('v1', 'v1 Token'), ('v2', 'v2 Token')],
                default='v1',
                help_text='Choose whether to authenticate using a v1 token or a v2 token key/secret pair.',
                max_length=2,
                verbose_name='Token Version',
            ),
        ),
    ]
