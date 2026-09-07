import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_required_monorepo_paths_exist() -> None:
    required_paths = [
        "apps/api",
        "apps/worker",
        "apps/edge-gateway",
        "apps/admin-web",
        "apps/pos-web",
        "apps/kds-web",
        "packages/contracts",
        "packages/domain-types",
        "packages/test-fixtures",
        "infra/docker",
        "infra/easypanel",
        "docs",
        "tests/architecture",
    ]

    missing = [path for path in required_paths if not (ROOT / path).exists()]

    assert missing == []


def test_contract_schemas_exist() -> None:
    schemas = [
        "health.schema.json",
        "command-envelope.schema.json",
        "event-envelope.schema.json",
        "purchase-command.schema.json",
    ]

    missing = [
        schema
        for schema in schemas
        if not (ROOT / "packages" / "contracts" / "schemas" / schema).exists()
    ]

    assert missing == []


def test_docker_entrypoints_have_explicit_startup_contracts() -> None:
    root_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    api_dockerfile = (ROOT / "infra/docker/api.Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "infra/docker/entrypoint.sh").read_text(encoding="utf-8")

    assert '"uvicorn", "restaurant_os.main:app"' in root_dockerfile
    assert "alembic upgrade head" not in root_dockerfile
    assert "COPY infra/docker/entrypoint.sh /app/entrypoint.sh" in api_dockerfile
    assert 'CMD ["/app/entrypoint.sh"]' in api_dockerfile
    assert "alembic upgrade head" in entrypoint
    assert "exec uvicorn restaurant_os.main:app" in entrypoint
    assert "alembic upgrade head && uvicorn" not in entrypoint


def test_web_process_has_no_runtime_migration_path() -> None:
    main = (ROOT / "apps/api/restaurant_os/main.py").read_text(encoding="utf-8")
    config = (ROOT / "apps/api/restaurant_os/config.py").read_text(encoding="utf-8")

    assert "_run_auto_migrations" not in main
    assert "command.upgrade" not in main
    assert "auto_migrate" not in main
    assert "auto_migrate" not in config


def test_legacy_operational_platform_shell_is_absent() -> None:
    main = (ROOT / "apps/api/restaurant_os/main.py").read_text(encoding="utf-8")

    assert not (ROOT / "apps/api/restaurant_os/platform_shell.py").exists()
    assert "platform_shell" not in main


def test_ci_has_one_pinned_high_severity_dependency_review_gate() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "dependency-review:" in workflow
    assert (
        "actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294"
        in workflow
    )
    assert "fail-on-severity: high" in workflow


def test_legacy_public_order_writer_is_absent_and_route_is_fail_closed() -> None:
    operations_path = ROOT / "apps/api/restaurant_os/operations.py"
    api_path = ROOT / "apps/api/restaurant_os/api.py"
    operations_tree = ast.parse(operations_path.read_text(encoding="utf-8"))
    api_tree = ast.parse(api_path.read_text(encoding="utf-8"))

    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "create_public_online_order"
        for node in ast.walk(operations_tree)
    )

    endpoint = next(
        node
        for node in api_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "public_create_order"
    )
    assert endpoint.args.args == []
    assert len(endpoint.body) == 1
    statement = endpoint.body[0]
    assert isinstance(statement, ast.Raise)
    assert isinstance(statement.exc, ast.Call)
    assert isinstance(statement.exc.func, ast.Name)
    assert statement.exc.func.id == "_public_order_error"
    assert [ast.literal_eval(argument) for argument in statement.exc.args] == [
        "public_order_unavailable",
        503,
    ]
