import gzip
import os
import struct
import sys
from ctypes import c_longlong, c_ulonglong
from datetime import datetime, timedelta
from math import ceil

from cache_memoize import cache_memoize
from django import template
from django.conf import settings

from burst.api.brs.v1.api import BrsApi
from burst.constants import MAX_BASE_TARGET, TxSubtypeBurstMining, TxSubtypeColoredCoins, TxSubtypePayment, TxType
from burst.libs.functions import calc_block_reward
from burst.libs.multiout import MultiOutPack
from burst.libs.reed_solomon import ReedSolomon
from burst.libs.transactions import get_message, get_message_sub, get_message_token
from config.settings import ADDRESS_PREFIX, BLOCKED_ASSETS, PHISHING_ASSETS
from java_wallet.fields import get_desc_tx_type
from java_wallet.models import Block, IndirectIncoming, IndirectRecipient, Transaction
from scan.caching_data.exchange import CachingExchangeData
from scan.caching_data.total_circulating import CachingTotalCirculating
from scan.helpers.queries import (
    get_account_balance,
    get_account_name,
    get_account_unconfirmed_balance,
    get_asset_details,
    get_asset_price,
    get_registered_tld_name,
    get_subscription_alias,
    get_subscription_recipient_id,
    get_tld_reciever_id,
    get_total_circulating,
    query_asset_fullhash,
    query_asset_treasury_acc,
)

register = template.Library()


@register.filter
def hours_ago(time, hours):
    return time + timedelta(hours=hours) > datetime.now()


@register.filter
def block_reward(block: Block) -> int:
    return calc_block_reward(block.height)


@register.filter
def block_reward_with_fee(block: Block) -> float:
    return (
        calc_block_reward(block.height)
        + (block.total_fee - block.total_fee_cash_back - block.total_fee_burnt) / 10**8
    )


@register.filter
def block_reward_with_fee_burnt(block: Block) -> float:
    return calc_block_reward(block.height) + (block.total_fee - block.total_fee_burnt) / 10**8


@register.filter
def block_fee_miner(block: Block) -> float:
    return block.total_fee - block.total_fee_cash_back - block.total_fee_burnt


@register.filter
def stld_name(tld_id):
    return get_registered_tld_name(tld_id)


@register.filter
def subscription_recipient_aliascheck(sub_id):
    return get_tld_reciever_id(sub_id)


@cache_memoize(240)
@register.filter
def subscription_attachment(sub_id):
    sub_recipient_id = get_subscription_recipient_id(sub_id)
    check = get_tld_reciever_id(sub_id)
    if sub_recipient_id != check:
        alias_name, alias_tld_id = get_subscription_alias(sub_id)
        tld_name = get_registered_tld_name(alias_tld_id)
        if tld_name == "signum":
            return "Quarterly Payment for Alias: " + alias_name
        else:
            return "Quarterly Payment for Alias: " + alias_name + "." + tld_name
    return ""


@cache_memoize(240)
@register.filter
def asset_circulating(asset_id: int) -> int:
    asset_details = BrsApi(settings.SIGNUM_NODE).get_asset(asset_id)
    return int(asset_details["quantityCirculatingQNT"])


@register.filter
def asset_owner(asset_id: int) -> int:
    asset_details = BrsApi(settings.SIGNUM_NODE).get_asset(asset_id)
    return int(asset_details["account"])


@register.filter
def asset_issuer(asset_id: int) -> int:
    asset_details = BrsApi(settings.SIGNUM_NODE).get_asset(asset_id)
    return int(asset_details["issuer"])


@register.filter
def burst_amount(value: int) -> float:
    if not value:
        value = int(0)
    return round(value / 100000000.0, 8)


@register.filter
def cashback_amount(value: int) -> float:
    return round(value / 400000000.0, 8)


@register.filter
def append_symbol(value: float) -> str:
    return value + " " + os.environ.get("COIN_SYMBOL")


@register.simple_tag()
def coin_symbol() -> str:
    return os.environ.get("COIN_SYMBOL")


@register.filter
def split(str, key):
    return str.split(key)


@register.filter
def env(key):
    return os.environ.get(key, None)


