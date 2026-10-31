import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.enums.user import UserRoleEnum
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.schemas.admin_user import (
    AdminUserListQuery,
    AdminUserListResponse,
    CreateAdminUserRequest,
)
from app.services.admin_user import AdminUserService
from app.services.auth import AuthService
from scripts.create_superadmin import validate_email, validate_phone


def run_coroutine(coro):
    stack = [coro]
    val = None
    while stack:
        try:
            res = stack[-1].send(val)
            stack.append(res)
            val = None
        except StopIteration as e:
            stack.pop()
            val = e.value
    return val


class AdminUsersTests(unittest.TestCase):
    def test_admin_users_query_validation(self):
        query = AdminUserListQuery(page=1, page_size=20, search="test", role="admin")
        self.assertEqual(query.page, 1)
        self.assertEqual(query.page_size, 20)
        self.assertEqual(query.role, "admin")

        with self.assertRaises(ValidationError):
            AdminUserListQuery(page=0)

        with self.assertRaises(ValidationError):
            AdminUserListQuery(page_size=101)

    def test_admin_user_service_get_directory_and_stats(self):
        admin = User(
            id=uuid4(),
            name="Arun Patel",
            email="arun@example.com",
            phone_number="9820121010",
            reference_id="CNX-REF-ARUN01",
            role=UserRoleEnum.SUPER_ADMIN,
            is_verified=True,
            is_active=True,
            title="Head of Lending Tech",
        )
        staff = User(
            id=uuid4(),
            name="Devika Shah",
            email="devika@example.com",
            phone_number="9845033210",
            reference_id="CNX-REF-DEVI02",
            role=UserRoleEnum.ADMIN,
            is_verified=True,
            is_active=True,
            title="Risk Manager",
        )
        borrower = User(
            id=uuid4(),
            name="Amit Verma",
            email="amit@example.com",
            phone_number="9711234567",
            reference_id="CNX-REF-AMIT03",
            role=UserRoleEnum.USER,
            is_verified=False,
            is_active=False,
        )

        fake_repo = _FakeAdminUserRepository(users=[admin, staff, borrower])
        service = AdminUserService(session=_FakeSession(), repository=fake_repo)

        response: AdminUserListResponse = run_coroutine(
            service.get_users_directory(AdminUserListQuery(page=1, page_size=10))
        )

        self.assertEqual(response.total, 3)
        self.assertEqual(len(response.items), 3)

        # Check stats
        self.assertEqual(response.stats.total_users, 3)
        self.assertEqual(response.stats.active_staff, 2)
        self.assertEqual(response.stats.verified_identities, 2)
        self.assertEqual(response.stats.pending_kyc, 1)

        # Check item formatting
        first_item = next(i for i in response.items if i.email == "arun@example.com")
        self.assertEqual(first_item.avatar_initials, "AP")
        self.assertEqual(first_item.title, "Head of Lending Tech")
        self.assertEqual(first_item.account_status, "active")
        self.assertEqual(first_item.verification_status, "verified")

        borrower_item = next(i for i in response.items if i.email == "amit@example.com")
        self.assertEqual(borrower_item.avatar_initials, "AV")
        self.assertEqual(borrower_item.title, "Portal Borrower")  # default fallback
        self.assertEqual(borrower_item.account_status, "inactive")
        self.assertEqual(borrower_item.verification_status, "unverified")

    def test_admin_user_service_create_user(self):
        actor = User(
            id=uuid4(),
            name="Super Admin",
            email="super@example.com",
            phone_number="9999999999",
            reference_id="CNX-REF-SUPER",
            role=UserRoleEnum.SUPER_ADMIN,
        )
        fake_repo = _FakeAdminUserRepository(users=[actor])
        service = AdminUserService(session=_FakeSession(), repository=fake_repo)

        # Successfully create user with auto-generated temp password
        req = CreateAdminUserRequest(
            name="Kavita Lakhani",
            email="kavita@crednexa.com",
            phone_number="9889810020",
            role=UserRoleEnum.ADMIN,
            account_status="active",
            title="Credit Risk Auditor",
        )
        created = run_coroutine(service.create_user(payload=req, actor=actor))
        self.assertEqual(created.name, "Kavita Lakhani")
        self.assertEqual(created.email, "kavita@crednexa.com")
        self.assertEqual(created.avatar_initials, "KL")
        self.assertEqual(created.title, "Credit Risk Auditor")
        self.assertEqual(created.account_status, "active")
        self.assertEqual(created.verification_status, "verified")
        self.assertIsNotNone(created.temporary_password)
        self.assertGreaterEqual(len(created.temporary_password), 8)

        # Conflict on duplicate email
        with self.assertRaises(ConflictError):
            run_coroutine(service.create_user(payload=req, actor=actor))

    def test_privilege_escalation_prevented(self):
        admin_actor = User(
            id=uuid4(),
            name="Regular Admin",
            email="admin@example.com",
            phone_number="9999999990",
            reference_id="CNX-REF-ADM01",
            role=UserRoleEnum.ADMIN,
        )
        fake_repo = _FakeAdminUserRepository(users=[admin_actor])
        service = AdminUserService(session=_FakeSession(), repository=fake_repo)

        # Regular Admin attempting to create SUPER_ADMIN must be blocked with ForbiddenError
        req = CreateAdminUserRequest(
            name="Sneaky Admin",
            email="sneaky@crednexa.com",
            phone_number="9889810021",
            role=UserRoleEnum.SUPER_ADMIN,
            account_status="active",
        )
        with self.assertRaises(ForbiddenError):
            run_coroutine(service.create_user(payload=req, actor=admin_actor))

    def test_create_user_with_explicit_temporary_password(self):
        actor = User(
            id=uuid4(),
            name="Super Admin",
            email="super@example.com",
            phone_number="9999999999",
            reference_id="CNX-REF-SUPER",
            role=UserRoleEnum.SUPER_ADMIN,
        )
        fake_repo = _FakeAdminUserRepository(users=[actor])
        service = AdminUserService(session=_FakeSession(), repository=fake_repo)

        req = CreateAdminUserRequest(
            name="Explicit Staff",
            email="explicit@crednexa.com",
            phone_number="9889810022",
            role=UserRoleEnum.ADMIN,
            account_status="active",
            temporary_password="StaffPassword123!",
        )
        created = run_coroutine(service.create_user(payload=req, actor=actor))
        self.assertEqual(created.temporary_password, "StaffPassword123!")
        self.assertEqual(created.verification_status, "verified")

    def test_prevent_regular_admin_from_deactivating_superadmin(self):
        admin_actor = User(
            id=uuid4(),
            name="Regular Admin",
            email="admin@example.com",
            phone_number="9999999990",
            reference_id="CNX-REF-ADM01",
            role=UserRoleEnum.ADMIN,
        )
        super_target = User(
            id=uuid4(),
            name="Boss",
            email="boss@crednexa.com",
            phone_number="9999999995",
            reference_id="CNX-REF-BOSS",
            role=UserRoleEnum.SUPER_ADMIN,
            is_active=True,
        )
        fake_repo = _FakeAdminUserRepository(users=[admin_actor, super_target])
        service = AdminUserService(session=_FakeSession(), repository=fake_repo)

        with self.assertRaises(ForbiddenError):
            run_coroutine(service.toggle_user_status(identifier=str(super_target.id), actor=admin_actor))

    def test_prevent_deactivating_last_active_superadmin(self):
        super_actor = User(
            id=uuid4(),
            name="Sole Boss",
            email="boss@crednexa.com",
            phone_number="9999999995",
            reference_id="CNX-REF-BOSS",
            role=UserRoleEnum.SUPER_ADMIN,
            is_active=True,
        )
        fake_repo = _FakeAdminUserRepository(users=[super_actor])
        service = AdminUserService(session=_FakeSession(), repository=fake_repo)

        with self.assertRaises(ConflictError):
            run_coroutine(service.toggle_user_status(identifier=str(super_actor.id), actor=super_actor))

    def test_update_user_role(self):
        super_actor = User(
            id=uuid4(),
            name="Super Admin",
            email="super@example.com",
            phone_number="9999999999",
            reference_id="CNX-REF-SUPER",
            role=UserRoleEnum.SUPER_ADMIN,
            is_active=True,
        )
        regular_admin = User(
            id=uuid4(),
            name="Regular Admin",
            email="admin@example.com",
            phone_number="9999999990",
            reference_id="CNX-REF-ADM01",
            role=UserRoleEnum.ADMIN,
            is_active=True,
        )
        target_user = User(
            id=uuid4(),
            name="Target User",
            email="target@example.com",
            phone_number="9999999998",
            reference_id="CNX-REF-TARGET",
            role=UserRoleEnum.USER,
            is_active=True,
        )
        fake_repo = _FakeAdminUserRepository(users=[super_actor, regular_admin, target_user])
        service = AdminUserService(session=_FakeSession(), repository=fake_repo)

        # Super Admin promotes user to ADMIN
        promoted = run_coroutine(
            service.update_user_role(
                identifier=str(target_user.id),
                new_role=UserRoleEnum.ADMIN,
                actor=super_actor,
            )
        )
        self.assertEqual(promoted.role, UserRoleEnum.ADMIN)

        # Regular Admin cannot update roles
        with self.assertRaises(ForbiddenError):
            run_coroutine(
                service.update_user_role(
                    identifier=str(target_user.id),
                    new_role=UserRoleEnum.SUPER_ADMIN,
                    actor=regular_admin,
                )
            )

        # Cannot demote sole remaining Super Admin
        with self.assertRaises(ConflictError):
            run_coroutine(
                service.update_user_role(
                    identifier=str(super_actor.id),
                    new_role=UserRoleEnum.ADMIN,
                    actor=super_actor,
                )
            )

    def test_create_superadmin_script_validators(self):
        self.assertTrue(validate_email("admin@crednexa.com"))
        self.assertFalse(validate_email("invalid-email"))
        self.assertTrue(validate_phone("9820121010"))
        self.assertTrue(validate_phone("+91 98201 21010"))
        self.assertFalse(validate_phone("1234567890"))  # Doesn't start with 6-9
        self.assertFalse(validate_phone("98201"))       # Too short

    def test_admin_user_service_toggle_status_and_revocation(self):
        actor = User(
            id=uuid4(),
            name="Admin",
            email="admin@example.com",
            phone_number="9999999991",
            reference_id="CNX-REF-ADM",
            role=UserRoleEnum.ADMIN,
        )
        target = User(
            id=uuid4(),
            name="Staff User",
            email="staff@example.com",
            phone_number="9999999992",
            reference_id="CNX-REF-STAFF",
            role=UserRoleEnum.ADMIN,
            is_active=True,
        )
        session = _FakeSession()
        fake_repo = _FakeAdminUserRepository(users=[actor, target])
        service = AdminUserService(session=session, repository=fake_repo)

        # Deactivate user
        updated = run_coroutine(
            service.toggle_user_status(identifier=str(target.id), actor=actor)
        )
        self.assertEqual(updated.account_status, "inactive")
        self.assertFalse(target.is_active)
        self.assertTrue(session.executed_revocation)

        # Non-existent user raises NotFoundError
        with self.assertRaises(NotFoundError):
            run_coroutine(
                service.toggle_user_status(identifier=str(uuid4()), actor=actor)
            )

    def test_inactive_user_cannot_login(self):
        password = "SecurePassword123!"
        user = User(
            id=uuid4(),
            name="Inactive User",
            email="inactive@example.com",
            phone_number="9876543210",
            reference_id="CNX-REF-INACTIVE",
            password_hash=hash_password(password=password),
            is_verified=True,
            is_active=False,
        )

        class _MockUserRepo:
            def __init__(self, user):
                self.user = user

            async def get_by_email(self, *, email):
                return self.user if email == self.user.email else None

        auth_service = AuthService.__new__(AuthService)
        auth_service.session = _FakeSession()
        auth_service.user_repository = _MockUserRepo(user)

        with self.assertRaises(ForbiddenError):
            run_coroutine(
                auth_service.login_user(email="inactive@example.com", password=password)
            )


