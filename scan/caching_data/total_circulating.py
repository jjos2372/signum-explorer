from django.db.models import Sum

from java_wallet.models import AccountBalance
from scan.caching_data.base import CachingDataBase


class CachingTotalCirculating(CachingDataBase):
    _cache_key = "total_circulating"
    _cache_expiring = 300
    live_if_empty = True
    default_data_if_empty = 0

    def _get_live_data(self):
        return (
            AccountBalance.objects.using("java_wallet")
            .filter(balance__gt=0, latest=True)
            .exclude(id=0)
            .aggregate(Sum("balance"))["balance__sum"]
        )
