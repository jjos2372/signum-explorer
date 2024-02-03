import os

from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from burst.libs.reed_solomon import ReedSolomon, ReedSolomonError
from java_wallet import models

SEARCH_BY = [
    ("Block", "height", "/block/{}"),
    ("At", "id", "/at/{}"),
    ("Asset", "id", "/asset/{}"),
    ("Account", "id", "/address/{}"),
    #    ("Goods", "id", "/mp/{}"),
    ("Transaction", "id", "/tx/{}"),
]

REED_SOLOMON_LENS = {17, 20, 26}


@require_http_methods(["GET"])
def search_view(request):
    query = request.GET.get("q", "").strip().upper()

    redirect_url = None

    if not query:
        redirect_url = None

    elif query.isdigit():
        query = int(query)

        for x in SEARCH_BY:
            exists = getattr(models, x[0]).objects.using("java_wallet").filter(**{x[1]: query}).exists()

            if exists:
                redirect_url = x[2].format(query)
                break

    elif len(query) in REED_SOLOMON_LENS or query.find(os.environ.get("ADDRESS_PREFIX")) == 0:
        try:
            if query.find(os.environ.get("ADDRESS_PREFIX")) == 0:
                query = query[len(os.environ.get("ADDRESS_PREFIX")) :]
            numeric_id = ReedSolomon().decode(query)
            exists = models.At.objects.using("java_wallet").filter(id=numeric_id).exists()
            if exists:
                redirect_url = f"/at/{numeric_id}"
            else:
                exists = models.Account.objects.using("java_wallet").filter(id=numeric_id).exists()
                if exists:
                    redirect_url = f"/address/{numeric_id}"

        except ReedSolomonError:
            pass

    else:
        account_exists = models.Account.objects.using("java_wallet").filter(name=query).exists()
        if account_exists:
            account_id = (
                models.Account.objects.using("java_wallet")
                .filter(name=query)
                .order_by("-height")
                .values_list("id", flat=True)
                .first()
            )
            redirect_url = f"/address/{account_id}"

        # peer = (
        #     PeerMonitor.objects.filter(announced_address__icontains=query)
        #     .values("announced_address")
        #     .order_by("-height")
        #     .first()
        # )
        # if peer:
        #     redirect_url = f'/peer/{peer["announced_address"]}'

    if redirect_url:
        return redirect(redirect_url)
    else:
        return render(request, "base.html", {"submit": "Search"})
