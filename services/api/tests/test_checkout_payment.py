from __future__ import annotations

import uuid
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.routers.checkout_payment import (
    ALLOWED_MOMO_RAILS,
    DEFAULT_COD_CAP_NGEWEE,
    _is_valid_payer_number,
    _normalize_payer_number,
    _validate_payment_method,
)
from fastapi.testclient import TestClient

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VALID_TOKEN = "valid-test-token"
COD_CAP = DEFAULT_COD_CAP_NGEWEE


def _current_user() -> CurrentUser:
    return CurrentUser(id=CUSTOMER_ID, roles=frozenset({"customer"}), token=VALID_TOKEN)


def _mock_service(
    *,
    session_id: str,
    subtotal: int,
    delivery_fee: int,
    total: int,
    cod_cap: int = COD_CAP,
) -> MagicMock:
    service = MagicMock()

    def table_side_effect(name: str) -> MagicMock:
        table = MagicMock()
        if name == "checkout_groups":
            select_chain = table.select.return_value.eq.return_value.eq.return_value
            chain = select_chain.maybe_single.return_value
            chain.execute.return_value = MagicMock(
                data={
                    "id": session_id,
                    "customer_id": CUSTOMER_ID,
                    "subtotal_ngwee": subtotal,
                    "delivery_fee_ngwee": delivery_fee,
                    "total_ngwee": total,
                    "status": "pending",
                    "created_at": "2099-01-01T00:00:00+00:00",
                }
            )
        elif name == "stock_reservations":
            chain = table.select.return_value.eq.return_value.order.return_value.limit.return_value
            chain.execute.return_value = MagicMock(
                data=[{"expires_at": "2099-01-01T00:00:00+00:00"}]
            )
        elif name == "platform_config":
            chain = table.select.return_value.eq.return_value.maybe_single.return_value
            chain.execute.return_value = MagicMock(data={"value": cod_cap})
        return table

    service.client.table.side_effect = table_side_effect
    return service


def _client_with_service(service: MagicMock) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _current_user

    def _override_service() -> Generator[object, None, None]:
        yield service

    app.dependency_overrides[get_supabase_client] = _override_service
    return TestClient(app, raise_server_exceptions=False)


class TestPayerNumberValidation:
    def test_valid_mtn_number(self) -> None:
        assert _is_valid_payer_number("+260971234567") is True

    def test_valid_airtel_number(self) -> None:
        assert _is_valid_payer_number("+260971234567") is True

    def test_rejects_invalid_prefix(self) -> None:
        assert _is_valid_payer_number("+260871234567") is False

    def test_accepts_nine_digit_local_after_normalization(self) -> None:
        assert _is_valid_payer_number("971234567") is True
        assert _normalize_payer_number("971234567") == "+260971234567"


class TestPaymentMethodValidationUnit:
    def test_cod_allowed_at_cap(self) -> None:
        rail, payer = _validate_payment_method(
            method="cod",
            rail=None,
            payer_number=None,
            total_ngwee=COD_CAP,
            cod_cap_ngwee=COD_CAP,
        )
        assert rail is None
        assert payer is None

    def test_cod_rejected_one_ngwee_above_cap(self) -> None:
        with pytest.raises(AppError) as exc_info:
            _validate_payment_method(
                method="cod",
                rail=None,
                payer_number=None,
                total_ngwee=COD_CAP + 1,
                cod_cap_ngwee=COD_CAP,
            )
        assert exc_info.value.code == "checkout.cod_ineligible"
        assert exc_info.value.http_status == 422

    def test_zamtel_rail_rejected(self) -> None:
        with pytest.raises(AppError) as exc_info:
            _validate_payment_method(
                method="momo",
                rail="zamtel",
                payer_number="+260971234567",
                total_ngwee=10_000,
                cod_cap_ngwee=COD_CAP,
            )
        assert exc_info.value.code == "checkout.rail_not_allowed"

    def test_mtn_rail_accepted(self) -> None:
        rail, payer = _validate_payment_method(
            method="momo",
            rail="mtn",
            payer_number="+260971234567",
            total_ngwee=10_000,
            cod_cap_ngwee=COD_CAP,
        )
        assert rail == "mtn"
        assert payer == "+260971234567"

    def test_airtel_rail_accepted(self) -> None:
        rail, payer = _validate_payment_method(
            method="momo",
            rail="airtel",
            payer_number="+260971234567",
            total_ngwee=10_000,
            cod_cap_ngwee=COD_CAP,
        )
        assert rail == "airtel"
        assert payer == "+260971234567"


