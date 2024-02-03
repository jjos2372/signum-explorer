import sys
from datetime import datetime

from django.http import Http404
from django.views.generic import ListView

from config.settings import BLOCKED_ASSETS, FEATURED_ASSETS, PHISHING_ASSETS
from java_wallet.models import AccountAsset, Asset, AssetTransfer, Trade, Transaction
from scan.caching_paginator import CachingPaginator
from scan.helpers.queries import get_account_name, get_asset_details, get_asset_details_owner
from scan.templatetags.burst_tags import burst_amount, mul_decimals
from scan.views.base import IntSlugDetailView
from scan.views.filters.assets import AssetTransferFilter, TradeFilter


def fill_data_asset_transfer(transfer):
    try:
        transfer.name, transfer.decimals, transfer.total_quantity, mintable = get_asset_details(transfer.asset_id)
    except Exception:
        transfer.name, transfer.decimals, transfer.total_quantity = ["NOTKNOWN", 1, 0]
    transfer.sender_name = get_account_name(transfer.sender_id)
    transfer.recipient_name = get_account_name(transfer.recipient_id)


def fill_data_asset_trade(trade):
    trade.name, trade.decimals, trade.total_quantity, mintable = get_asset_details(trade.asset_id)
    trade.buyer_name = get_account_name(trade.buyer_id)
    trade.seller_name = get_account_name(trade.seller_id)


def fill_data_asset_distribution(distrib):
    distrib.sender_name = get_account_name(distrib.sender_id)


class AssetListView(ListView):
    model = Asset
    queryset = Asset.objects.using("java_wallet").all()
    template_name = "assets/list.html"
    context_object_name = "assets"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-height"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]

        context["BLOCKED_ASSETS"] = BLOCKED_ASSETS
        context["PHISHING_ASSETS"] = PHISHING_ASSETS

        for t in obj:
            t.account_name = get_account_name(t.account_id)
            check_name = t.name.upper()
            if check_name in BLOCKED_ASSETS or check_name in PHISHING_ASSETS:
                t.name = str(t.id)[0:10]

        featured_assets = []
        for fid in FEATURED_ASSETS:
            asset = Asset.objects.using("java_wallet").filter(id=fid).first()
            if asset:
                asset.account_name = get_account_name(asset.account_id)
                featured_assets.append(asset)
        context["featured_assets"] = featured_assets

        return context


class AssetTradesListView(ListView):
    model = Trade
    queryset = Trade.objects.using("java_wallet").all()
    template_name = "assets/trades.html"
    context_object_name = "assets_trades"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-height"
    filter_set = None

    def get_queryset(self):
        self.filter_set = TradeFilter(self.request.GET, queryset=super().get_queryset())
        if self.filter_set.is_valid() and self.filter_set.data:
            qs = self.filter_set.qs[:10000]
        else:
            raise Http404()

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assets_trades_cnt"] = self.filter_set.qs.count()
        obj = context[self.context_object_name]

        for trade in obj:
            fill_data_asset_trade(trade)

        return context


class AssetTransfersListView(ListView):
    model = AssetTransfer
    queryset = AssetTransfer.objects.using("java_wallet").all()
    template_name = "assets/transfers.html"
    context_object_name = "assets_transfers"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-height"
    filter_set = None

    def get_queryset(self):
        self.filter_set = AssetTransferFilter(self.request.GET, queryset=super().get_queryset())
        if self.filter_set.is_valid() and self.filter_set.data:
            qs = self.filter_set.qs[:10000]
        else:
            raise Http404()

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assets_transfers_cnt"] = self.filter_set.qs.count()
        obj = context[self.context_object_name]
        for transfer in obj:
            fill_data_asset_transfer(transfer)

        return context