@cache_memoize(180)
def get_exchange_data():
    return CachingExchangeData().cached_data


@register.filter
def in_usd(value: float) -> float:
    data = get_exchange_data()
    return value * data.price_usd


@register.filter
def rounding(value: float, accuracy: int) -> float:
    return round(value, accuracy)


@register.filter
def bin2hex(value: bytes) -> str:
    if not value:
        return ""
    return value.hex().upper()


@register.filter
def blkatid(value: bytes) -> str:
    if not value:
        return ""
    lst = []
    s = value.hex().upper()
    for x in (s[k : k + 16] for k in range(0, len(s), 3 * 16)):
        i = struct.unpack("<Q", bytes.fromhex(x))[0]
        j = str(i)
        lst.append(j)
    return lst


@register.filter
def gzip2hex(value: bytes) -> str:
    if not value:
        return ""
    decompressed_byte_data = gzip.decompress(value)
    return decompressed_byte_data.hex().upper()


@register.filter
def tx_message(tx: Transaction) -> str:
    if not tx.has_message or not tx.attachment_bytes:
        return ""
    return get_message(tx.attachment_bytes)


@register.filter
def tx_message_sub(tx: Transaction) -> str:
    if not tx.has_message or not tx.attachment_bytes:
        return ""
    return get_message_sub(tx.attachment_bytes)


@register.filter
def tx_message_token(tx: Transaction) -> str:
    if not tx.has_message or not tx.attachment_bytes:
        return ""
    return get_message_token(tx.attachment_bytes)


@register.filter
def tx_type(tx: Transaction) -> str:
    return get_desc_tx_type(tx.type, tx.subtype)


@register.filter
def tx_is_in(tx: Transaction, account_id=None) -> bool:
    if account_id:
        account_id = int(account_id)
        if tx.sender_id == account_id:
            return False

        if tx.recipient_id == account_id and tx.amount > 0:
            return True

        if tx.type == TxType.PAYMENT and tx.subtype in [TxSubtypePayment.MULTI_OUT, TxSubtypePayment.MULTI_OUT_SAME]:
            tx = tx_load_recipients(tx)
            for r in tx.recipients:
                if r.id == account_id:
                    return True

        if tx.type == TxType.BURST_MINING and tx.subtype == TxSubtypeBurstMining.COMMITMENT_REMOVE:
            return True

        if tx.type == TxType.COLORED_COINS and tx.subtype == TxSubtypeColoredCoins.ASSET_TRANSFER:
            return True

        if tx.type == TxType.COLORED_COINS and tx.subtype == TxSubtypeColoredCoins.ASSET_TRANSFER_MULTI:
            return True

        if tx.type == TxType.COLORED_COINS and tx.subtype == TxSubtypeColoredCoins.DISTRIBUTE_TO_HOLDERS:
            return True

    return False


@register.filter
def tx_is_out(tx: Transaction, account_id: None) -> bool:
    if account_id and tx.sender_id == int(account_id):
        if tx.amount > 0:
            return True
        elif tx.type == TxType.BURST_MINING and tx.subtype == TxSubtypeBurstMining.COMMITMENT_ADD:
            return True
        if tx.type == TxType.COLORED_COINS and tx.subtype == TxSubtypeColoredCoins.ASSET_TRANSFER:
            return True
        if tx.type == TxType.COLORED_COINS and tx.subtype == TxSubtypeColoredCoins.ASSET_TRANSFER_MULTI:
            return True

    return False


def asset_offset(height: int) -> int:
    start_block = 0
    env_start_block = os.environ.get("DIGITAL_GOODS_STORE_BLOCK")
    if env_start_block:
        start_block = int(env_start_block)

    offset = 1
    if height > 0 and height < start_block:
        offset = 0

    return offset


