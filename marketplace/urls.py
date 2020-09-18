
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required

from marketplace.views import ShowProductList, ProductDetail, ProductList, ChangeProduct, set_momo_payment, \
    confirm_payment

urlpatterns = patterns(
    '',
    url(r'^laakam/products/$', permission_required('accesscontrol.sudo')(ProductList.as_view()), name='product_list'),
    url(r'^laakam/product$', permission_required('accesscontrol.sudo')(ChangeProduct.as_view()), name='change_product'),
    url(r'^laakam/product/(?P<object_id>[-\w]+)$', permission_required('accesscontrol.sudo')(ChangeProduct.as_view()), name='change_product'),

    url(r'^$', ShowProductList.as_view(), name='home'),

    url(r'^set_momo_payment$', set_momo_payment),
    url(r'^confirm_payment/(?P<tx_id>[-\w]+)/(?P<signature>[-\w]+)$', confirm_payment, name='confirm_payment'),

    url(r'^(?P<slug>[-\w]+)$', ProductDetail.as_view(), name='product_detail'),
    url(r'^(?P<slug>[-\w]+)/(?P<payment_id>[-\w]+)$', ProductDetail.as_view(), name='product_detail'),
)
