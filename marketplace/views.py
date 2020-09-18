import logging
import random
import string
from datetime import datetime, timedelta
from threading import Thread

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.utils.module_loading import import_by_path
from django.utils.translation import activate, ugettext as _
from django.views.generic import DetailView

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.core.constants import CONFIRMED
from ikwen.core.models import Application, Service
from ikwen.core.views import HybridListView, ChangeObjectBase
from ikwen.core.utils import set_counters, increment_history_field, get_service_instance, get_mail_content, send_push
from ikwen.billing.models import MoMoTransaction, MTN_MOMO

from daraja.models import Dara, DARAJA

from marketplace.admin import ProductAdmin
from marketplace.models import Product, Payment


logger = logging.getLogger('ikwen')


class ShowProductList(HybridListView):
    template_name = 'marketplace/show_product_list.html'
    queryset = Product.objects.select_related('app', 'provider').filter(is_active=True)


class ProductDetail(DetailView):
    template_name = 'marketplace/product_detail.html'
    model = Product

    def get_object(self, queryset=None):
        slug = self.kwargs.get('slug')
        try:
            return Product.objects.select_related('provider', 'app').get(slug=slug)
        except:
            raise Http404("No product found with slug '%s'" % slug)

    def get_context_data(self, **kwargs):
        context = super(ProductDetail, self).get_context_data(**kwargs)
        payment_id = kwargs.get('payment_id')
        if payment_id:
            context['payment'] = get_object_or_404(Payment, pk=payment_id, status=CONFIRMED)
        return context

    def render_to_response(self, context, **response_kwargs):
        product = context['product']
        if product.template_name:
            # Render with the defined in the Product object
            return render(self.request, product.template_name, context)
        return super(ProductDetail, self).render_to_response(context, **response_kwargs)


class ProductList(HybridListView):
    model = Product
    list_filter = ('app', 'provider', 'lang', )


class ChangeProduct(ChangeObjectBase):
    model = Product
    model_admin = ProductAdmin


def set_momo_payment(request, *args, **kwargs):
    service = get_service_instance()
    config = service.config
    product_id = request.POST['product_id']
    product = Product.objects.get(pk=product_id)
    payment = Payment.objects.create(member=request.user, product=product, method=Payment.MOBILE_MONEY,
                                     amount=product.cost)
    model_name = 'marketplace.Payment'
    mean = request.GET.get('mean', MTN_MOMO)
    signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for i in range(16)])
    MoMoTransaction.objects.using(WALLETS_DB_ALIAS).filter(object_id=product.id).delete()
    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS)\
        .create(service_id=service.id, type=MoMoTransaction.CASH_OUT, amount=product.cost, phone='N/A', model=model_name,
                object_id=payment.id, task_id=signature, wallet=mean, username=request.user.username, is_running=True)
    notification_url = service.url + reverse('marketplace:confirm_checkout', args=(tx.id, signature))
    cancel_url = service.url + reverse('marketplace:product_detail', args=(product.slug, ))
    return_url = service.url + reverse('marketplace:product_detail', args=(product.slug, payment.id, ))
    gateway_url = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_URL', 'http://payment.ikwen.com/v1')
    endpoint = gateway_url + '/request_payment'
    user_id = request.user.username if request.user.is_authenticated() else '<Anonymous>'
    params = {
        'username': getattr(settings, 'IKWEN_PAYMENT_GATEWAY_USERNAME', service.project_name_slug),
        'amount': product.cost,
        'merchant_name': config.company_name,
        'notification_url': notification_url,
        'return_url': return_url,
        'cancel_url': cancel_url,
        'user_id': user_id
    }
    try:
        r = requests.get(endpoint, params)
        resp = r.json()
        token = resp.get('token')
        if token:
            next_url = gateway_url + '/checkoutnow/' + resp['token'] + '?mean=' + mean
        else:
            logger.error("%s - Init payment flow failed with URL %s and message %s" % (service.project_name, r.url, resp['errors']))
            messages.error(request, resp['errors'])
            next_url = cancel_url
    except:
        logger.error("%s - Init payment flow failed with URL." % service.project_name, exc_info=True)
        next_url = cancel_url
    return HttpResponseRedirect(next_url)