@register.filter
def tx_amount(tx: Transaction, filtered_account=None) -> float:
    account_id = filtered_account
    if account_id and type(account_id) is str:
        account_id = int(account_id)
    if (
        account_id
        and tx.sender_id != account_id
        and tx.type == TxType.PAYMENT
        and tx.subtype in [TxSubtypePayment.MULTI_OUT, TxSubtypePayment.MULTI_OUT_SAME]
    ):
        tx = tx_load_recipients(tx)
        for r in tx.recipients:
            if r.id == account_id:
                return burst_amount(r.amount)

    elif (
        tx.attachment_bytes
        and tx.type == TxType.BURST_MINING
        and tx.subtype in [TxSubtypeBurstMining.COMMITMENT_ADD, TxSubtypeBurstMining.COMMITMENT_REMOVE]
    ):
        offset = asset_offset(tx.height)
        return burst_amount(int.from_bytes(tx.attachment_bytes[offset : offset + 8], byteorder=sys.byteorder))

    elif tx.attachment_bytes and tx.type == TxType.COLORED_COINS:
        offset = asset_offset(tx.height)
        if tx.subtype == TxSubtypeColoredCoins.ASSET_TRANSFER:
            return burst_amount(tx.amount)

        elif tx.subtype in [TxSubtypeColoredCoins.ASK_ORDER_PLACEMENT, TxSubtypeColoredCoins.BID_ORDER_PLACEMENT]:
            quantity = int.from_bytes(tx.attachment_bytes[offset + 8 : offset + 16], byteorder=sys.byteorder)
            price = int.from_bytes(tx.attachment_bytes[offset + 16 : offset + 24], byteorder=sys.byteorder)
            return burst_amount(quantity * price)

        elif tx.subtype == TxSubtypeColoredCoins.DISTRIBUTE_TO_HOLDERS and account_id:
            indirect = (
                IndirectIncoming.objects.using("java_wallet")
                .filter(account_id=account_id, transaction_id=tx.id)
                .order_by("-height")
                .first()
            )
            if indirect:
                return burst_amount(indirect.amount)

    return burst_amount(tx.amount)


@register.filter
def tx_quantity(tx: Transaction, filtered_account=None) -> float:
    account_id = filtered_account
    offset = asset_offset(tx.height)
    if account_id and type(account_id) is str:
        account_id = int(account_id)
    if account_id and tx.sender_id == account_id and tx.subtype == TxSubtypeColoredCoins.DISTRIBUTE_TO_HOLDERS:
        asset_id = int.from_bytes(tx.attachment_bytes[offset + 16 : offset + 24], byteorder=sys.byteorder)
        name, decimals, total_quantity, mintable = get_asset_details(asset_id)
        quantity = int.from_bytes(tx.attachment_bytes[offset + 24 : offset + 32], byteorder=sys.byteorder)
        return div_decimals(quantity, decimals)
    elif tx.subtype == TxSubtypeColoredCoins.DISTRIBUTE_TO_HOLDERS and account_id:
        asset_id = int.from_bytes(tx.attachment_bytes[offset + 16 : offset + 24], byteorder=sys.byteorder)
        name, decimals, total_quantity, mintable = get_asset_details(asset_id)
        indirect = (
            IndirectIncoming.objects.using("java_wallet")
            .filter(account_id=account_id, transaction_id=tx.id)
            .order_by("-height")
            .first()
        )
        if indirect and indirect.quantity:
            return div_decimals(indirect.quantity, decimals)
    elif tx.subtype == TxSubtypeColoredCoins.DISTRIBUTE_TO_HOLDERS and not account_id:
        # Only checking if a token gets distributed for the sender (no filter_account)
        # needs ony quantity
        asset_id = int.from_bytes(tx.attachment_bytes[offset + 16 : offset + 24], byteorder=sys.byteorder)
        if not asset_id:
            return 0
        else:
            quantity = int.from_bytes(tx.attachment_bytes[offset + 24 : offset + 32], byteorder=sys.byteorder)
            return div_decimals(quantity, decimals)
    elif tx.attachment_bytes and tx.type == TxType.COLORED_COINS:
        asset_id = int.from_bytes(tx.attachment_bytes[offset : offset + 8], byteorder=sys.byteorder)
        try:
            name, decimals, total_quantity, mintable = get_asset_details(asset_id)
        except Exception:
            decimals = 1
        quantity = int.from_bytes(tx.attachment_bytes[offset + 8 : offset + 16], byteorder=sys.byteorder)
        return div_decimals(quantity, decimals)
    else:
        return 0.0
    return 0.0


