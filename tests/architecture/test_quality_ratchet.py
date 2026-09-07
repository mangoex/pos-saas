# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-quality-ratchet-synthetic-v1
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.quality_ratchet import Finding, analyze_diff, format_findings

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quality_ratchet.py"
TYPE_IGNORE = "type:" + " ignore"
NOQA = "no" + "qa"
TS_IGNORE = "@ts-" + "ignore"
ESLINT_DISABLE = "eslint-" + "disable"
PYTEST_SKIP = "pytest.mark." + "skip"
TEST_SKIP = "test." + "skip"


def test_tc193_detects_new_python_suppressions_and_disabled_tests() -> None:
    diff = f"""\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,0 +2,3 @@
+value = source  # {TYPE_IGNORE}[arg-type]
+@{PYTEST_SKIP}(reason="later")
+clean = 1
"""

    assert analyze_diff(diff) == [
        Finding("app.py", 2, "python_type_suppression"),
        Finding("app.py", 3, "test_disabled"),
    ]


def test_tc193_detects_typescript_lint_and_test_suppression() -> None:
    diff = f"""\
diff --git a/ui.ts b/ui.ts
--- a/ui.ts
+++ b/ui.ts
@@ -7,0 +8,4 @@
+// {TS_IGNORE}
+// {ESLINT_DISABLE}-next-line no-explicit-any
+{TEST_SKIP}("later", () => {{}})
+const enabled = true
"""

    assert analyze_diff(diff) == [
        Finding("ui.ts", 8, "typescript_type_suppression"),
        Finding("ui.ts", 9, "lint_suppression"),
        Finding("ui.ts", 10, "test_disabled"),
    ]


def test_tc193_ignores_historical_context_and_unsupported_files() -> None:
    diff = f"""\
diff --git a/legacy.py b/legacy.py
--- a/legacy.py
+++ b/legacy.py
@@ -1,2 +1,3 @@
 value = source  # {NOQA}: F401
+clean = 2
diff --git a/notes.md b/notes.md
--- a/notes.md
+++ b/notes.md
@@ -1,0 +2 @@
+Example: // {TS_IGNORE}
"""

    assert analyze_diff(diff) == []


def test_tc193_accepts_only_a_local_nonempty_exception_reason() -> None:
    diff = f"""\
diff --git a/bootstrap.py b/bootstrap.py
--- a/bootstrap.py
+++ b/bootstrap.py
@@ -1,0 +2,2 @@
+from app import api  # {NOQA}: E402  # quality-ratchet: allow -- bootstrap must precede app import
+from app import db  # {NOQA}: E402  # quality-ratchet: allow --
"""

    assert analyze_diff(diff) == [
        Finding("bootstrap.py", 3, "lint_suppression"),
    ]


def test_tc193_output_is_deterministic_and_does_not_repeat_source() -> None:
    secret_marker = "do-not-print-this-source"
    diff = f"""\
diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -0,0 +1 @@
+token = "{secret_marker}"  # {NOQA}: S105
"""

    first = format_findings(analyze_diff(diff))
    second = format_findings(analyze_diff(diff))

    assert first == second == ["config.py:1: lint_suppression"]
    assert secret_marker not in "\n".join(first)


def test_tc193_ratchet_sources_do_not_block_their_own_addition() -> None:
    for relative in (
        "scripts/quality_ratchet.py",
        "tests/architecture/test_quality_ratchet.py",
    ):
        content = (ROOT / relative).read_text(encoding="utf-8").splitlines()
        diff = "\n".join(
            [
                f"diff --git a/{relative} b/{relative}",
                "--- /dev/null",
                f"+++ b/{relative}",
                f"@@ -0,0 +1,{len(content)} @@",
                *(f"+{line}" for line in content),
            ]
        )
        assert analyze_diff(diff) == []


def test_tc193_cli_fails_closed_when_base_cannot_be_resolved(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(tmp_path),
            "--base",
            "missing-base",
            "--head",
            "HEAD",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "quality-ratchet: unable to inspect diff missing-base...HEAD\n"


def test_tc193_cli_compares_commits_without_inheriting_baseline_debt(
    tmp_path: Path,
) -> None:
    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    git("init", "-q")
    git("config", "user.email", "quality-ratchet@example.test")
    git("config", "user.name", "Quality Ratchet Test")
    source = tmp_path / "app.py"
    source.write_text(f"legacy = source  # {TYPE_IGNORE}[assignment]\n")
    git("add", "app.py")
    git("commit", "-qm", "baseline")
    base = git("rev-parse", "HEAD").stdout.strip()

    source.write_text(
        source.read_text() + f"new_value = source  # {NOQA}: F401\n"
    )
    git("add", "app.py")
    git("commit", "-qm", "add suppression")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(tmp_path),
            "--base",
            base,
            "--head",
            "HEAD",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert result.stdout == "app.py:2: lint_suppression\n"
    assert result.stderr == ""
