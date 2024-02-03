import logging
import random
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from distutils.version import LooseVersion
from functools import lru_cache
from time import sleep
from urllib.parse import urlparse

import requests
from cache_memoize import cache_memoize
from django import forms
from django.conf import settings
from django.db import transaction
from django.db.models import DurationField, ExpressionWrapper, F
from django.db.models.functions import Now
from django.utils import timezone
from requests.exceptions import RequestException

from burst.api.brs.p2p import P2PApi
from burst.api.exceptions import BurstException
from config.settings import PEERS_SCAN_DELAY
from java_wallet.models import Block
from scan.models import PeerMonitor

logger = logging.getLogger(__name__)

if PEERS_SCAN_DELAY > 0:
    logger.info(f"Peers sleeping for {PEERS_SCAN_DELAY} seconds...")
sleep(PEERS_SCAN_DELAY)


def get_ip_by_domain(peer: str) -> str or None:
    # truncating port if exists
    if not peer.startswith("http"):
        peer = f"http://{peer}"
    hostname = urlparse(peer).hostname

    if not hostname:
        return None

    # ipv6
    if ":" in hostname:
        return hostname

    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror as e:
        logger.debug("Can't resolve host: %s - %r", peer, e)
        return None


@cache_memoize(60 * 60 * 24 * 7)
def get_country_by_ip(ip: str) -> str:
    try:
        response = requests.get(f"https://ipwho.is/{ip}")
        response.raise_for_status()
        json_response = response.json()
        georesponse = json_response["continent"] or "??"
        logger.info("Geo lookup, found peer from: %s", georesponse)
        return json_response["country_code"] or "??"
    except (RequestException, ValueError, KeyError):
        logger.warning("Geo lookup ERROR!")
        return "??"


class PeerMonitorForm(forms.ModelForm):
    class Meta:
        model = PeerMonitor
        fields = [
            "announced_address",
            "real_ip",
            "platform",
            "application",
            "version",
            "height",
            "cumulative_difficulty",
            "country_code",
            "state",
            "downtime",
            "lifetime",
            "availability",
            "last_online_at",
        ]


def is_good_version(version: str) -> bool:
    if not version:
        return False
    if version[0] == "v":
        version = version[1:]

    try:
        return LooseVersion(version) >= LooseVersion(settings.MIN_PEER_VERSION)
    except TypeError:
        return False


def get_local_difficulty() -> dict:
    latest_blocks = (
        Block.objects.using("java_wallet").order_by("-height").values("height", "cumulative_difficulty", "id")[:3]
    )
    result = latest_blocks[1]

    result["cumulative_difficulty"] = str(int(result["cumulative_difficulty"].hex(), 16))
    result["previous_block_id"] = latest_blocks[2]["id"]

    return result


@lru_cache(maxsize=None)
def get_block_cumulative_difficulty(height: int) -> str:
    cumulative_difficulty = (
        Block.objects.using("java_wallet").filter(height=height).values_list("cumulative_difficulty", flat=True).first()
    )
    return str(int(cumulative_difficulty.hex(), 16))


def explore_peer(local_difficulty: dict, address: str, updates: dict):
    logger.debug("Peer: %s", address)

    if address in updates:
        return

    try:
        p2p_api = P2PApi(address)
        peer_info = p2p_api.get_info()
        if not is_good_version(peer_info["version"]):
            logger.debug("Old version: %s", peer_info["version"])
            updates[address] = None
            return
        if "announcedAddress" not in peer_info:
            peer_info["announcedAddress"] = address

        default_port = ":" + str(settings.DEFAULT_P2P_PORT)
        peer_info["announcedAddress"] = peer_info["announcedAddress"].replace(default_port, "")
        peer_info.update(p2p_api.get_cumulative_difficulty())
        peer_info["next_block_ids"] = []
        try:
            peer_info["next_block_ids"] = p2p_api.get_next_block_ids(local_difficulty["previous_block_id"])
        except Exception:
            logger.debug("Could not get next block ids for " + p2p_api.node_url)
    except BurstException:
        logger.debug("Can't connect to peer: %s", p2p_api.node_url)
        updates[address] = None
        return

    ip = get_ip_by_domain(address)

    updates[address] = {
        "announced_address": peer_info["announcedAddress"],
        "real_ip": ip,
        "country_code": get_country_by_ip(ip) if ip else "??",
        "application": peer_info["application"],
        "platform": peer_info["platform"],
        "version": peer_info["version"],
        "height": peer_info["blockchainHeight"],
        "cumulative_difficulty": peer_info["cumulativeDifficulty"],
        "last_online_at": timezone.now(),
        "next_block_ids": peer_info["next_block_ids"],
    }