class TestPaymentMethodEndpoint:
    def test_cod_boundary_at_cap_allowed(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=COD_CAP,
                delivery_fee=0,
                total=COD_CAP,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={"session_id": session_id, "method": "cod"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["method"] == "cod"
        assert payload["total_ngwee"] == COD_CAP
        assert payload["cod_eligible"] is True

    def test_cod_boundary_one_ngwee_above_rejected(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=COD_CAP + 1,
                delivery_fee=0,
                total=COD_CAP + 1,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={"session_id": session_id, "method": "cod"},
        )

        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "checkout.cod_ineligible"

    def test_tampered_cod_above_cap_rejected(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=75_000,
                delivery_fee=0,
                total=75_000,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={"session_id": session_id, "method": "cod"},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "checkout.cod_ineligible"

    def test_zamtel_rail_rejected_by_server(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=10_000,
                delivery_fee=0,
                total=10_000,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={
                "session_id": session_id,
                "method": "momo",
                "rail": "zamtel",
                "payer_number": "+260971234567",
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "checkout.rail_not_allowed"

    def test_momo_mtn_accepted(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=25_000,
                delivery_fee=0,
                total=25_000,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={
                "session_id": session_id,
                "method": "momo",
                "rail": "mtn",
                "payer_number": "+260971234567",
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["rail"] == "mtn"
        assert payload["payer_number"] == "+260971234567"

    def test_invalid_payer_number_rejected(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=10_000,
                delivery_fee=0,
                total=10_000,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={
                "session_id": session_id,
                "method": "momo",
                "rail": "mtn",
                "payer_number": "+260871234567",
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "checkout.invalid_payer_number"

    def test_payment_options_reflects_cod_eligibility(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=COD_CAP + 1,
                delivery_fee=0,
                total=COD_CAP + 1,
            )
        )
        response = client.get(
            f"/checkout/steps/payment-options?session_id={session_id}",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["cod_eligible"] is False
        assert payload["cod_cap_ngwee"] == COD_CAP
        assert payload["total_ngwee"] == COD_CAP + 1

    def test_tampered_disabled_rail_rejected(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=10_000,
                delivery_fee=0,
                total=10_000,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={
                "session_id": session_id,
                "method": "momo",
                "rail": "vodacom",
                "payer_number": "+260971234567",
            },
        )

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "checkout.rail_not_allowed"
        assert set(body["error"]["details"]["allowed_rails"]) == ALLOWED_MOMO_RAILS

    def test_card_method_accepted(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=120_000,
                delivery_fee=0,
                total=120_000,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={"session_id": session_id, "method": "card"},
        )

        assert response.status_code == 200
        assert response.json()["method"] == "card"

    def test_totals_read_from_session_not_recomputed(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=30_000,
                delivery_fee=3_000,
                total=33_000,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={"session_id": session_id, "method": "card"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["subtotal_ngwee"] == 30_000
        assert payload["delivery_fee_ngwee"] == 3_000
        assert payload["total_ngwee"] == 33_000

    def test_cod_cap_read_from_platform_config(self) -> None:
        session_id = str(uuid.uuid4())
        client = _client_with_service(
            _mock_service(
                session_id=session_id,
                subtotal=40_000,
                delivery_fee=0,
                total=40_000,
                cod_cap=50_000,
            )
        )
        response = client.post(
            "/checkout/steps/payment",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={"session_id": session_id, "method": "cod"},
        )

        assert response.status_code == 200
        assert response.json()["cod_cap_ngwee"] == 50_000
