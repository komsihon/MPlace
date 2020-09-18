from django.db import models

from ikwen.core.constants import PENDING
from ikwen.core.models import Application, Service
from ikwen.billing.models import AbstractProduct, AbstractPayment
from ikwen.accesscontrol.models import Member

from conf.settings import LANGUAGES


class Product(AbstractProduct):
    app = models.ForeignKey(Application, blank=True, null=True)
    provider = models.ForeignKey(Service, blank=True, null=True)
    phone = models.CharField(max_length=60, blank=True, null=True,
                             help_text="Contact phone of support team")
    email = models.EmailField(blank=True, null=True,
                              help_text="Contact email of support team")
    ikwen_share_rate = models.FloatField(default=10)
    callback = models.CharField(max_length=255, blank=True,
                                help_text="Callback that is run after completion of payment of this product.")
    template_name = models.CharField(max_length=150, blank=True,
                                     help_text="Template of the detail page of the Product.")
    lang = models.CharField(max_length=30, choices=LANGUAGES, default='en')
    tags = models.CharField(max_length=255, db_index=True, blank=True, null=True,
                            help_text="Search tags")


class Payment(AbstractPayment):
    member = models.ForeignKey(Member)
    product = models.ForeignKey(Product)
    status = models.CharField(max_length=100, default=PENDING)
