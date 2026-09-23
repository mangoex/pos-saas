"""Real Kiwi Branch Catalog Loader.

Imports and structures:
- 156 base supplies from INSUMOS.XLS
- 159 commercial presentations from PRESENTACIONES.XLS with yield factors
- 16 sale categories and 165 sale products from PRODUCTOS.XLS with exact tax and price versions
- 7 modifier categories with 152 options from PRODUCTOS.XLS linked to sale products
- 33,219 customer records from CLIENTES.XLS with workplace / branch reference notes
"""

from __future__ import annotations

# ruff: noqa: E501
import os
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.orm import Session

from . import models
from .category_deletion import lock_catalog_organization
from .operations import BRANCH_ID, ORGANIZATION_ID, BusinessError, _now


def _uid() -> str:
    return str(uuid4())


def load_real_catalog_from_excels(
    session: Session,
    excel_dir: str = ".",
    organization_id: str = ORGANIZATION_ID,
    branch_id: str = BRANCH_ID,
    import_customers: bool = True,
    max_customers: int | None = None,
) -> dict[str, int]:
    """Imports all clean records from the 5 real excel files into the active database."""
    lock_catalog_organization(session, organization_id)
    now = _now()
    summary = {
        "units": 0,
        "supplies": 0,
        "presentations": 0,
        "categories": 0,
        "products": 0,
        "modifier_groups": 0,
        "modifier_options": 0,
        "customers": 0,
    }

    # -------------------------------------------------------------
    # 1. INVENTORY UNITS (KILO, LITRO, PIEZA)
    # -------------------------------------------------------------
    units_def = [
        ("KG", "KILO", "Kilogramo", "mass", 3),
        ("L", "LITRO", "Litro", "volume", 3),
        ("PZ", "PIEZA", "Pieza", "discrete", 0),
        ("POR", "PORCION", "Porción", "discrete", 0),
    ]
    unit_map: dict[str, str] = {}  # code -> id
    for short_code, code, name, dimension, precision in units_def:
        existing = session.execute(
            sa.select(models.inventory_units.c.id).where(
                models.inventory_units.c.organization_id == organization_id,
                models.inventory_units.c.code == code,
            )
        ).scalar_one_or_none()
        if existing:
            unit_id = str(existing)
        else:
            unit_id = f"unit-{code.lower()}"
            session.execute(
                models.inventory_units.insert().values(
                    id=unit_id,
                    organization_id=organization_id,
                    code=code,
                    name=name,
                    dimension=dimension,
                    precision_scale=precision,
                    created_at=now,
                )
            )
            summary["units"] += 1
        unit_map[code] = unit_id
        unit_map[short_code] = unit_id

    # -------------------------------------------------------------
    # 2. INVENTORY SUPPLIES (INSUMOS.XLS)
    # -------------------------------------------------------------
    insumos_path = os.path.join(excel_dir, "INSUMOS.XLS")
    supply_map: dict[str, str] = {}  # legacy_clave / sku -> item_id
    if os.path.exists(insumos_path):
        df_ins = pd.read_excel(insumos_path, header=4).dropna(subset=["CLAVE", "DESCRIPCION"])
        for _, row in df_ins.iterrows():
            clave = str(row["CLAVE"]).strip()
            desc = str(row["DESCRIPCION"]).strip()
            grupo = (
                str(row["GRUPODEINSUMOS"]).strip() if pd.notna(row["GRUPODEINSUMOS"]) else "GENERAL"
            )
            raw_unit = (
                str(row["UNIDADDEMEDIDA"]).strip().upper()
                if pd.notna(row["UNIDADDEMEDIDA"])
                else "KILO"
            )
            unit_code = (
                "KILO"
                if "KIL" in raw_unit or "KG" in raw_unit
                else ("LITRO" if "LIT" in raw_unit or "LTS" in raw_unit else "PIEZA")
            )
            unit_id = unit_map.get(unit_code, unit_map["KILO"])
            sku = f"INS-{clave}"

            existing = session.execute(
                sa.select(models.inventory_items.c.id).where(
                    models.inventory_items.c.organization_id == organization_id,
                    models.inventory_items.c.sku == sku,
                )
            ).scalar_one_or_none()

            if existing:
                item_id = str(existing)
                session.execute(
                    sa.update(models.inventory_items)
                    .where(models.inventory_items.c.id == item_id)
                    .values(
                        name=desc[:160],
                        category_name=grupo[:120],
                        base_unit_id=unit_id,
                        status="active",
                        updated_at=now,
                    )
                )
            else:
                item_id = f"item-ins-{clave.lower()}"
                session.execute(
                    models.inventory_items.insert().values(
                        id=item_id,
                        organization_id=organization_id,
                        name=desc[:160],
                        sku=sku[:64],
                        base_unit_id=unit_id,
                        item_type="ingredient",
                        category_name=grupo[:120],
                        catalog_scope="organization",
                        source_branch_id=None,
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
                summary["supplies"] += 1
            supply_map[clave] = item_id
            supply_map[sku] = item_id

    # -------------------------------------------------------------
    # 3. SUPPLIERS & PURCHASE PRESENTATIONS (PRESENTACIONES.XLS)
    # -------------------------------------------------------------
    default_supplier_id = "sup-general-kiwi"
    existing_sup = session.execute(
        sa.select(models.suppliers.c.id).where(
            models.suppliers.c.organization_id == organization_id,
            models.suppliers.c.id == default_supplier_id,
        )
    ).scalar_one_or_none()
    if not existing_sup:
        session.execute(
            models.suppliers.insert().values(
                id=default_supplier_id,
                organization_id=organization_id,
                code="SUP-KIWI-01",
                commercial_name="Proveedores Locales Culiacán",
                legal_name="Proveedores Locales S.A. de C.V.",
                tax_id="MECA9102201G4",
                currency="MXN",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )

    pres_path = os.path.join(excel_dir, "PRESENTACIONES.XLS")
    if os.path.exists(pres_path):
        df_pres = pd.read_excel(pres_path, header=4).dropna(subset=["CLAVE", "DESCRIPCION"])
        for _, row in df_pres.iterrows():
            clave = str(row["CLAVE"]).strip()
            desc = str(row["DESCRIPCION"]).strip()
            rendimiento = (
                Decimal(str(row["RENDIMIENTO"]))
                if pd.notna(row["RENDIMIENTO"]) and float(row["RENDIMIENTO"]) > 0
                else Decimal("1.000")
            )
            raw_unit = str(row["UNIDAD"]).strip().upper() if pd.notna(row["UNIDAD"]) else "KILO"
            unit_code = (
                "KILO"
                if "KIL" in raw_unit or "KG" in raw_unit
                else ("LITRO" if "LIT" in raw_unit or "LTS" in raw_unit else "PIEZA")
            )
            unit_id = unit_map.get(unit_code, unit_map["KILO"])

            ultimo_costo = (
                Decimal(str(row["ULTIMOCOSTO"]))
                if pd.notna(row["ULTIMOCOSTO"])
                else Decimal("0.00")
            )
            impuesto = (
                Decimal(str(row["IMPUESTO"])) / Decimal("100")
                if pd.notna(row["IMPUESTO"])
                else Decimal("0.00")
            )
            cost_per_base = (ultimo_costo / rendimiento) if rendimiento > 0 else ultimo_costo

            item_id = supply_map.get(clave)
            if not item_id:
                item_id = f"item-ins-{clave.lower()}"
                session.execute(
                    models.inventory_items.insert().values(
                        id=item_id,
                        organization_id=organization_id,
                        name=desc[:160],
                        sku=f"INS-{clave}",
                        base_unit_id=unit_id,
                        item_type="ingredient",
                        category_name="GENERAL",
                        catalog_scope="organization",
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
                supply_map[clave] = item_id

            pres_code = f"PRES-{clave}"
            existing_pres = session.execute(
                sa.select(models.purchase_presentations.c.id).where(
                    models.purchase_presentations.c.organization_id == organization_id,
                    models.purchase_presentations.c.code == pres_code,
                )
            ).scalar_one_or_none()

            if existing_pres:
                session.execute(
                    sa.update(models.purchase_presentations)
                    .where(models.purchase_presentations.c.id == str(existing_pres))
                    .values(
                        name=desc[:180],
                        package_type="comercial",
                        commercial_quantity=Decimal("1.000"),
                        commercial_unit_id=unit_id,
                        base_unit_id=unit_id,
                        base_unit_yield=rendimiento,
                        usable_content=rendimiento,
                        yield_percent=Decimal("1.000"),
                        tax_rate=impuesto,
                        last_net_price=ultimo_costo,
                        cost_per_base_unit=cost_per_base,
                        status="active",
                        updated_at=now,
                    )
                )
            else:
                pres_id = f"pres-{clave.lower()}"
                session.execute(
                    models.purchase_presentations.insert().values(
                        id=pres_id,
                        organization_id=organization_id,
                        supplier_id=default_supplier_id,
                        item_id=item_id,
                        code=pres_code,
                        name=desc[:180],
                        package_type="comercial",
                        commercial_quantity=Decimal("1.000"),
                        commercial_unit_id=unit_id,
                        base_unit_id=unit_id,
                        base_unit_yield=rendimiento,
                        gross_content=rendimiento,
                        net_content=rendimiento,
                        usable_content=rendimiento,
                        yield_percent=Decimal("1.000"),
                        tax_rate=impuesto,
                        last_net_price=ultimo_costo,
                        cost_per_base_unit=cost_per_base,
                        is_preferred=True,
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
                summary["presentations"] += 1

    # -------------------------------------------------------------
    # 4. PRODUCTS & MODIFIERS (PRODUCTOS.XLS)
    # -------------------------------------------------------------
    prod_path = os.path.join(excel_dir, "PRODUCTOS.XLS")
    if os.path.exists(prod_path):
        df_prod = pd.read_excel(prod_path, header=4).dropna(subset=["CLAVE", "DESCRIPCION"])

        modifier_categories = {
            "INGREDIENTE EXTRA",
            "EXTRA JUGOS",
            "MODIFICADOR DE QUESOS/FRITURAS",
            "EXTRA LICUADOS",
            "MEDIO PARA COMBOS",
            "TIPO DE PAN/TORTILLA",
            "SERVICIOS A DOMICILIO",
        }

        category_map: dict[str, str] = {}
        sale_rows = []
        modifier_rows = []

        for _, row in df_prod.iterrows():
            grupo = (
                str(row["GRUPODEPRODUCTOS"]).strip()
                if pd.notna(row["GRUPODEPRODUCTOS"])
                else "GENERAL"
            )
            if grupo in modifier_categories:
                modifier_rows.append(row)
            else:
                sale_rows.append(row)

        for row in sale_rows:
            grupo = (
                str(row["GRUPODEPRODUCTOS"]).strip()
                if pd.notna(row["GRUPODEPRODUCTOS"])
                else "GENERAL"
            )
            if grupo not in category_map:
                existing_cat = session.execute(
                    sa.select(models.product_categories.c.id, models.product_categories.c.status).where(
                        models.product_categories.c.organization_id == organization_id,
                        sa.func.lower(models.product_categories.c.name) == grupo.lower(),
                    )
                ).mappings().first()
                if existing_cat:
                    if existing_cat["status"] == "archived":
                        raise BusinessError("category_archived", "La importación incluye una categoría eliminada.")
                    category_map[grupo] = str(existing_cat["id"])
                else:
                    cat_id = f"cat-{grupo.lower().replace(' ', '-').replace('/', '-')[:30]}"
                    session.execute(
                        models.product_categories.insert().values(
                            id=cat_id,
                            organization_id=organization_id,
                            name=grupo[:120],
                            display_order=len(category_map) + 1,
                            status="active",
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    category_map[grupo] = cat_id
                    summary["categories"] += 1

        created_products: list[dict[str, Any]] = []
        for row in sale_rows:
            clave = str(row["CLAVE"]).strip().replace("'", "")
            desc = str(row["DESCRIPCION"]).strip()
            grupo = (
                str(row["GRUPODEPRODUCTOS"]).strip()
                if pd.notna(row["GRUPODEPRODUCTOS"])
                else "GENERAL"
            )
            precio = float(row["PRECIO"]) if pd.notna(row["PRECIO"]) else 0.0
            price_cents = int(round(precio * 100))
            category_id = category_map.get(grupo)
            sku = f"PROD-{clave}"
            station = (
                "cocina"
                if any(
                    k in grupo
                    for k in [
                        "ENSALADA",
                        "SANDWICH",
                        "BAGUETTE",
                        "FOCACCIA",
                        "CUERNITO",
                        "QUESADILLA",
                        "COMBOS",
                        "OMELETTE",
                    ]
                )
                else "barra"
            )

            existing_p = session.execute(
                sa.select(models.products.c.id, models.products.c.status).where(
                    models.products.c.organization_id == organization_id,
                    models.products.c.sku == sku,
                )
            ).mappings().first()

            if existing_p:
                if existing_p["status"] == "archived":
                    raise BusinessError("product_archived", "La importación incluye un producto eliminado.")
                prod_id = str(existing_p["id"])
                session.execute(
                    sa.update(models.products)
                    .where(models.products.c.id == prod_id)
                    .values(
                        name=desc[:160],
                        category_id=category_id,
                        station=station,
                        status="active",
                        updated_at=now,
                    )
                )
            else:
                prod_id = f"prod-{clave.lower()}"
                session.execute(
                    models.products.insert().values(
                        id=prod_id,
                        organization_id=organization_id,
                        category_id=category_id,
                        name=desc[:160],
                        sku=sku[:64],
                        description=f"{desc} - {grupo}",
                        station=station,
                        status="active",
                        catalog_scope="organization",
                        source_branch_id=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                summary["products"] += 1

            existing_pv = session.execute(
                sa.select(models.price_versions.c.id).where(
                    models.price_versions.c.product_id == prod_id,
                    models.price_versions.c.organization_id == organization_id,
                    models.price_versions.c.valid_to.is_(None),
                )
            ).scalar_one_or_none()
            if not existing_pv:
                session.execute(
                    models.price_versions.insert().values(
                        id=_uid(),
                        organization_id=organization_id,
                        product_id=prod_id,
                        price_cents=price_cents,
                        currency="MXN",
                        valid_from=now,
                        valid_to=None,
                        created_at=now,
                    )
                )

            created_products.append({"id": prod_id, "name": desc, "category": grupo})

        mods_by_category: dict[str, list[dict[str, Any]]] = {}
        for row in modifier_rows:
            mod_group = str(row["GRUPODEPRODUCTOS"]).strip()
            desc = str(row["DESCRIPCION"]).strip()
            precio = float(row["PRECIO"]) if pd.notna(row["PRECIO"]) else 0.0
            price_cents = int(round(precio * 100))
            if mod_group not in mods_by_category:
                mods_by_category[mod_group] = []
            mods_by_category[mod_group].append({"name": desc, "price_cents": price_cents})

        category_modifier_links = {
            "JUGOS": ["EXTRA JUGOS", "INGREDIENTE EXTRA"],
            "LICUADOS": ["EXTRA LICUADOS", "INGREDIENTE EXTRA"],
            "SMOOTHIES Y EXTRACTOS": ["EXTRA LICUADOS", "INGREDIENTE EXTRA"],
            "AGUAS": ["EXTRA JUGOS", "INGREDIENTE EXTRA"],
            "BAGUETTES": [
                "TIPO DE PAN/TORTILLA",
                "MODIFICADOR DE QUESOS/FRITURAS",
                "INGREDIENTE EXTRA",
            ],
            "SANDWICH": [
                "TIPO DE PAN/TORTILLA",
                "MODIFICADOR DE QUESOS/FRITURAS",
                "INGREDIENTE EXTRA",
            ],
            "CUERNITO": ["MODIFICADOR DE QUESOS/FRITURAS", "INGREDIENTE EXTRA"],
            "FOCACCIA": [
                "TIPO DE PAN/TORTILLA",
                "MODIFICADOR DE QUESOS/FRITURAS",
                "INGREDIENTE EXTRA",
            ],
            "QUESADILLAS": [
                "TIPO DE PAN/TORTILLA",
                "MODIFICADOR DE QUESOS/FRITURAS",
                "INGREDIENTE EXTRA",
            ],
            "ENSALADAS": ["INGREDIENTE EXTRA", "MODIFICADOR DE QUESOS/FRITURAS"],
            "COMBOS": ["MEDIO PARA COMBOS", "INGREDIENTE EXTRA"],
            "KIWI BOX": ["MEDIO PARA COMBOS", "INGREDIENTE EXTRA"],
            "OMELETTE": [
                "TIPO DE PAN/TORTILLA",
                "MODIFICADOR DE QUESOS/FRITURAS",
                "INGREDIENTE EXTRA",
            ],
        }

        for prod in created_products:
            prod_id = prod["id"]
            prod_cat = prod["category"]
            applicable_mods = category_modifier_links.get(prod_cat, ["INGREDIENTE EXTRA"])

            for mod_cat_name in applicable_mods:
                if mod_cat_name not in mods_by_category:
                    continue

                options = mods_by_category[mod_cat_name]
                is_required = mod_cat_name == "TIPO DE PAN/TORTILLA"
                min_sel = 1 if is_required else 0
                max_sel = 1 if is_required else (5 if "EXTRA" in mod_cat_name else 3)

                existing_group = session.execute(
                    sa.select(models.modifier_groups.c.id).where(
                        models.modifier_groups.c.product_id == prod_id,
                        models.modifier_groups.c.name == mod_cat_name,
                    )
                ).scalar_one_or_none()

                if existing_group:
                    group_id = str(existing_group)
                else:
                    group_id = _uid()
                    session.execute(
                        models.modifier_groups.insert().values(
                            id=group_id,
                            organization_id=organization_id,
                            product_id=prod_id,
                            name=mod_cat_name[:120],
                            is_required=is_required,
                            minimum_selections=min_sel,
                            maximum_selections=max_sel,
                            station="cocina"
                            if "PAN" in mod_cat_name or "QUESO" in mod_cat_name
                            else "barra",
                            display_order=1 if is_required else 2,
                            status="active",
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    summary["modifier_groups"] += 1

                for opt_idx, opt in enumerate(options):
                    opt_name = opt["name"]
                    price_delta = opt["price_cents"]

                    existing_opt = session.execute(
                        sa.select(models.modifier_options.c.id).where(
                            models.modifier_options.c.group_id == group_id,
                            models.modifier_options.c.name == opt_name,
                        )
                    ).scalar_one_or_none()

                    if not existing_opt:
                        session.execute(
                            models.modifier_options.insert().values(
                                id=_uid(),
                                group_id=group_id,
                                name=opt_name[:120],
                                effect_type="addition" if price_delta > 0 else "choice",
                                price_delta_cents=price_delta,
                                affected_item_id=None,
                                replacement_item_id=None,
                                remove_quantity=Decimal("0"),
                                add_quantity=Decimal("1"),
                                inventory_effect=False,
                                kitchen_text=f"+ {opt_name}",
                                station=None,
                                display_order=opt_idx + 1,
                                status="active",
                                created_at=now,
                                updated_at=now,
                            )
                        )
                        summary["modifier_options"] += 1

    # -------------------------------------------------------------
    # 5. CUSTOMERS (CLIENTES.XLS)
    # -------------------------------------------------------------
    if import_customers:
        cli_path = os.path.join(excel_dir, "CLIENTES.XLS")
        if os.path.exists(cli_path):
            df_cli = pd.read_excel(cli_path, header=4).dropna(subset=["CLAVE", "NOMBRE"])
            if max_customers is not None:
                df_cli = df_cli.head(max_customers)

            for _, row in df_cli.iterrows():
                clave = str(row["CLAVE"]).strip()
                nombre = str(row["NOMBRE"]).strip()
                direccion = str(row["DIRECCION"]).strip() if pd.notna(row["DIRECCION"]) else ""

                clean_clave = clave.replace('"', "").replace(".", "").strip() or _uid()[:8]
                cust_id = f"cust-legacy-{clean_clave}"
                existing_c = session.execute(
                    sa.select(models.customers.c.id).where(
                        models.customers.c.organization_id == organization_id,
                        models.customers.c.id == cust_id,
                    )
                ).scalar_one_or_none()

                if not existing_c:
                    session.execute(
                        models.customers.insert().values(
                            id=cust_id,
                            organization_id=organization_id,
                            name=nombre[:160],
                            email=None,
                            customer_type="corporate" if "/" in nombre else "person",
                            customer_segment="oficina" if "/" in nombre else "general",
                            notes=f"Ref: {direccion}"
                            if direccion
                            else "Cliente frecuente sucursal",
                            status="active",
                            origin_branch_id=branch_id,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    summary["customers"] += 1

    session.commit()
    return summary
