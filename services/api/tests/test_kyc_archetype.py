from __future__ import annotations

from typing import Any

import pytest
from app.routers.kyc import KycSubmitRequest, _persist_vendor_basics
from pydantic import ValidationError

VENDOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _base_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tier": 1,
        "doc_storage_paths": ["kyc/nrc.jpg", "kyc/selfie.jpg"],
        "momo_phone": "0977000111",
        "legal_name": "Acme Traders",
    }
    payload.update(overrides)
    return payload


class TestArchetypeValidation:
    def test_accepts_known_archetype(self) -> None:
        req = KycSubmitRequest.model_validate(_base_payload(archetype="electronics"))
        assert req.archetype == "electronics"

    def test_blank_archetype_normalises_to_none(self) -> None:
        req = KycSubmitRequest.model_validate(_base_payload(archetype="  "))
        assert req.archetype is None

    def test_missing_archetype_is_none(self) -> None:
        req = KycSubmitRequest.model_validate(_base_payload())
        assert req.archetype is None

    def test_rejects_unknown_archetype(self) -> None:
        with pytest.raises(ValidationError):
            KycSubmitRequest.model_validate(_base_payload(archetype="weapons"))

    def test_accepts_optional_business_name(self) -> None:
        req = KycSubmitRequest.model_validate(
            _base_payload(business_name="Lusaka Spares", archetype="electronics")
        )
        assert req.business_name == "Lusaka Spares"
        assert req.archetype == "electronics"


class _RecordingTable:
    def __init__(self, sink: dict[str, Any]) -> None:
        self._sink = sink

    def update(self, payload: dict[str, Any]) -> _RecordingTable:
        self._sink["update"] = payload
        return self

    def eq(self, column: str, value: Any) -> _RecordingTable:
        self._sink.setdefault("eq", []).append((column, value))
        return self

    def execute(self) -> Any:
        self._sink["executed"] = True
        return type("R", (), {"data": []})()


class _RecordingClient:
    def __init__(self, sink: dict[str, Any]) -> None:
        self._sink = sink

    def table(self, name: str) -> _RecordingTable:
        self._sink["table"] = name
        return _RecordingTable(self._sink)


class _RecordingService:
    def __init__(self) -> None:
        self.sink: dict[str, Any] = {}
        self.client = _RecordingClient(self.sink)


class TestPersistVendorBasics:
    def test_persists_archetype_when_set(self) -> None:
        service = _RecordingService()
        _persist_vendor_basics(service, VENDOR, archetype="groceries")
        assert service.sink["table"] == "vendors"
        assert service.sink["update"] == {"archetype": "groceries"}
        assert ("id", VENDOR) in service.sink["eq"]
        assert service.sink["executed"] is True

    def test_persists_business_name_and_archetype(self) -> None:
        service = _RecordingService()
        _persist_vendor_basics(
            service,
            VENDOR,
            business_name="Chipata Market",
            archetype="groceries",
        )
        assert service.sink["update"] == {
            "display_name": "Chipata Market",
            "archetype": "groceries",
        }
        assert service.sink["executed"] is True

    def test_noop_when_none(self) -> None:
        service = _RecordingService()
        _persist_vendor_basics(service, VENDOR, business_name=None, archetype=None)
        assert service.sink == {}
