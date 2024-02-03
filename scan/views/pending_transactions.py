from django.shortcuts import render

from scan.helpers.queries import get_unconfirmed_transactions


def pending_transactions(request):
    context = {"txs_pending": get_unconfirmed_transactions()}
    return render(request, "txs_pending/list.html", context)
