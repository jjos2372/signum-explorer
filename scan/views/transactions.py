import csv

from django.db.models.query_utils import Q
from django.http import Http404
from django.http.response import HttpResponse
from django.views.generic import ListView

from burst.libs.multiout import MultiOutPack
from java_wallet.models import IndirectIncoming, Transaction
from scan.caching_data.last_height import CachingLastHeight
from scan.caching_data.total_txs_count import CachingTotalTxsCount
from scan.caching_paginator import CachingPaginator
from scan.helpers.queries import get_account_name, get_unconfirmed_transactions
from scan.templatetags.burst_tags import burst_amount, num2rs, tx_load_recipients, tx_type
from scan.views.base import IntSlugDetailView
from scan.views.filters.transactions import TxFilter


def fill_data_transaction(obj, list_page=True):
    obj.sender_name = get_account_name(obj.sender_id)
    if obj.recipient_id:
        obj.recipient_name = get_account_name(obj.recipient_id)

    if obj.type == 0 and obj.subtype in {1, 2}:
        if obj.height == 0:
            # TODO: quick hack pending transaction
            return
        v, obj.multiout = MultiOutPack().unpack_header(obj.attachment_bytes)


class TxListView(ListView):
    model = Transaction
    queryset = Transaction.objects.using("java_wallet").all()
    template_name = "txs/list.html"
    context_object_name = "txs"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = ("-height", "-timestamp")
    filter_set = None

    def get_queryset(self):
        self.filter_set = TxFilter(self.request.GET, queryset=super().get_queryset())
        qs = self.filter_set.qs
        if not self.filter_set.data:
            qs = qs[:10000]

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        for t in obj:
            fill_data_transaction(t, list_page=True)

        # if no filtering get cached total count instead paginator.count in template
        if not self.filter_set.data:
            context["txs_cnt"] = CachingTotalTxsCount().cached_data

        return context


def tx_export_csv(request, id: int):
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{id}.csv"'},
    )
    writer = csv.writer(response)

    indirects_query = (
        IndirectIncoming.objects.using("java_wallet").values_list("transaction_id", flat=True).filter(account_id=id)
    )
    txs_indirects = Transaction.objects.using("java_wallet").filter(id__in=indirects_query)

    txs = (
        Transaction.objects.using("java_wallet")
        .filter(Q(sender_id=id) | Q(recipient_id=id))
        .union(txs_indirects)
        .order_by("-height")
    )[:2000]

    header = ["ID", "Height", "timestamp", "Type", "From", "To", "Amount", "Fee"]
    writer.writerow(header)

    id = int(id)
    id_rs = num2rs(id)
    for tx in txs:
        amount = tx.amount
        from_rs = id_rs if tx.sender_id == id else num2rs(tx.sender_id)
        to_rs = num2rs(tx.recipient_id) if tx.recipient_id else None
        if not tx.recipient_id:
            # multiout or something like that
            tx = tx_load_recipients(tx)
            if tx.recipients:
                for r in tx.recipients:
                    if r.id == id:
                        to_rs = id_rs
                        amount = r.amount
                        break

        writer.writerow(
            [
                tx.id,
                tx.height,
                tx.block_timestamp,
                tx_type(tx),
                from_rs,
                to_rs,
                burst_amount(amount),
                burst_amount(tx.fee),
            ]
        )

    return response


class TxDetailView(IntSlugDetailView):
    model = Transaction
    queryset = Transaction.objects.using("java_wallet").all()
    template_name = "txs/detail.html"
    context_object_name = "tx"
    slug_field = "id"
    slug_url_kwarg = "id"

    def get_object(self, queryset=None):
        try:
            obj = super().get_object(queryset)
        except Http404 as e:
            txs_pending = list(
                filter(
                    lambda x: x.get("transaction") == self.kwargs.get(self.slug_url_kwarg),
                    get_unconfirmed_transactions(),
                )
            )
            if not txs_pending:
                raise e

            tx = txs_pending[0]
            obj = Transaction(
                id=int(tx["transaction"]),
                deadline=tx["deadline"],
                sender_public_key=tx["senderPublicKey"].encode(),
                recipient_id=tx.get("recipient"),
                amount=tx["amountNQT"],
                fee=tx["feeNQT"],
                height=0,  # TODO why tx["height"] exists?
                block_id=0,
                signature=tx["signature"].encode(),
                timestamp=tx["timestamp"],
                type=tx["type"],
                subtype=tx["subtype"],
                sender_id=int(tx["sender"]),
                block_timestamp=tx["timestamp"],  # TODO
                full_hash=tx["fullHash"].encode(),
                referenced_transaction_fullhash=None,  # TODO
                attachment_bytes=tx["attachment_bytes"],
                version=tx["version"],
                has_message=False,
                has_encrypted_message=False,
                has_public_key_announcement=False,  # TODO
                ec_block_height=tx["ecBlockHeight"],
                ec_block_id=tx["ecBlockId"],
                has_encrypttoself_message=False,  # TODO
            )
            # obj.attachment = tx.get("attachment")
            obj.multiout = tx.get("multiout")

        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        obj.blocks_confirm = CachingLastHeight().cached_data - obj.height
        fill_data_transaction(obj, list_page=False)
        return context
