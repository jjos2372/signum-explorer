from django.views.generic import ListView

from java_wallet.models import Subscription
from scan.caching_paginator import CachingPaginator


class SubscriptionListView(ListView):
    model = Subscription
    queryset = Subscription.objects.using("java_wallet").all()
    template_name = "subscription/list.html"
    context_object_name = "subscriptions"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-height"

    def get_queryset(self):
        qs = self.queryset
        qs = qs.filter(latest=True)
        if "a" in self.request.GET:
            qs = qs.filter(sender_id=self.request.GET["a"], latest=True)
        return qs.order_by(self.ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context