class _FakeSession:
    def __init__(self):
        self.executed_revocation = False

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def refresh(self, obj):
        return None

    async def execute(self, statement):
        self.executed_revocation = True
        return None


class _FakeAdminUserRepository:
    def __init__(self, users: list[User]):
        self.users = {u.id: u for u in users}

    async def get_users_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        role: str | None = None,
        verification: str | None = None,
        status: str | None = None,
    ):
        filtered = list(self.users.values())
        if search:
            s = search.lower()
            filtered = [
                u for u in filtered
                if s in u.name.lower() or s in u.email.lower() or s in u.phone_number.lower()
            ]
        if role and role != "all":
            filtered = [u for u in filtered if u.role == role]
        if verification == "verified":
            filtered = [u for u in filtered if u.is_verified]
        elif verification == "unverified":
            filtered = [u for u in filtered if not u.is_verified]
        if status == "active":
            filtered = [u for u in filtered if u.is_active]
        elif status == "inactive":
            filtered = [u for u in filtered if not u.is_active]

        total = len(filtered)
        offset = (page - 1) * page_size
        rows = [(u, 0) for u in filtered[offset : offset + page_size]]
        return rows, total

    async def get_stats(self):
        users = list(self.users.values())
        total_users = len(users)
        active_staff = len([
            u for u in users
            if u.role in [UserRoleEnum.ADMIN, UserRoleEnum.SUPER_ADMIN] and u.is_active
        ])
        verified_identities = len([u for u in users if u.is_verified])
        pending_kyc = len([u for u in users if not u.is_verified or not u.is_active])
        return {
            "total_users": total_users,
            "active_staff": active_staff,
            "verified_identities": verified_identities,
            "pending_kyc": pending_kyc,
        }

    async def count_active_super_admins(self) -> int:
        return len([
            u for u in self.users.values()
            if u.role == UserRoleEnum.SUPER_ADMIN and u.is_active
        ])

    async def update_role(self, user: User, role: UserRoleEnum) -> User:
        user.role = role
        return user

    async def get_by_id(self, user_id):
        return self.users.get(user_id)

    async def get_by_id_or_ref(self, identifier):
        for u in self.users.values():
            if str(u.id) == identifier or u.reference_id == identifier:
                return u
        return None

    async def get_by_email(self, email):
        for u in self.users.values():
            if u.email == email:
                return u
        return None

    async def get_by_phone(self, phone):
        for u in self.users.values():
            if u.phone_number == phone:
                return u
        return None

    async def create(self, user):
        self.users[user.id] = user
        return user


if __name__ == "__main__":
    unittest.main()
