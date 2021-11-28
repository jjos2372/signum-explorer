from datetime import datetime, timedelta
from math import ceil
import sys

from django import template
from django.conf import settings

from burst.constants import MAX_BASE_TARGET, TxSubtypeBurstMining, TxType
from burst.libs.functions import calc_block_reward
from burst.libs.reed_solomon import ReedSolomon
from burst.libs.transactions import get_message
from burst.api.brs.v1.api import BrsApi

from java_wallet.fields import get_desc_tx_type
from java_wallet.models import Block, Transaction
from scan.caching_data.exchange import CachingExchangeData

import struct
import os

register = template.Library()


@register.filter
def block_reward(block: Block) -> int:
    return calc_block_reward(block.height)


@register.filter
def block_reward_with_fee(block: Block) -> float:
    return calc_block_reward(block.height) + block.total_fee / 10 ** 8

@register.filter
def asset_circulating(asset_id: int) -> int:
    asset_details = BrsApi(settings.SIGNUM_NODE).get_asset(asset_id)
    return int(asset_details["quantityCirculatingQNT"])

@register.filter
def burst_amount(value: int) -> float:
    return value / 100000000.0

@register.filter
def append_symbol(value: float) -> str:
    return value + " " + os.environ.get("COIN_SYMBOL")

@register.simple_tag()
def coin_symbol() -> str:
    return os.environ.get("COIN_SYMBOL")


@register.filter
def in_usd(value: float) -> float:
    data = CachingExchangeData().cached_data
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
def tx_message(tx: Transaction) -> str:
    if not tx.has_message:
        return ""
    return get_message(tx.attachment_bytes)


@register.filter
def tx_type(tx: Transaction) -> str:
    return get_desc_tx_type(tx.type, tx.subtype)

@register.filter
def tx_amount(tx: Transaction) -> int:
    if tx.type == TxType.BURST_MINING and (tx.subtype == TxSubtypeBurstMining.COMMITMENT_ADD or tx.subtype == TxSubtypeBurstMining.COMMITMENT_REMOVE):
        return int.from_bytes(tx.attachment_bytes[1:], byteorder=sys.byteorder)
    return tx.amount

@register.filter
def num2rs(value: str or int) -> str:
    return os.environ.get("ADDRESS_PREFIX") + ReedSolomon().encode(str(value))


@register.simple_tag()
def block_generation_time(block: Block) -> timedelta:
    if block.previous_block:
        return block.timestamp - block.previous_block.timestamp
    else:
        # first block
        return timedelta(0)


@register.filter
def sub(a: int or float, b: int or float) -> int or float:
    return a - b


@register.filter
def div(a: int or float, b: int or float) -> float:
    return a / b


@register.filter
def mul(a: int or float, b: int or float) -> int or float:
    return a * b


@register.filter
def div_decimals(a: int or float, b: int) -> float:
    return a / 10 ** b


@register.filter
def mul_decimals(a: int or float, b: int) -> float:
    return a * 10 ** b


@register.filter
def percent(value: int or float, total: int or float) -> int or float:
    return value / total * 100


@register.filter
def net_capacity_tib(base_target: int) -> float:
    if base_target < 100000000000:
        return MAX_BASE_TARGET / (base_target)
    s = struct.pack('>l', base_target & 0xFFFFFFFF)
    base_target_capacity = struct.unpack('>f', s)[0]
    return MAX_BASE_TARGET / (1.83 * base_target_capacity)

@register.filter
def format_capacity(capacity: float) -> str:
    unit = "TiB"
    if capacity > 10000:
        capacity = capacity/1024
        unit = "PiB"
    return "{:.1f}".format(capacity) + " " + unit

@register.filter
def net_commitment(base_target: int) -> float:
    if base_target < 100000000000:
        return 1000
    s = struct.pack('>l', base_target >> 32)
    avg_commitment = struct.unpack('>f', s)[0]
    return avg_commitment/100000000.0

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
