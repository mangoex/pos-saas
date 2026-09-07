"""Explicit local provisioner for a persisted platform superadmin flag."""
from __future__ import annotations

import argparse
from getpass import getpass

from restaurant_os.database import get_session_factory
from restaurant_os.superadmin.service import provision_platform_superadmin


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision a platform superadmin outside HTTP")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--confirm-email", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    email = args.email.strip().lower()
    if not args.apply or args.confirm_email.strip().lower() != email:
        raise SystemExit("platform_superadmin_confirmation_required")
    password = getpass("Platform administrator password: ")
    confirmation = getpass("Confirm platform administrator password: ")
    if password != confirmation:
        raise SystemExit("platform_superadmin_password_mismatch")

    with get_session_factory()() as session:
        result = provision_platform_superadmin(
            session,
            email=email,
            password=password,
            display_name=args.display_name,
        )
    print(f"platform_superadmin_provisioned id={result['id']} created={result['created']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
