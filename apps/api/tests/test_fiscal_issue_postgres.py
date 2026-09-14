# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-fiscal-issue-postgres-synthetic-v1
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.invoicing.service import InvoicingService
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session, sessionmaker

API_DIR = Path(__file__).resolve().parents[1]


def _migrate(schema: str, command: str) -> str:
    url = os.environ["SAAS_TEST_POSTGRES_URL"]
    scoped = (
        sa.engine.make_url(url)
        .set(query={"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *command.split()],
        cwd=API_DIR,
        env={**os.environ, "RESTAURANTOS_DATABASE_URL": scoped},
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return scoped


def _order(session: Session, org: str, branch: str, order_id: str) -> None:
    session.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=org,
            branch_id=branch,
            folio=f"PG-{order_id}",
            order_type="dine_in",
            channel="UBER_EATS",
            status="completed",
            total_cents=1000,
            currency="MXN",
            payment_method_intent="cash",
            version=1,
            created_at=datetime.now(timezone.utc),
        )
    )


def test_postgres_overlapping_fiscal_claims_are_atomic_and_survive_reupgrade() -> None:
    url = os.environ["SAAS_TEST_POSTGRES_URL"]
    schema = f"saas_fiscal_claim_{uuid4().hex}"
    admin = sa.create_engine(url)
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    scoped = _migrate(schema, "upgrade head")
    engine = sa.create_engine(scoped)
    factory = sessionmaker(bind=engine)
    try:
        with factory() as session:
            tenant = signup_tenant(
                session,
                {
                    "business_name": "Fiscal PG",
                    "owner_name": "Owner",
                    "email": "fiscal-pg@example.test",
                    "password": "synthetic-pg-password",
                    "business_type": "blank",
                },
            )
            org, branch, actor = (
                str(tenant["organization"]["id"]),
                str(tenant["branch"]["id"]),
                str(tenant["user"]["id"]),
            )
            for order_id in ("order-a", "order-b", "order-c"):
                _order(session, org, branch, order_id)
            InvoicingService().save_config(
                session,
                org,
                {"is_enabled": True, "environment": "sandbox", "api_key": "sk_test_live_fake"},
            )
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def claim(ids: list[str]) -> None:
            with factory() as session:
                barrier.wait(timeout=15)
                try:
                    InvoicingService()._prepare_issue_command(
                        session,
                        organization_id=org,
                        branch_id=branch,
                        order_ids=ids,
                        receptor={},
                        invoice_draft={},
                        actor_user_id=actor,
                    )
                    outcomes.append("inflight")
                except ValueError:
                    outcomes.append("blocked")

        threads = [
            threading.Thread(target=claim, args=(ids,))
            for ids in (["order-a", "order-b"], ["order-b", "order-c"])
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert sorted(outcomes) == ["blocked", "inflight"]
        with factory() as session:
            command = session.execute(sa.select(models.fiscal_commands)).mappings().one()
            assert command["status"] == "inflight"
            assert (
                session.scalar(
                    sa.select(sa.func.count()).select_from(models.fiscal_command_order_claims)
                )
                == 2
            )
            claimed_orders = set(command["order_ids"])
            overlapping = (
                ["order-b", "order-c"]
                if claimed_orders == {"order-a", "order-b"}
                else ["order-a", "order-b"]
            )
            session.execute(
                models.fiscal_commands.update()
                .where(models.fiscal_commands.c.id == command["id"])
                .values(status="confirmed")
            )
            session.commit()
            with pytest.raises(ValueError, match="ya fueron facturados"):
                InvoicingService()._prepare_issue_command(
                    session,
                    organization_id=org,
                    branch_id=branch,
                    order_ids=overlapping,
                    receptor={},
                    invoice_draft={},
                    actor_user_id=actor,
                )
            receipt = InvoicingService()._prepare_resource_command(
                session,
                organization_id=org,
                branch_id=branch,
                operation="receipt",
                target_id="order-a",
                snapshot={},
                actor_user_id=actor,
            )
            with pytest.raises(ValueError, match="reconciliación"):
                InvoicingService()._prepare_resource_command(
                    session,
                    organization_id=org,
                    branch_id=branch,
                    operation="receipt",
                    target_id="order-a",
                    snapshot={},
                    actor_user_id=actor,
                )
            assert receipt["status"] == "inflight"

        for operation, target_id, snapshot in (
            ("receipt", "order-c", {}),
            ("cancel", "invoice-a", {"motive": "01", "substitution_uuid": None}),
        ):
            resource_barrier = threading.Barrier(2)
            resource_outcomes: list[str] = []

            def claim_resource(
                barrier: threading.Barrier = resource_barrier,
                command_operation: str = operation,
                command_target_id: str = target_id,
                command_snapshot: dict[str, object] = snapshot,
                outcomes: list[str] = resource_outcomes,
            ) -> None:
                with factory() as session:
                    barrier.wait(timeout=15)
                    try:
                        InvoicingService()._prepare_resource_command(
                            session,
                            organization_id=org,
                            branch_id=branch,
                            operation=command_operation,
                            target_id=command_target_id,
                            snapshot=command_snapshot,
                            actor_user_id=actor,
                        )
                        outcomes.append("inflight")
                    except ValueError:
                        outcomes.append("blocked")

            threads = [threading.Thread(target=claim_resource) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
                assert not thread.is_alive()
            assert sorted(resource_outcomes) == ["blocked", "inflight"]
            with factory() as session:
                assert (
                    session.scalar(
                        sa.select(sa.func.count())
                        .select_from(models.fiscal_command_resource_claims)
                        .where(
                            models.fiscal_command_resource_claims.c.organization_id == org,
                            models.fiscal_command_resource_claims.c.operation == operation,
                            models.fiscal_command_resource_claims.c.target_id == target_id,
                        )
                    )
                    == 1
                )
        _migrate(schema, "downgrade 0073_pos_handoff_support_context")
        with factory() as session:
            assert (
                session.scalar(
                    sa.select(sa.func.count()).select_from(models.fiscal_command_resource_claims)
                )
                == 3
            )
        _migrate(schema, "upgrade head")
        with factory() as session:
            assert (
                session.scalar(
                    sa.select(sa.func.count()).select_from(models.fiscal_command_order_claims)
                )
                == 2
            )
            assert (
                session.scalar(
                    sa.select(sa.func.count()).select_from(models.fiscal_command_resource_claims)
                )
                == 3
            )
            drafts = list(
                session.execute(sa.select(models.fiscal_commands.c.invoice_draft)).scalars()
            )
            assert {} in drafts
            assert {"motive": "01", "substitution_uuid": None} in drafts
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()
