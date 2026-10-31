import argparse
import asyncio
import getpass
import os
import re
import sys
from uuid import uuid4

# Ensure parent directory is in sys.path so app modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.core.reference_id import generate_reference_id
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.enums.user import UserRoleEnum
from app.models.user import User


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email.strip()))


def validate_phone(phone: str) -> bool:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return len(digits) == 10 and digits[0] in "6789"


async def async_create_superadmin(
    *,
    name: str,
    email: str,
    phone: str,
    password: str,
    title: str = "System Administrator",
) -> None:
    email = email.strip().lower()
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    phone = digits
    name = name.strip()
    title = title.strip() or "System Administrator"

    if not validate_email(email):
        print(f"Error: Invalid email format '{email}'.", file=sys.stderr)
        sys.exit(1)

    if not validate_phone(phone):
        print(
            f"Error: Phone number must be a 10-digit Indian number starting with 6, 7, 8, or 9 (got '{phone}').",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(password) < 8:
        print("Error: Password must be at least 8 characters long.", file=sys.stderr)
        sys.exit(1)

    async with AsyncSessionLocal() as session:
        # Check existing email
        existing_email = await session.scalar(
            select(User).where(User.email == email)
        )
        if existing_email:
            print(f"Error: A user with email '{email}' already exists.", file=sys.stderr)
            sys.exit(1)

        # Check existing phone
        existing_phone = await session.scalar(
            select(User).where(User.phone_number == phone)
        )
        if existing_phone:
            print(f"Error: A user with phone number '{phone}' already exists.", file=sys.stderr)
            sys.exit(1)

        user_id = uuid4()
        user = User(
            id=user_id,
            name=name,
            email=email,
            phone_number=phone,
            reference_id=generate_reference_id(user_id=user_id),
            password_hash=hash_password(password=password),
            role=UserRoleEnum.SUPER_ADMIN,
            is_verified=True,
            is_active=True,
            title=title,
        )

        session.add(user)
        await session.commit()
        await session.refresh(user)

        print("\n" + "=" * 50)
        print(" Super Admin created successfully!")
        print("=" * 50)
        print(f" Name:         {user.name}")
        print(f" Email:        {user.email}")
        print(f" Phone:        {user.phone_number}")
        print(f" Role:         {user.role.value}")
        print(f" Title:        {user.title}")
        print(f" Reference ID: {user.reference_id}")
        print(f" Verified:     {user.is_verified}")
        print(f" Active:       {user.is_active}")
        print("=" * 50)
        print("You can now log in at the admin portal with these credentials.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap or create a Super Admin user for CredNexa."
    )
    parser.add_argument("--name", help="Full name of the super administrator")
    parser.add_argument("--email", help="Unique business email address")
    parser.add_argument("--phone", help="10-digit Indian phone number (e.g. 9820121010)")
    parser.add_argument("--password", help="Secure password (minimum 8 characters)")
    parser.add_argument(
        "--title",
        default="System Administrator",
        help="Designation / Title (default: 'System Administrator')",
    )

    args = parser.parse_args()

    name = args.name
    email = args.email
    phone = args.phone
    password = args.password
    title = args.title

    # Interactive prompts if required fields are missing
    if not name:
        name = input("Enter Full Name: ").strip()
    if not email:
        email = input("Enter Business Email: ").strip()
    if not phone:
        phone = input("Enter Phone Number (10 digits): ").strip()
    if not title:
        title = input("Enter Designation / Title [System Administrator]: ").strip() or "System Administrator"

    if not password:
        while True:
            pwd1 = getpass.getpass("Enter Password (min 8 chars): ")
            if len(pwd1) < 8:
                print("Password must be at least 8 characters. Please try again.")
                continue
            pwd2 = getpass.getpass("Confirm Password: ")
            if pwd1 != pwd2:
                print("Passwords do not match. Please try again.")
                continue
            password = pwd1
            break

    asyncio.run(
        async_create_superadmin(
            name=name,
            email=email,
            phone=phone,
            password=password,
            title=title,
        )
    )


if __name__ == "__main__":
    main()