def explore_node(local_difficulty: dict, address: str, updates: dict):
    logger.debug("Node: %s", address)

    try:
        peers = P2PApi(address).get_peers()
        explore_peer(local_difficulty, address, updates)
    except BurstException:
        logger.debug("Can't connect to node: %s", address)
        return

    if settings.DEBUG:
        for peer in peers:
            explore_peer(local_difficulty, peer, updates)
    else:
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(lambda p: explore_peer(local_difficulty, p, updates), peers)


def get_nodes_list() -> list:
    # first check UNREACHABLE because more chance they are still offline
    # and timeout connection in worker
    addresses_offline = (
        list(
            PeerMonitor.objects.values_list("announced_address", flat=True)
            .filter(state=PeerMonitor.State.UNREACHABLE)
            .distinct()
        )
        or []
    )

    # get other addresses exclude UNREACHABLE
    addresses_other = (
        list(
            PeerMonitor.objects.values_list("announced_address", flat=True)
            .exclude(state=PeerMonitor.State.UNREACHABLE)
            .distinct()
        )
        or []
    )

    # add well-known peers
    addresses_other.extend(settings.BRS_BOOTSTRAP_PEERS)

    # mix it
    random.shuffle(addresses_offline)
    random.shuffle(addresses_other)

    # first UNREACHABLE
    return addresses_offline + addresses_other


def check_state(local_difficulty: dict, update: dict, peer_obj: PeerMonitor or None) -> int:
    check_id = str(local_difficulty["id"])

    if update["height"] > local_difficulty["height"]:
        if check_id in update["next_block_ids"]:
            state = PeerMonitor.State.ONLINE
        else:
            state = PeerMonitor.State.FORKED
    else:
        if peer_obj and peer_obj.height == update["height"]:
            state = PeerMonitor.State.STUCK
        else:
            _cumulative_difficulty = get_block_cumulative_difficulty(update["height"])
            if update["cumulative_difficulty"] == _cumulative_difficulty:
                state = PeerMonitor.State.SYNC
            else:
                state = PeerMonitor.State.FORKED

    return state


def get_count_nodes_online() -> int:
    return PeerMonitor.objects.filter(state=PeerMonitor.State.ONLINE).count()


# @lock_decorator(key="peer_monitor", auto_renewal=True) #locking up peers for some reason
@transaction.atomic
def peer_cmd():
    logger.info("Start the scan")

    local_difficulty = get_local_difficulty()
    logger.info(
        f"Checking for height: {local_difficulty['height']}, id: {local_difficulty['id']}, "
        f"prev id: {local_difficulty['previous_block_id']}"
    )

    addresses = get_nodes_list()
    # logger.info("The list of peers:") #enable to troubleshoot peers list
    # logger.info(addresses)            #enable to troubleshoot peers list
    # explore every peer and collect updates
    updates = {}
    if settings.TEST_NET:
        for address in addresses:
            explore_node(local_difficulty, address, updates)
    else:
        with ThreadPoolExecutor(max_workers=20) as executor:
            executor.map(lambda address: explore_node(local_difficulty, address, updates), addresses)
    updates_with_data = tuple(filter(lambda x: x is not None, updates.values()))
    # if more than __% peers were gone offline in __min, probably network problem
    if len(updates_with_data) < get_count_nodes_online() * 0.8:
        logger.warning("Peers update was rejected: %d - %d", len(updates_with_data), len(addresses))
        return

    # set all peers unreachable, if will no update - peer will be unreachable
    PeerMonitor.objects.update(state=PeerMonitor.State.UNREACHABLE)

    # calculate state and apply updates
    for update in updates_with_data:
        logger.debug("Update: %r", update)

        peer_obj = PeerMonitor.objects.filter(announced_address=update["announced_address"]).first()
        if not peer_obj:
            logger.info("Found new peer: %s", update["announced_address"])

        update["state"] = check_state(local_difficulty, update, peer_obj)

        form = PeerMonitorForm(update, instance=peer_obj)

        if form.is_valid():
            form.save()
        else:
            logger.info("Not valid data: %r - %r", form.errors, update)

    PeerMonitor.objects.update(lifetime=F("lifetime") + 1)

    PeerMonitor.objects.filter(
        state__in=[PeerMonitor.State.UNREACHABLE, PeerMonitor.State.STUCK, PeerMonitor.State.FORKED]
    ).update(downtime=F("downtime") + 1)

    PeerMonitor.objects.annotate(
        duration=ExpressionWrapper(Now() - F("last_online_at"), output_field=DurationField())
    ).filter(duration__gte=timedelta(days=5)).delete()

    PeerMonitor.objects.update(
        availability=100 - (F("downtime") / F("lifetime") * 100),
        modified_at=timezone.now(),
    )

    logger.info("Done")
