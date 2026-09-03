from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.assisted_order import OpenRouterOptions
from restaurant_os.menu_parser import parse_menu_document
from restaurant_os.saas_onboarding import (
    import_custom_catalog_for_org,
    seed_starter_catalog_for_org,
)
from sqlalchemy.orm import Session

UTC = timezone.utc
ORG_ID = "018f6f73-2d0a-74f0-8f1c-000000000001"
BRANCH_1 = "018f6f73-2d0a-74f0-8f1c-000000000010"
BRANCH_2 = "018f6f73-2d0a-74f0-8f1c-000000000020"


def _seed_org_and_multiple_branches(session: Session, now: datetime) -> None:
    session.execute(
        models.organizations.insert().values(
            id=ORG_ID,
            name="Org Multiple Branches",
            created_at=now,
            updated_at=now,
        )
    )
    legal_entity_id = "018f6f73-2d0a-74f0-8f1c-000000001011"
    unit_id = "018f6f73-2d0a-74f0-8f1c-000000001013"
    session.execute(
        models.legal_entities.insert().values(
            id=legal_entity_id,
            organization_id=ORG_ID,
            name="Legal",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.business_units.insert().values(
            id=unit_id,
            organization_id=ORG_ID,
            legal_entity_id=legal_entity_id,
            name="Unit",
            code="01",
            unit_type="restaurant",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    # Insert TWO branches for the organization to trigger multiple rows
    session.execute(
        models.branches.insert().values(
            id=BRANCH_1,
            organization_id=ORG_ID,
            legal_entity_id=legal_entity_id,
            business_unit_id=unit_id,
            name="Sucursal Matriz",
            code="01",
            timezone="UTC",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.branches.insert().values(
            id=BRANCH_2,
            organization_id=ORG_ID,
            legal_entity_id=legal_entity_id,
            business_unit_id=unit_id,
            name="Sucursal Piloto",
            code="02",
            timezone="UTC",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_seed_starter_catalog_with_multiple_branches_does_not_raise_multiple_results() -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    now = datetime(2026, 9, 1, tzinfo=UTC)

    with Session(engine) as session:
        _seed_org_and_multiple_branches(session, now)

        # Must not raise MultipleResultsFound even with branch_id=None and multiple branches
        result = seed_starter_catalog_for_org(
            session=session,
            organization_id=ORG_ID,
            branch_id=None,
            business_type="taqueria",
        )
        assert result["status"] == "ok"
        assert result["template"] == "taqueria"

        # Verify categories were created
        cats = session.execute(
            sa.select(models.product_categories.c.name).where(
                models.product_categories.c.organization_id == ORG_ID
            )
        ).scalars().all()
        assert "Tacos" in cats
        assert "Bebidas" in cats

        # Verify products were linked to both active branches
        availability_count = session.execute(
            sa.select(sa.func.count(models.branch_product_availability.c.product_id))
        ).scalar()
        assert availability_count > 0

        # Running again must be idempotent and not crash
        result_again = seed_starter_catalog_for_org(
            session=session,
            organization_id=ORG_ID,
            branch_id=None,
            business_type="taqueria",
        )
        assert result_again["status"] == "ok"


def test_import_custom_catalog_creates_products_and_prices() -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    now = datetime(2026, 9, 1, tzinfo=UTC)

    with Session(engine) as session:
        _seed_org_and_multiple_branches(session, now)

        custom_catalog = [
            {
                "category": "Pizzas Gourmet",
                "products": [
                    {
                        "name": "Pizza Cuatro Quesos",
                        "price": 180.0,
                        "description": "Mozzarella, Gorgonzola, Parmesano y Provolone",
                        "station": "cocina",
                    },
                    {
                        "name": "Cerveza Artesanal",
                        "price": 65.0,
                        "description": "IPA 355ml",
                        "station": "barra",
                    },
                ],
            }
        ]

        result = import_custom_catalog_for_org(
            session=session,
            organization_id=ORG_ID,
            branch_id=BRANCH_1,
            catalog_data=custom_catalog,
            now=now,
        )
        assert result["status"] == "ok"
        assert result["created_products"] == 2

        # Verify product pricing in cents
        prod = session.execute(
            sa.select(models.products.c.id).where(
                models.products.c.name == "Pizza Cuatro Quesos",
                models.products.c.organization_id == ORG_ID,
            )
        ).scalar()
        assert prod is not None

        price_cents = session.execute(
            sa.select(models.price_versions.c.price_cents).where(
                models.price_versions.c.product_id == prod
            )
        ).scalar()
        assert price_cents == 18000


def test_parse_menu_document_with_mock_openrouter() -> None:
    mock_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "categories": [
                                {
                                    "name": "Café y Té",
                                    "products": [
                                        {
                                            "name": "Espresso Doble",
                                            "price": 42.0,
                                            "description": "Extracción doble de café de especialidad",
                                            "station": "barra",
                                        }
                                    ],
                                }
                            ]
                        }
                    )
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_opener = MagicMock(return_value=mock_resp)

    options = OpenRouterOptions(
        api_key="test-api-key-12345",
        model="google/gemini-2.5-flash",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=10.0,
    )

    result = parse_menu_document(
        file_base64="aW1hZ2VkYXRh",
        mime_type="image/jpeg",
        filename="menu_cafeteria.jpg",
        options=options,
        opener=mock_opener,
    )

    assert "categories" in result
    assert len(result["categories"]) == 1
    assert result["categories"][0]["name"] == "Café y Té"
    prod = result["categories"][0]["products"][0]
    assert prod["name"] == "Espresso Doble"
    assert prod["price"] == 42.0
    assert prod["price_cents"] == 4200
    assert prod["station"] == "barra"


def test_parse_menu_document_fallback_for_sushi_menu_without_key() -> None:
    options = OpenRouterOptions(
        api_key="",
        model="google/gemini-2.5-flash",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=10.0,
    )

    result = parse_menu_document(
        file_base64="aW1hZ2VkYXRh" * 100,
        mime_type="image/jpeg",
        filename="menusushi.jpg",
        options=options,
    )

    assert "categories" in result
    category_names = [c["name"] for c in result["categories"]]
    assert "Sushi" in category_names
    assert "Gratinados" in category_names
    assert "Bebidas" in category_names

    sushi_cat = next(c for c in result["categories"] if c["name"] == "Sushi")
    assert any(p["name"] == "Baby Roll" and p["price"] == 95.0 and p["station"] == "cocina" for p in sushi_cat["products"])

    bebidas_cat = next(c for c in result["categories"] if c["name"] == "Bebidas")
    assert any(p["name"] == "Té 1LT" and p["station"] == "barra" for p in bebidas_cat["products"])


def test_parse_menu_document_with_gemini_direct_key() -> None:
    mock_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "categories": [
                                        {
                                            "name": "Bebidas",
                                            "products": [
                                                {
                                                    "name": "Limonada Rosa",
                                                    "price": 38.0,
                                                    "description": "Limonada natural con frutos rojos",
                                                    "station": "barra",
                                                }
                                            ],
                                        }
                                    ]
                                }
                            )
                        }
                    ]
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_opener = MagicMock(return_value=mock_resp)

    options = OpenRouterOptions(
        api_key="AIzaSyDummyGeminiApiKeyForTest12345",
        model="google/gemini-2.5-flash",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=10.0,
    )

    result = parse_menu_document(
        file_base64="aW1hZ2VkYXRh",
        mime_type="image/jpeg",
        filename="menu.jpg",
        options=options,
        opener=mock_opener,
    )

    assert "categories" in result
    assert result["categories"][0]["name"] == "Bebidas"
    assert result["categories"][0]["products"][0]["name"] == "Limonada Rosa"
    assert result["categories"][0]["products"][0]["price"] == 38.0
    assert result["categories"][0]["products"][0]["station"] == "barra"
