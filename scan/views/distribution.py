from django.views.generic import ListView

from java_wallet.models import IndirectIncoming
from scan.caching_paginator import CachingPaginator
from scan.helpers.queries import get_account_name, get_details_by_tx, get_single_tx_class


def fill_data_indirect(obj, list_page=True):
    reciepent, sender, txtimestamp = get_details_by_tx(obj.transaction_id)
    obj.recipient_name = get_account_name(obj.account_id)
    obj.sender_id = sender
    obj.sender_name = get_account_name(obj.sender_id)
    obj.timestamp = txtimestamp
    obj.tx = get_single_tx_class(obj.transaction_id)


class DistributionListView(ListView):
    model = IndirectIncoming
    queryset = IndirectIncoming.objects.using("java_wallet").all().order_by("-amount", "-quantity")
    template_name = "distribution/list.html"
    context_object_name = "distribution"
    paginator_class = CachingPaginator
    paginate_by = 25
    # ordering = "-amount"

    def get_queryset(self):
        qs = self.queryset
        if "a" in self.request.GET:
            qs = qs.filter(transaction_id=self.request.GET["a"])
        # return qs.order_by(self.ordering)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        for t in obj:
            fill_data_indirect(t)
        return context