class AssetHoldersListView(ListView):
    model = AccountAsset
    queryset = AccountAsset.objects.using("java_wallet").filter(latest=True)
    template_name = "assets/holders.html"
    context_object_name = "assets_holders"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-quantity"
    filter_set = None

    def get_queryset(self):
        self.filter_set = AssetTransferFilter(self.request.GET, queryset=super().get_queryset())
        if self.filter_set.is_valid() and self.filter_set.data:
            qs = self.filter_set.qs[:10000]
        else:
            raise Http404()

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assets_holders_cnt"] = self.filter_set.qs.count()
        obj = context[self.context_object_name]

        for asset in obj:
            asset.name, asset.decimals, asset.total_quantity, asset.mintable, asset.owner_id = get_asset_details_owner(
                asset.asset_id
            )
            asset.account_name = get_account_name(asset.account_id)

        return context


class AssetDetailView(IntSlugDetailView):
    model = Asset
    queryset = Asset.objects.using("java_wallet").all()
    template_name = "assets/detail.html"
    context_object_name = "asset"
    slug_field = "id"
    slug_url_kwarg = "id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = context[self.context_object_name]
        obj.account_name = get_account_name(obj.account_id)
        name, decimals, total_quantity, mintable = get_asset_details(obj.id)

        # assets transfer

        assets_transfers = (
            AssetTransfer.objects.using("java_wallet")
            .using("java_wallet")
            .filter(asset_id=obj.id)
            .order_by("-height")[:15]
        )

        for transfer in assets_transfers:
            fill_data_asset_transfer(transfer)

        context["assets_transfers"] = assets_transfers
        context["assets_transfers_cnt"] = AssetTransfer.objects.using("java_wallet").filter(asset_id=obj.id).count()

        # assets trades

        assets_trades = (
            Trade.objects.using("java_wallet").using("java_wallet").filter(asset_id=obj.id).order_by("-height")[:15]
        )

        for trade in assets_trades:
            fill_data_asset_trade(trade)

        context["assets_trades"] = assets_trades
        context["assets_trades_cnt"] = Trade.objects.using("java_wallet").filter(asset_id=obj.id).count()

        # asset minting
        mint_tx = Transaction.objects.using("java_wallet").filter(type=2, subtype=6).order_by("-height")
        assets_minting_cnt = 0
        asset_minting_tx = []
        for mints in mint_tx:
            asset_id = int.from_bytes(mints.attachment_bytes[1:9], byteorder=sys.byteorder)
            if asset_id == obj.id:
                assets_minting_cnt += 1
                asset_minting_tx.append(mints)
        context["assets_minting_cnt"] = assets_minting_cnt
        context["assets_minting_tx"] = asset_minting_tx

        # asset distributions
        assets_distribution_cnt = 0
        assets_distribution_tx = []
        distribution_tx = Transaction.objects.using("java_wallet").filter(type=2, subtype=8).order_by("-height")

        for distrib_tx in distribution_tx:
            fill_data_asset_distribution(distrib_tx)

        for distrib in distribution_tx:
            asset_id = int.from_bytes(distrib.attachment_bytes[1:9], byteorder=sys.byteorder)
            if asset_id == obj.id:
                assets_distribution_cnt += 1
                assets_distribution_tx.append(distrib)

        context["assets_distribution_cnt"] = assets_distribution_cnt
        context["assets_distribution_tx"] = assets_distribution_tx[:15]

        # asset holders
        assets_holders_cnt = AccountAsset.objects.using("java_wallet").filter(asset_id=obj.id, latest=True).count()
        assets_holders = (
            AccountAsset.objects.using("java_wallet").filter(asset_id=obj.id, latest=True).order_by("-quantity")[:15]
        )

        for asset in assets_holders:
            asset.name, asset.decimals, asset.total_quantity, asset.mintable, asset.owner_id = get_asset_details_owner(
                asset.asset_id
            )
            asset.account_name = get_account_name(asset.account_id)

        context["assets_holders"] = assets_holders
        context["assets_holders_cnt"] = assets_holders_cnt

        # price history

        price_query = (
            Trade.objects.using("java_wallet").using("java_wallet").filter(asset_id=obj.id).order_by("-height")[:2000]
        )

        price_history = "["
        old_time = None
        last_price = None
        now = datetime.now().strftime("%s")
        for trade in reversed(price_query):
            price = burst_amount(mul_decimals(trade.price, decimals))
            time = trade.timestamp.strftime("%s")
            last_price = price
            if time != old_time and time != now:
                # one per day
                price_history += "[" + time + "000," + str(price) + "],"
                old_time = time

        # add now as latest price
        if last_price:
            price_history += "[" + now + "000," + str(price) + "],"

        price_history += "]"

        context["price_history"] = price_history

        return context


