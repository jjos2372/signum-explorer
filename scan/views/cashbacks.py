from django.views.generic import ListView

from burst.libs.multiout import MultiOutPack
from java_wallet.models import Transaction
from scan.caching_paginator import CachingPaginator
from scan.helpers.queries import get_account_name
from scan.views.ats import fill_at_data
from scan.views.base import IntSlugDetailView


def fill_data_transaction(obj, list_page=True):
    obj.sender_name = get_account_name(obj.sender_id)
    if obj.recipient_id:
        obj.recipient_name = get_account_name(obj.recipient_id)

    if obj.type == 0 and obj.subtype in {1, 2}:
        if obj.height == 0:
            # TODO: quick hack pending transaction
            return
        v, obj.multiout = MultiOutPack().unpack_header(obj.attachment_bytes)


class CBListView(ListView):
    model = Transaction
    queryset = Transaction.objects.using("java_wallet").all()
    template_name = "cbs/list.html"
    context_object_name = "cbs"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-height"

    def get_queryset(self):
        qs = self.queryset
        if "a" in self.request.GET:
            qs = qs.filter(cash_back_id=self.request.GET["a"])

        return qs.order_by(self.ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        for t in obj:
            fill_data_transaction(t)

        return context


class CBDetailView(IntSlugDetailView):
    model = Transaction
    queryset = Transaction.objects.using("java_wallet").all()
    template_name = "cbs/detail.html"
    context_object_name = "cb"
    slug_field = "id"
    slug_url_kwarg = "id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        fill_at_data(obj)

        return context
