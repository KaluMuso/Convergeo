"""Staging-only synthetic marketplace contract (seed + transactional fixtures)."""

from app.staging.synthetic_contract import (
    CATALOG_FIXTURES,
    PERSONAS,
    SEED_PREFIX,
    SYNTHETIC_IMAGE_PREFIX,
    assert_contract_valid,
    persona_by_key,
    product_fixture,
)

__all__ = [
    "CATALOG_FIXTURES",
    "PERSONAS",
    "SEED_PREFIX",
    "SYNTHETIC_IMAGE_PREFIX",
    "assert_contract_valid",
    "persona_by_key",
    "product_fixture",
]