def confirm_payment(request, *args, **kwargs):
    status = request.GET['status']
    message = request.GET['message']
    operator_tx_id = request.GET['operator_tx_id']
    phone = request.GET['phone']
    tx_id = kwargs['tx_id']
    try:
        tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS).get(pk=tx_id)
        if not getattr(settings, 'DEBUG', False):
            tx_timeout = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_TIMEOUT', 15) * 60
            expiry = tx.created_on + timedelta(seconds=tx_timeout)
            if datetime.now() > expiry:
                return HttpResponse("Transaction %s timed out." % tx_id)
    except:
        raise Http404("Transaction %s not found" % tx_id)

    callback_signature = kwargs.get('signature')
    no_check_signature = request.GET.get('ncs')
    if getattr(settings, 'DEBUG', False):
        if not no_check_signature:
            if callback_signature != tx.task_id:
                return HttpResponse('Invalid transaction signature')
    else:
        if callback_signature != tx.task_id:
            return HttpResponse('Invalid transaction signature')

    if status != MoMoTransaction.SUCCESS:
        return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))

    tx.status = status
    tx.message = message
    tx.processor_tx_id = operator_tx_id
    tx.phone = phone
    tx.is_running = False
    tx.save()
    mean = tx.wallet
    payment = Payment.objects.select_related('member', 'product').get(pk=tx.object_id)
    payment.status = CONFIRMED
    payment.processor_tx_id = operator_tx_id
    payment.save()

    product = payment.product
    provider = product.provider
    payer = payment.member
    provider_member = provider.member

    try:
        callback = import_by_path(product.callback)
        callback(product, payer)  # Callback should send notification email, push, etc.
    except:
        logger.error("", exc_info=True)

    marketplace_weblet = get_service_instance()
    config = marketplace_weblet.config

    if provider and provider.project_name_slug != 'ikwen':
        provider_earnings = tx.amount * (100 - product.ikwen_share_rate) / 100
        provider.raise_balance(provider_earnings, provider=mean)
        daraja = Application.objects.get(slug=DARAJA)
        dara_weblet = Service.objects.using(UMBRELLA).get(app=daraja, member=provider_member)
        dara_db = dara_weblet.database
        dara_weblet_self = Service.objects.using(dara_db).get(pk=dara_weblet.id)
        set_counters(dara_weblet_self)
        increment_history_field(dara_weblet_self, 'turnover_history', provider_earnings)
        increment_history_field(dara_weblet_self, 'earnings_history', provider_earnings)
        increment_history_field(dara_weblet_self, 'transaction_count_history')

        activate(provider_member.language)
        dashboard_url = 'https://daraja.ikwen.com' + reverse('daraja:dashboard')
        subject = _("New transaction on %s" % config.company_name)
        try:
            html_content = get_mail_content(subject, template_name='daraja/mails/new_transaction.html',
                                            extra_context={'currency_symbol': config.currency_symbol,
                                                           'amount': tx.amount,
                                                           'dara_earnings': provider_earnings,
                                                           'tx_date': tx.updated_on.strftime('%Y-%m-%d'),
                                                           'tx_time': tx.updated_on.strftime('%H:%M:%S'),
                                                           'account_balance': dara_weblet.balance,
                                                           'dashboard_url': dashboard_url})
            sender = 'ikwen Daraja <no-reply@ikwen.com>'
            msg = EmailMessage(subject, html_content, sender, [provider_member.email])
            msg.content_subtype = "html"
            if getattr(settings, 'UNIT_TESTING', False):
                msg.send()
            else:
                Thread(target=lambda m: m.send(), args=(msg,)).start()
        except:
            logger.error("Failed to notify %s Dara after follower purchase." % dara_weblet, exc_info=True)

        body = _("%(customer)s just purchased a %(product)s pack for %(currency)s %(amount)s. Please take a look "
                 "and deliver the best service." % {'customer': payer.full_name, 'product': product,
                                                    'currency': config.currency_code, 'amount': intcomma(tx.amount)})
        daraja_weblet = Service.objects.using(UMBRELLA).get(slug=DARAJA)
        send_push(daraja_weblet, provider_member, subject, body, dashboard_url)

    email = product.email
    if not email:
        email = product.provider.config.contact_email
    if not email:
        email = product.provider.member.email
    if email:
        subject = _("New payment of %s" % product.name)
        try:
            html_content = get_mail_content(subject, template_name='marketplace/mails/payment_notice.html',
                                            extra_context={'currency_symbol': config.currency_symbol,
                                                           'product': product,
                                                           'payer': payer,
                                                           'tx_date': tx.updated_on.strftime('%Y-%m-%d'),
                                                           'tx_time': tx.updated_on.strftime('%H:%M:%S')})
            sender = 'ikwen MarketPlace <no-reply@ikwen.com>'
            msg = EmailMessage(subject, html_content, sender, [provider_member.email])
            msg.content_subtype = "html"
            if getattr(settings, 'UNIT_TESTING', False):
                msg.send()
            else:
                Thread(target=lambda m: m.send(), args=(msg,)).start()
        except:
            logger.error("%s - Failed to send notice mail to %s." % (marketplace_weblet, email), exc_info=True)
    return HttpResponse("Notification successfully received")
