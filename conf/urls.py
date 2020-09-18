from django.conf.urls import patterns, include, url

from ikwen.core.views import Offline, DashboardBase
from ikwen.flatpages.views import FlatPageView
from marketplace.views import ShowProductList

urlpatterns = patterns(
    '',
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^offline.html$', Offline.as_view(), name='offline'),
    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),
    url(r'^theming/', include('ikwen.theming.urls', namespace='theming')),
    url(r'^page/(?P<url>[-\w]+)/$', FlatPageView.as_view(), name='flatpage'),
    url(r'^echo/', include('echo.urls', namespace='echo')),
    url(r'^ikwen/cashout/', include('ikwen.cashout.urls', namespace='cashout')),
    url(r'^ikwen/', include('ikwen.core.urls', namespace='ikwen')),

    url(r'^gorilla/dashboard$', DashboardBase.as_view(), name='admin_home'),
    url(r'^gorilla/dashboard$', DashboardBase.as_view(), name='dashboard'),
    url(r'^$', ShowProductList.as_view(), name='home'),
    url(r'^', include('marketplace.urls', namespace='marketplace')),
)
