"""M11-P06 — pre-acceptance contact-info stripping tests.

Covers the pure ``strip_contacts`` util (evasion corpus + price false-positive
guard) and the ``quotes.py`` wiring (pre-acceptance strip + moderation log,
post-acceptance left untouched, repeated-evasion provider flag threshold).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.quotes import (
    CONTACT_EVASION_FLAG_REASON,
    CONTACT_EVASION_FLAG_THRESHOLD,
    CONTACT_STRIP_ACTION,
)
from app.services.moderation.contact_strip import NOTICE_TOKEN, strip_contacts
from fastapi.testclient import TestClient
from tests.test_quotes import (
    CUSTOMER_A_ID,
    JOB_ID,
    VENDOR_A_ID,
    VENDOR_OWNER_A,
    FakeSupabaseClient,
    _seed_job,
    _seed_match_outbox,
    _seed_service,
    _seed_vendor,
)

# --- evasion corpus (>= 15 distinct patterns) --------------------------------

EVASION_CORPUS: list[str] = [
    "Call me on 0971234567 today",
    "reach 097 123 4567 anytime",
    "digits 09 7 1 234 567 ok",
    "dotted 09.7.1.234.567 here",
    "dashed 097-123-4567 please",
    "e164 +260971234567 mobile",
    "spaced +260 97 123 4567 line",
    "cc 260 97 123 4567 number",
    "airtel 0770123456 works",
    "ping me on whatsapp 0971234567",
    "link wa.me/260971234567 chat",
    "full https://wa.me/260971234567 now",
    "group chat.whatsapp.com/ABCdef123 join",
    "email me john.doe@example.com fast",
    "spelled zero nine seven one two three four five six seven",
    "oh nine seven one two three four five call",
    "short code 961234567 mobile",
]

# --- price / benign false-positive guard (must NOT be stripped) --------------

FALSE_POSITIVE_CORPUS: list[str] = [
    "The job costs K970 total",
    "Budget is ZMW 1,200 for this",
    "I can do it for 50000 kwacha",
    "Parts run about K1500 extra",
    "Small fix, only 250 today",
    "order 1234 confirmed",
    "budget band 5000 ngwee",
    "I can fix your tap tomorrow, includes parts",
]


@pytest.mark.parametrize("sample", EVASION_CORPUS)
def test_evasion_patterns_are_stripped(sample: str) -> None:
    result = strip_contacts(sample)
    assert result.hit_count >= 1, sample
    assert NOTICE_TOKEN in result.clean_text, sample
    assert result.stripped_spans, sample


def test_specific_contacts_removed_from_clean_text() -> None:
    assert "0971234567" not in strip_contacts("call 0971234567").clean_text
    assert "260971234567" not in strip_contacts("wa.me/260971234567").clean_text
    assert "@example.com" not in strip_contacts("mail me@example.com now").clean_text
    spelled = strip_contacts("zero nine seven one two three four five six")
    assert "zero" not in spelled.clean_text


@pytest.mark.parametrize("sample", FALSE_POSITIVE_CORPUS)
def test_prices_and_benign_text_survive(sample: str) -> None:
    result = strip_contacts(sample)
    assert result.hit_count == 0, sample
    assert result.clean_text == sample, sample
    assert NOTICE_TOKEN not in result.clean_text, sample


def test_empty_and_none_inputs() -> None:
    assert strip_contacts(None).clean_text == ""
    assert strip_contacts("").hit_count == 0


def test_overlapping_link_and_phone_count_once() -> None:
    result = strip_contacts("join https://wa.me/260971234567 please")
    assert result.hit_count == 1


def test_multiple_distinct_hits_counted() -> None:
    result = strip_contacts("phone 0971234567 or email a@b.com")
    assert result.hit_count == 2


# --- router wiring -----------------------------------------------------------


@pytest.fixture(autouse=True)
def _allow_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.quotes.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )


def _matched_fake(*, job_status: str = "open") -> FakeSupabaseClient:
    fake = FakeSupabaseClient()
    _seed_vendor(
        fake,
        vendor_id=VENDOR_A_ID,
        owner_user_id=VENDOR_OWNER_A,
        display_name="Alpha Plumbing",
    )
    _seed_service(
        fake,
        service_id="service-a",
        vendor_id=VENDOR_A_ID,
        category="home_services",
        service_area="Lusaka, Woodlands",
    )
    _seed_job(fake, status=job_status)
    _seed_match_outbox(fake, job_id=JOB_ID, vendor_id=VENDOR_A_ID)
    return fake


def _provider_client(fake: FakeSupabaseClient) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=VENDOR_OWNER_A, roles=frozenset({"vendor"}), token="token-a"
    )
    return TestClient(app, raise_server_exceptions=False)


def _seed_prior_evasions(fake: FakeSupabaseClient, *, vendor_id: str, count: int) -> None:
    for _ in range(count):
        fake.tables["audit_log"].rows.append(
            {
                "id": str(uuid4()),
                "actor": "00000000-0000-0000-0000-000000000001",
                "action": CONTACT_STRIP_ACTION,
                "entity_type": "vendor",
                "entity_id": vendor_id,
                "after": {"hit_count": 1, "stripped": ["0971234567"]},
            }
        )


class TestPreAcceptanceStripping:
    def test_contact_stripped_and_logged_on_submit(self) -> None:
        fake = _matched_fake()
        client = _provider_client(fake)
        response = client.post(
            f"/jobs/{JOB_ID}/quotes",
            json={
                "amount_ngwee": 150_000,
                "message": "Best price K970. Call me 0971234567 or wa.me/260971234567",
                "validity_days": 7,
            },
        )
        assert response.status_code == 200
        message = response.json()["quote"]["message"]
        assert NOTICE_TOKEN in message
        assert "0971234567" not in message
        assert "260971234567" not in message
        # Price survives the strip.
        assert "K970" in message

        audit_rows = [
            row
            for row in fake.tables["audit_log"].rows
            if row.get("action") == CONTACT_STRIP_ACTION
            and row.get("entity_id") == VENDOR_A_ID
        ]
        assert len(audit_rows) == 1
        assert audit_rows[0]["after"]["stripped"]

    def test_clean_message_produces_no_moderation_log(self) -> None:
        fake = _matched_fake()
        client = _provider_client(fake)
        response = client.post(
            f"/jobs/{JOB_ID}/quotes",
            json={"amount_ngwee": 150_000, "message": "I can fix it tomorrow for K450"},
        )
        assert response.status_code == 200
        assert response.json()["quote"]["message"] == "I can fix it tomorrow for K450"
        assert not [
            row
            for row in fake.tables["audit_log"].rows
            if row.get("action") == CONTACT_STRIP_ACTION
        ]


class TestPostAcceptanceUntouched:
    def test_accepted_job_rejects_new_quote_and_never_strips(self) -> None:
        # Job past acceptance leaves JOB_QUOTABLE_STATUSES -> submit path unreachable,
        # so the strip/moderation log is never applied post-acceptance.
        fake = _matched_fake(job_status="accepted")
        client = _provider_client(fake)
        response = client.post(
            f"/jobs/{JOB_ID}/quotes",
            json={"amount_ngwee": 150_000, "message": "call 0971234567"},
        )
        assert response.status_code == 409
        assert not [
            row
            for row in fake.tables["audit_log"].rows
            if row.get("action") == CONTACT_STRIP_ACTION
        ]
        assert fake.tables["job_quotes"].rows == []


class TestEvasionThreshold:
    def test_flag_raised_at_threshold(self) -> None:
        fake = _matched_fake()
        _seed_prior_evasions(
            fake, vendor_id=VENDOR_A_ID, count=CONTACT_EVASION_FLAG_THRESHOLD - 1
        )
        client = _provider_client(fake)
        response = client.post(
            f"/jobs/{JOB_ID}/quotes",
            json={"amount_ngwee": 150_000, "message": "reach me 0971234567"},
        )
        assert response.status_code == 200
        flags = [
            row
            for row in fake.table("flags").rows
            if row.get("entity_id") == VENDOR_A_ID
            and row.get("reason") == CONTACT_EVASION_FLAG_REASON
        ]
        assert len(flags) == 1
        assert flags[0]["status"] == "open"
        assert flags[0]["reporter_user_id"] == CUSTOMER_A_ID

    def test_no_flag_below_threshold(self) -> None:
        fake = _matched_fake()
        client = _provider_client(fake)
        response = client.post(
            f"/jobs/{JOB_ID}/quotes",
            json={"amount_ngwee": 150_000, "message": "reach me 0971234567"},
        )
        assert response.status_code == 200
        assert fake.table("flags").rows == []
