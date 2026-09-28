"""Regenerate Python 3.12 locks, or verify that committed locks match their inputs."""

import argparse
import importlib.metadata
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKS = ROOT / "requirements"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Update locks; default only checks")
    args = parser.parse_args()
    if importlib.metadata.version("uv") != "0.12.19":
        raise RuntimeError("Use uv 0.12.19 from requirements/python-dev.lock")
    with tempfile.TemporaryDirectory(prefix="restaurantos-locks-") as directory:
        staging = Path(directory)
        specs = [
            ("api", ["apps/api/pyproject.toml"], []),
            ("bootstrap", ["requirements/python-bootstrap.in"], []),
            ("edge", ["apps/edge-gateway/pyproject.toml"], ["api"]),
            (
                "dev",
                [
                    "apps/api/pyproject.toml",
                    "apps/edge-gateway/pyproject.toml",
                    "requirements/python-tools.in",
                    "requirements/python-bootstrap.in",
                    "--extra",
                    "dev",
                ],
                ["api", "bootstrap"],
            ),
        ]
        changed = []
        for name, inputs, constraints in specs:
            filename = f"python-{name}.lock"
            target = staging / filename
            original = LOCKS / filename
            if original.exists():
                shutil.copyfile(original, target)
            command = [
                sys.executable,
                "-m",
                "uv",
                "pip",
                "compile",
                *inputs,
                "--universal",
                "--python-version",
                "3.12",
                "--generate-hashes",
                "--no-annotate",
                "--no-header",
                "--quiet",
                "--output-file",
                str(target),
            ]
            for constraint in constraints:
                command.extend(["--constraint", str(staging / f"python-{constraint}.lock")])
            subprocess.run(command, cwd=ROOT, check=True)
            if not original.exists() or original.read_text() != target.read_text():
                changed.append(filename)
        if args.write:
            for filename in changed:
                shutil.copyfile(staging / filename, LOCKS / filename)
        elif changed:
            print("Stale Python locks: " + ", ".join(changed), file=sys.stderr)
            return 1
    print("Python locks written" if args.write else "Python locks match declared inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
