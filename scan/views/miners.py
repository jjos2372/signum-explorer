from django.db.models import F, Q
from django.views.generic import ListView

from java_wallet.models import RewardRecipAssign
from scan.caching_paginator import CachingPaginator
from scan.helpers.queries import get_timestamp_of_block


class MinerListView(ListView):
    model = RewardRecipAssign
    queryset = (
        RewardRecipAssign.objects.using("java_wallet")
        .filter(~Q(recip_id=F("account_id")))
        .filter(latest=1)
        .values("recip_id", "account_id", "height")
    )
    template_name = "miner/list.html"
    context_object_name = "miners"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-height"

    def get_queryset(self):
        qs = self.queryset
        qs = qs.filter(latest=True)
        if "a" in self.request.GET:
            qs = qs.filter(recip_id=self.request.GET["a"], latest=1)
        return qs.order_by(self.ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        for miner in obj:
            miner["block_timestamp"] = get_timestamp_of_block(miner["height"])
        return context
