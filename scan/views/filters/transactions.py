from django.db.models import Q
from django_filters import FilterSet, NumberFilter

from java_wallet.models import IndirectIncoming, Transaction


class TxFilter(FilterSet):
    block = NumberFilter(field_name="block__height")
    a = NumberFilter(method="filter_by_account")

    class Meta:
        model = Transaction
        fields = ("block", "a")

    @staticmethod
    def filter_by_account(queryset, name, value):
        indirects = list(
            IndirectIncoming.objects.using("java_wallet")
            .values_list("transaction_id", flat=True)
            .filter(account_id=value)
        )
        return queryset.filter(Q(sender_id=value) | Q(recipient_id=value) | Q(id__in=indirects))

    @staticmethod
    def filter_by_indirects(queryset, name, value):
        indirects = list(
            IndirectIncoming.objects.using("java_wallet").values_list("db_id", flat=True).filter(transaction_id=value)
        )
        return queryset.filter(Q(id__in=indirects))
