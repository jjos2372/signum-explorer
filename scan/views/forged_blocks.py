from django.db.models import F, OuterRef, Q
from django.views.generic import ListView

from java_wallet.models import Block, RewardRecipAssign
from scan.caching_paginator import CachingPaginator
from scan.helpers.queries import get_timestamp_of_block


class ForgedBlocksListView(ListView):
    model = Block
    queryset = (
        Block.objects.using("java_wallet")
        .annotate(
            pool_id=RewardRecipAssign.objects.using("java_wallet")
            .filter(~Q(recip_id=F("account_id")))
            .filter(height__lte=OuterRef("height"))
            .filter(account_id=OuterRef("generator_id"))
            .order_by("-height")
            .values("recip_id")[:1]
        )
        .annotate(block=F("height"))
        .values("generator_id", "block", "pool_id")
        .exclude(height__isnull=True)
        .exclude(pool_id__isnull=True)
        .order_by("-block")
    )
    template_name = "forged_blocks/list.html"
    context_object_name = "forged_blocks"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-block"

    def get_queryset(self):
        qs = self.queryset
        if "a" in self.request.GET:
            qs = qs.filter(pool_id=self.request.GET["a"])
        return qs.order_by(self.ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        for forged_block in obj:
            forged_block["block_timestamp"] = get_timestamp_of_block(forged_block["block"])
        return context