@register.filter
def tx_quantity_multi(tx: Transaction, asset_number=0) -> float:
    asset_offset = [2, 18, 34, 50]
    qunatity_offset = [10, 26, 42, 58]
    asset_id_offset = asset_offset[asset_number - 1]
    asset_quantity_offset = qunatity_offset[asset_number - 1]
    asset_id_offset2 = asset_id_offset + 8
    asset_quantity_offset2 = asset_quantity_offset + 8
    if tx.attachment_bytes and tx.type == TxType.COLORED_COINS:
        asset_id = int.from_bytes(tx.attachment_bytes[asset_id_offset:asset_id_offset2], byteorder=sys.byteorder)
        name, decimals, total_quantity, mintable = get_asset_details(asset_id)
        quantity = int.from_bytes(
            tx.attachment_bytes[asset_quantity_offset:asset_quantity_offset2], byteorder=sys.byteorder
        )
        return div_decimals(quantity, decimals)
    else:
        return 0.0


@register.filter
def tx_asset_multi_size(tx: Transaction) -> float:
    offset = asset_offset(tx.height)
    if tx.attachment_bytes and tx.type == TxType.COLORED_COINS:
        asset_size = int.from_bytes(tx.attachment_bytes[offset : offset + 1], byteorder=sys.byteorder)
        return asset_size
    else:
        return 0.0


@register.filter
def tx_symbol(tx: Transaction) -> str:
    if tx.type == TxType.COLORED_COINS and tx.attachment_bytes:
        offset = asset_offset(tx.height)
        if tx.subtype in (
            [
                TxSubtypeColoredCoins.ASSET_TRANSFER,
                TxSubtypeColoredCoins.ASSET_MINT,
                TxSubtypeColoredCoins.ASK_ORDER_PLACEMENT,
                TxSubtypeColoredCoins.BID_ORDER_PLACEMENT,
            ]
        ):
            asset_id = int.from_bytes(tx.attachment_bytes[offset : offset + 8], byteorder=sys.byteorder)
            try:
                name, decimals, total_quantity, mintable = get_asset_details(asset_id)
            except Exception:
                name = "NOTKNOWN"
            check_name = name.upper()
            if check_name in BLOCKED_ASSETS or check_name in PHISHING_ASSETS:
                return str(asset_id)[0:10]
            return name

    return coin_symbol()


@register.filter
def tx_symbol_multi(tx: Transaction, asset_number=1) -> str:
    asset_offset = [2, 18, 34, 50]
    asset_id_offset = asset_offset[asset_number - 1]
    asset_id_offset2 = asset_id_offset + 8
    if tx.type == TxType.COLORED_COINS and tx.attachment_bytes:
        asset_id = int.from_bytes(tx.attachment_bytes[asset_id_offset:asset_id_offset2], byteorder=sys.byteorder)
        name, decimals, total_quantity, mintable = get_asset_details(asset_id)
        check_name = name.upper()
        if check_name in BLOCKED_ASSETS or check_name in PHISHING_ASSETS:
            return str(asset_id)[0:10]
        return name


@register.filter
def tx_assetid_multi(tx: Transaction, asset_number=1) -> str:
    asset_offset = [2, 18, 34, 50]
    asset_id_offset = asset_offset[asset_number - 1]
    asset_id_offset2 = asset_id_offset + 8
    if tx.type == TxType.COLORED_COINS and tx.attachment_bytes:
        asset_id = int.from_bytes(tx.attachment_bytes[asset_id_offset:asset_id_offset2], byteorder=sys.byteorder)
        return asset_id


@register.filter
def tx_symbol_distribution(tx: Transaction) -> str:
    if tx.type == TxType.COLORED_COINS and tx.attachment_bytes:
        offset = asset_offset(tx.height)
        if tx.subtype == TxSubtypeColoredCoins.DISTRIBUTE_TO_HOLDERS:
            asset_id = int.from_bytes(tx.attachment_bytes[offset + 16 : offset + 24], byteorder=sys.byteorder)
            name, decimals, total_quantity, mintable = get_asset_details(asset_id)
            check_name = name.upper()
            if check_name in BLOCKED_ASSETS or check_name in PHISHING_ASSETS:
                return str(asset_id)[0:10]
            return name
        elif tx.subtype == TxSubtypeColoredCoins.ASSET_MINT:
            asset_id = int.from_bytes(tx.attachment_bytes[offset + 16 : offset + 24], byteorder=sys.byteorder)
            name, decimals, total_quantity, mintable = get_asset_details(asset_id)
            check_name = name.upper()
            if check_name in BLOCKED_ASSETS or check_name in PHISHING_ASSETS:
                return str(asset_id)[0:10]
            return name
    return ""


