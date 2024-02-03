import gzip

from django.views.generic import ListView

from java_wallet.models import At
from scan.caching_paginator import CachingPaginator
from scan.helpers.queries import get_account_name, get_ap_code, get_at_state
from scan.views.base import IntSlugDetailView


def fill_at_data(obj):
    obj.creator_name = get_account_name(obj.creator_id)
    if not obj.ap_code and obj.ap_code_hash_id:
        obj.ap_code = get_ap_code(obj.ap_code_hash_id)

    state, obj.activation = get_at_state(obj.id)
    # skip the internal state, balances, etc.
    obj.state = gzip.decompress(state)[106:]


class AtListView(ListView):
    model = At
    queryset = At.objects.using("java_wallet").filter(latest=True).all()
    template_name = "ats/list.html"
    context_object_name = "ats"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-height"

    def get_queryset(self):
        qs = self.queryset
        if "a" in self.request.GET:
            qs = qs.filter(creator_id=self.request.GET["a"])
        return qs.order_by(self.ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        for t in obj:
            fill_at_data(t)

        return context


class AtDetailView(IntSlugDetailView):
    model = At
    queryset = At.objects.using("java_wallet").filter(latest=True).all()
    template_name = "ats/detail.html"
    context_object_name = "at"
    slug_field = "id"
    slug_url_kwarg = "id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        fill_at_data(obj)

        return context
