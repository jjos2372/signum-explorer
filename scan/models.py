from django.db.models import (
    CharField,
    DateTimeField,
    FloatField,
    Model,
    PositiveIntegerField,
    PositiveSmallIntegerField,
)
from django.utils.translation import gettext as _


class PeerMonitor(Model):
    class State:
        ONLINE = 1
        UNREACHABLE = 2
        SYNC = 3
        STUCK = 4
        FORKED = 5

    STATE_CHOICES = (
        (State.ONLINE, _("online")),
        (State.UNREACHABLE, _("unreachable")),
        (State.SYNC, _("in sync")),
        (State.STUCK, _("stuck")),
        (State.FORKED, _("forked")),
    )

    announced_address = CharField(primary_key=True, max_length=255)
    real_ip = CharField(max_length=255, blank=True)
    platform = CharField(max_length=255, blank=True)
    application = CharField(max_length=255, blank=True)
    version = CharField(max_length=255, blank=True)

    height = PositiveIntegerField(db_index=True, blank=True)
    cumulative_difficulty = CharField(max_length=255, blank=True)

    country_code = CharField(max_length=2, blank=True)
    state = PositiveSmallIntegerField(choices=STATE_CHOICES, db_index=True)
    downtime = PositiveIntegerField(default=0, blank=True)
    lifetime = PositiveIntegerField(default=0, blank=True)
    availability = FloatField(default=0, blank=True)

    last_online_at = DateTimeField()

    created_at = DateTimeField(auto_now_add=True)
    modified_at = DateTimeField(auto_now=True)

    reward_state = CharField(max_length=255, blank=True, null=True, default="none")
    reward_time = DateTimeField(blank=True, null=True)
