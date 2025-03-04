from django.db import models
from django.core.exceptions import ValidationError
import re

def validate_domain(value):
    domain_regex = re.compile(
        r'^(?:[a-zA-Z0-9]'  # First character of the domain
        r'(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)'  # Sub domain + hostname
        r'+[a-zA-Z]{2,6}$'  # Top level domain
    )
    if not domain_regex.match(value):
        raise ValidationError(f'{value} is not a valid domain name')

class DomainField(models.CharField):
    default_validators = [validate_domain]

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 253  # Maximum length of a domain name is 253 characters
        super().__init__(*args, **kwargs)