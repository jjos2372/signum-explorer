from cache_memoize import cache_memoize
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from java_wallet.models import AccountBalance
from scan.models import PeerMonitor


@cache_memoize(300)
@require_http_methods(["GET"])
def top_accounts_json(request, results=10):
    bal = list(
        AccountBalance.objects.all()
        .filter(latest=True, balance__gte=10000000000000)
        .exclude(id=0)
        .order_by("-balance")
        .values("id", "balance")[:results]
    )
    return JsonResponse(bal, safe=False)


@cache_memoize(10)
@require_http_methods(["GET"])
def get_state_json(request, address):
    state = PeerMonitor.objects.only("state").get(real_ip=address).state
    return JsonResponse(state, safe=False)


@cache_memoize(300)
@require_http_methods(["GET"])
def get_snr_json(request):
    snrraw = list(PeerMonitor.objects.all().values_list("announced_address", "real_ip", "reward_state", "reward_time"))
    return JsonResponse(snrraw, safe=False)