class AssetMintingDetailView(ListView):
    model = Asset
    queryset = Asset.objects.using("java_wallet").all()
    template_name = "assets/mintings.html"
    context_object_name = "asset"
    slug_field = "id"
    slug_url_kwarg = "id"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-height"
    filter_set = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        focus = Asset.objects.using("java_wallet").filter(id=self.request.GET["asset"])
        for asset_focus in focus:
            obj = asset_focus
        name, decimals, total_quantity, mintable = get_asset_details(obj.id)
        # assets transfer

        assets_transfers = (
            AssetTransfer.objects.using("java_wallet")
            .using("java_wallet")
            .filter(asset_id=obj.id)
            .order_by("-height")[:15]
        )

        for transfer in assets_transfers:
            fill_data_asset_transfer(transfer)

        context["assets_transfers"] = assets_transfers
        context["assets_transfers_cnt"] = AssetTransfer.objects.using("java_wallet").filter(asset_id=obj.id).count()

        # assets trades

        assets_trades = (
            Trade.objects.using("java_wallet").using("java_wallet").filter(asset_id=obj.id).order_by("-height")[:15]
        )

        for trade in assets_trades:
            fill_data_asset_trade(trade)

        context["assets_trades"] = assets_trades
        context["assets_trades_cnt"] = Trade.objects.using("java_wallet").filter(asset_id=obj.id).count()

        # asset minting
        mint_tx = (
            Transaction.objects.using("java_wallet")
            .filter(type=2, subtype=6, sender_id=obj.account_id)
            .order_by("-height")
        )
        assets_minting_cnt = 0
        asset_minting_tx = []
        for mints in mint_tx:
            asset_id = int.from_bytes(mints.attachment_bytes[1:9], byteorder=sys.byteorder)
            if asset_id == obj.id:
                assets_minting_cnt += 1
                asset_minting_tx.append(mints)
        context["assets_minting_cnt"] = assets_minting_cnt
        context["assets_minting_tx"] = asset_minting_tx

        return context


class AssetDistributionDetailView(ListView):
    model = Asset
    queryset = Asset.objects.using("java_wallet").all()
    template_name = "assets/distributions.html"
    context_object_name = "asset"
    paginator_class = CachingPaginator
    paginate_by = 25
    ordering = "-height"
    filter_set = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        focus = Asset.objects.using("java_wallet").filter(id=self.request.GET["asset"])
        for asset_focus in focus:
            obj = asset_focus
        name, decimals, total_quantity, mintable = get_asset_details(obj.id)

        # asset distributions
        assets_distribution_cnt = 0
        assets_distribution_tx = []
        distribution_tx = Transaction.objects.using("java_wallet").filter(type=2, subtype=8).order_by("-height")

        for distrib_tx in distribution_tx:
            fill_data_asset_distribution(distrib_tx)

        for distrib in distribution_tx:
            asset_id = int.from_bytes(distrib.attachment_bytes[1:9], byteorder=sys.byteorder)
            if asset_id == obj.id:
                assets_distribution_cnt += 1
                assets_distribution_tx.append(distrib)

        context["assets_distribution_cnt"] = assets_distribution_cnt
        context["assets_distribution_tx"] = assets_distribution_tx

        return context
