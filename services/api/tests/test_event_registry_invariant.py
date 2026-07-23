"""Guard the EVENT_REGISTRY → render-registry invariant (pure-symbol, no DB).

`services/api/app/services/notifications/events.py` documents the rule:

    "Only templates that EXIST in the WhatsApp template registry are mapped;
     everything else stays None until its template ships."

Nothing in CI enforced it, which is how a lifecycle event (e.g. ``event_cancelled``
during the FIX-K work) could be added to ``EVENT_REGISTRY`` while its template was
still missing from ``WHATSAPP_TEMPLATES`` — the outbox row enqueues but then fails
to render at send time (a latent bug the fake-based emit tests do not catch).

This test fails fast the moment a whatsapp-channel mapping points at a template
that is not fully wired (render definition + dispatch classification). i18n body
keys are covered transitively: ``test_notification_i18n.py`` asserts every
``TEMPLATE_CLASSIFICATION`` template resolves a ``whatsapp.<id>.body`` key, and
this test guarantees every mapped template is classified.
"""

from __future__ import annotations

import pytest
from app.services.notifications.dispatcher import TEMPLATE_CLASSIFICATION
from app.services.notifications.events import EVENT_REGISTRY, NotificationMapping
from app.services.notifications.templates.whatsapp import WHATSAPP_TEMPLATES

_MAPPED: list[tuple[str, NotificationMapping]] = sorted(
    ((event, mapping) for event, mapping in EVENT_REGISTRY.items() if mapping is not None),
    key=lambda item: item[0],
)


def test_registry_has_wired_events() -> None:
    """Sanity: the parametrized guard below is not vacuous."""
    assert _MAPPED, "expected at least one non-None EVENT_REGISTRY mapping"


@pytest.mark.parametrize(
    ("event", "mapping"),
    _MAPPED,
    ids=[event for event, _ in _MAPPED],
)
def test_mapped_whatsapp_template_is_fully_wired(
    event: str, mapping: NotificationMapping
) -> None:
    if mapping.channel != "whatsapp":
        pytest.skip(f"{event} routes via {mapping.channel!r}, not whatsapp")

    assert mapping.template in WHATSAPP_TEMPLATES, (
        f"EVENT_REGISTRY maps {event!r} -> {mapping.template!r}, but that template is "
        f"absent from WHATSAPP_TEMPLATES: the outbox row would enqueue yet fail to "
        f"render at send time. Add it to services/api/app/services/notifications/"
        f"templates/whatsapp.py (and sms.py) before mapping the event."
    )
    assert mapping.template in TEMPLATE_CLASSIFICATION, (
        f"{mapping.template!r} (mapped by {event!r}) has no TEMPLATE_CLASSIFICATION "
        f"entry in dispatcher.py — its send/quiet-hours classification is undefined."
    )