@register.filter
def tx_asset_holder(tx: Transaction) -> str:
    if tx.type == TxType.COLORED_COINS and tx.attachment_bytes:
        offset = asset_offset(tx.height)
        if tx.subtype == TxSubtypeColoredCoins.DISTRIBUTE_TO_HOLDERS:
            asset_id = int.from_bytes(tx.attachment_bytes[offset : offset + 8], byteorder=sys.byteorder)
            name, decimals, total_quantity, mintable = get_asset_details(asset_id)
            check_name = name.upper()
            if check_name in BLOCKED_ASSETS or check_name in PHISHING_ASSETS:
                return str(asset_id)[0:10]
            return name

    return ""


@register.filter
def tx_asset_id(tx: Transaction) -> int:
    if tx.type == TxType.COLORED_COINS and tx.attachment_bytes:
        offset = asset_offset(tx.height)
        if tx.subtype in (
            [
                TxSubtypeColoredCoins.ASSET_TRANSFER,
                TxSubtypeColoredCoins.ASK_ORDER_PLACEMENT,
                TxSubtypeColoredCoins.BID_ORDER_PLACEMENT,
                TxSubtypeColoredCoins.ASSET_MINT,
            ]
        ):
            asset_id = int.from_bytes(tx.attachment_bytes[offset : offset + 8], byteorder=sys.byteorder)
            return asset_id

    return 0


@register.filter
def total_circulating(account_id: int) -> float:
    return get_total_circulating() - get_account_balance(0)


@register.filter
def total_circulating_network(account_id: int) -> float:
    return CachingTotalCirculating().cached_data - get_account_balance(0)


@cache_memoize(23)
@register.filter
def account_balance(account_id: int) -> float:
    return get_account_balance(account_id)


@cache_memoize(23)
@register.filter
def account_unconfirmed_balance(account_id: int) -> float:
    return get_account_unconfirmed_balance(account_id)


@cache_memoize(23)
@register.filter
def account_locked_balance(account_id: int) -> float:
    return get_account_balance(account_id) - get_account_unconfirmed_balance(account_id)


@cache_memoize(240)
@register.filter
def account_name_string(account_id: int) -> float:
    account_name = get_account_name(account_id)
    return account_name if account_name else ""


@register.filter
def asset_price(asset_id: int) -> float:
    return get_asset_price(asset_id)


@register.filter
def is_asset_blocked(asset) -> bool:
    return asset.name.upper() in BLOCKED_ASSETS


@register.filter
def is_asset_phishing(asset) -> bool:
    return asset.name.upper() in PHISHING_ASSETS or asset.name.upper() in BLOCKED_ASSETS


@register.filter
def is_asset_treasury(asset, account_id) -> bool:
    if not account_id:
        return False
    # use fullhash from asset
    fullh = query_asset_fullhash(asset)
    resultt = query_asset_treasury_acc(asset, c_longlong(account_id).value)
    for i in resultt:
        if fullh == i:
            return True
    resultt = query_asset_treasury_acc(asset, c_ulonglong(account_id).value)
    for i in resultt:
        if fullh == i:
            return True
    return False


def group_list(lst: list or tuple, n: int):
    for i in range(0, len(lst), n):
        val = lst[i : i + n]
        if len(val) == n:
            yield tuple(val)


