from django.views.generic import ListView

from java_wallet.models import Alias
from scan.caching_paginator import CachingPaginator


class AliasListView(ListView):
    model = Alias
    queryset = Alias.objects.using("java_wallet").all()
    template_name = "alias/list.html"
    context_object_name = "aliases"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "alias_name"

    def get_queryset(self):
        qs = self.queryset
        # Excluding the STLDs
        qs = qs.filter(latest=True).exclude(tld=None)
        if "a" in self.request.GET:
            qs = qs.filter(account_id=self.request.GET["a"], latest=True).exclude(tld=None)
        return qs.order_by(self.ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        return context
