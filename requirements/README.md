# Python 3.12 dependency locks

`python-api.lock` is the production API graph. `python-edge.lock` is the smaller gateway graph.
`python-dev.lock` adds tests, typing, audit and resolution tools. `python-bootstrap.lock` fixes the
installer/build tools. Each graph pins versions and hashes; platform markers cover Windows and
Linux. Runtime shared versions are constrained by the API lock when generating edge and dev.

From the repository root, in a fresh Python 3.12 environment:

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements/python-bootstrap.lock
python -m pip install --require-hashes --only-binary=:all: -r requirements/python-dev.lock
python -m pip check
python -m pip_audit --strict
python -m pip install --no-deps --no-build-isolation -e ./apps/api -e ./apps/edge-gateway
```

API Docker uses bootstrap + API locks, followed by an editable local project installation without
resolution or build isolation. Gateway installations use bootstrap + edge locks and the same local
installation flags. Do not use a ranged `pip install -e .` as the release dependency source.

Regenerate with uv 0.12.19 (included in the dev lock):

```sh
python -m uv pip compile apps/api/pyproject.toml --universal --python-version 3.12 --generate-hashes --no-annotate --no-header -o requirements/python-api.lock
python -m uv pip compile requirements/python-bootstrap.in --universal --python-version 3.12 --generate-hashes --no-annotate --no-header -o requirements/python-bootstrap.lock
python -m uv pip compile apps/edge-gateway/pyproject.toml -c requirements/python-api.lock --universal --python-version 3.12 --generate-hashes --no-annotate --no-header -o requirements/python-edge.lock
python -m uv pip compile apps/api/pyproject.toml apps/edge-gateway/pyproject.toml requirements/python-tools.in requirements/python-bootstrap.in --extra dev -c requirements/python-api.lock -c requirements/python-bootstrap.lock --universal --python-version 3.12 --generate-hashes --no-annotate --no-header -o requirements/python-dev.lock
```

Existing output pins are preferred. Use `--upgrade-package NAME` for reviewed updates, regenerate
dependants, inspect the diff, audit and execute affected tests. Do not add vulnerability ignores to
make a gate pass. CI audits the installed graph and pnpm lock on PR/manual runs; a separate weekly
workflow rechecks existing dependencies. Network/audit service failure leaves the gate unapproved.

`python scripts/python_locks.py` checks the complete resolution against current inputs in a
temporary directory; it returns nonzero on drift or resolver failure. `--write` updates all four
locks after successful resolution. CI uses check mode. Inputs remain the pyproject and `.in` files.

The locks fix Python packages, not the OS image or interpreter patch version. Linux installation
and Docker build remain release gates; a Windows installation alone does not prove them.

Frontend security constraints live in root `package.json` under `pnpm.overrides`: PostCSS,
nanoid 3, Browserslist and baseline-browser-mapping use patched releases. Browserslist is unified
on 4.29.2 to avoid conflicting peer resolutions. React Router DOM is >=7.18.2; Lucide React 0.468
declares React 19 compatibility. Frozen pnpm installation and all application builds validate the
resolved graph; overrides are version constraints, not audit suppressions.