@register.filter
def tx_load_recipients(tx: Transaction) -> Transaction:
    if not tx.recipients and tx.attachment_bytes:
        if tx.type == TxType.PAYMENT and tx.subtype == TxSubtypePayment.MULTI_OUT:
            data = MultiOutPack().unpack_multi_out(tx.attachment_bytes)
            recipients = []
            for r, a in group_list(data, 2):
                recipient = IndirectRecipient()
                recipient.amount = a
                recipient.id = r
                recipients.append(recipient)
            tx.recipients = recipients
        elif tx.type == TxType.PAYMENT and tx.subtype == TxSubtypePayment.MULTI_OUT_SAME:
            data = MultiOutPack().unpack_multi_out_same(tx.attachment_bytes)
            recipients = []
            for r in data:
                recipient = IndirectRecipient()
                recipient.amount = tx.amount / len(data)
                recipient.id = r
                recipients.append(recipient)

            tx.recipients = recipients
    return tx


@register.filter
def num2rs(value: str or int) -> str:
    return ADDRESS_PREFIX + ReedSolomon().encode(str(value))


@register.filter
def sub_next_send(value):
    stamp = 1407722400 + value
    next_send = datetime.fromtimestamp(stamp)
    return next_send


@register.simple_tag()
def block_generation_time(block: Block) -> timedelta:
    if block.previous_block:
        return block.timestamp - block.previous_block.timestamp
    else:
        # first block
        return timedelta(0)


@register.filter
def to_int(value):
    return int(value)


@register.filter
def sub(a: int or float, b: int or float) -> int or float:
    return a - b


@register.filter
def div(a: int or float, b: int or float) -> float:
    return a / b if b else 0


@register.filter
def mul(a: int or float, b: int or float) -> int or float:
    return a * b


@register.filter
def div_decimals(a: int or float, b: int) -> float:
    if b == 0:
        return a
    return a / 10**b


@register.filter
def mul_decimals(a: int or float, b: int) -> float:
    if b == 0:
        return a
    return a * 10**b


@register.filter
def percent(value: int or float, total: int or float) -> int or float:
    return value / total * 100


@register.filter
def net_capacity_tib(base_target: int) -> float:
    if base_target < 100000000000:
        return MAX_BASE_TARGET / (base_target)
    s = struct.pack(">l", base_target & 0xFFFFFFFF)
    base_target_capacity = struct.unpack(">f", s)[0]
    return MAX_BASE_TARGET / (1.83 * base_target_capacity)


@register.filter
def base_target_capacity(base_target: int) -> int:
    if base_target < 100000000000:
        return int(MAX_BASE_TARGET / (base_target))
    s = struct.pack(">l", base_target & 0xFFFFFFFF)
    return int(struct.unpack(">f", s)[0])


@register.filter
def format_capacity(capacity: float) -> str:
    unit = "TiB"
    if capacity > 10000:
        capacity = capacity / 1024
        unit = "PiB"
    return "{:.1f}".format(capacity) + " " + unit


@register.filter
def net_commitment(base_target: int) -> float:
    if base_target < 100000000000:
        return 1000
    s = struct.pack(">l", base_target >> 32)
    avg_commitment = struct.unpack(">f", s)[0]
    return avg_commitment / 100000000.0


@register.simple_tag(takes_context=True)
def rank_row(context: dict, number: int) -> int:
    start = 0
    if context["page_obj"].number > 0:
        start = context["paginator"].per_page * (context["page_obj"].number - 1)

    return number + start


@register.filter
def tx_deadline(value):
    return value["timestamp"] + timedelta(minutes=value["deadline"]) - datetime.now()


@register.filter()
def sec_time(secs):
    return timedelta(seconds=secs)


@register.filter()
def smooth_timedelta(timedelta_obj):
    secs = timedelta_obj.total_seconds()
    time_str = ""
    if secs > 86400:  # 60sec * 60min * 24hrs
        days = secs // 86400
        time_str += f"{int(days)} d"
        secs = secs - days * 86400

    if secs > 3600:
        hours = secs // 3600
        time_str += f" {int(hours)} h"
        secs = secs - hours * 3600

    if secs > 60:
        minutes = ceil(secs / 60)
        time_str += f" {int(minutes)} min"

    if not time_str:
        time_str = f"{int(secs)} seconds"

    return time_str


@register.simple_tag()
def multiply(qty, unit_price, decimals, direction, *args, **kwargs):
    if isinstance(qty, str):
        qty = qty.replace(",", "")
    if isinstance(unit_price, str):
        unit_price = unit_price.replace(",", "")
    return round(float(qty) * float(unit_price) * float(direction), decimals)
