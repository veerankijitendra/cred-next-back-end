import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from pydantic import ValidationError

from app.core.auth import require_admin
from app.core.constants import ApplicationType, LeadStatus, LoanType
from app.core.exceptions import ForbiddenError
from app.enums.user import UserRoleEnum
from app.models.lead import Lead
from app.models.user import User
from app.schemas.admin_lead import AdminLeadListQuery, AdminLeadListResponse
from app.services.lead import LeadService


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


class AdminLeadsTests(unittest.TestCase):
    def test_require_admin_allows_admin_and_super_admin(self):
        admin_user = User(
            id=uuid4(),
            name="Admin User",
            email="admin@example.com",
            phone_number="9876543210",
            reference_id="CNX-REF-ADMIN",
            role=UserRoleEnum.ADMIN,
            is_verified=True,
        )
        super_admin_user = User(
            id=uuid4(),
            name="Super Admin",
            email="superadmin@example.com",
            phone_number="9876543211",
            reference_id="CNX-REF-SUPER",
            role=UserRoleEnum.SUPER_ADMIN,
            is_verified=True,
        )

        res1 = run_coroutine(require_admin(current_user=admin_user))
        self.assertEqual(res1.id, admin_user.id)

        res2 = run_coroutine(require_admin(current_user=super_admin_user))
        self.assertEqual(res2.id, super_admin_user.id)

    def test_require_admin_rejects_regular_user(self):
        regular_user = User(
            id=uuid4(),
            name="Regular User",
            email="user@example.com",
            phone_number="9876543212",
            reference_id="CNX-REF-USER",
            role=UserRoleEnum.USER,
            is_verified=True,
        )
        with self.assertRaises(ForbiddenError):
            run_coroutine(require_admin(current_user=regular_user))

    def test_query_validation_date_range(self):
        # Valid date range
        query = AdminLeadListQuery(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 15),
            status=LeadStatus.LEAD_SUBMITTED,
            loan_type=LoanType.PERSONAL_LOAN,
        )
        self.assertEqual(query.start_date, date(2026, 1, 1))
        self.assertEqual(query.end_date, date(2026, 1, 15))

        # Invalid date range (start_date after end_date)
        with self.assertRaises(ValidationError):
            AdminLeadListQuery(
                start_date=date(2026, 2, 1),
                end_date=date(2026, 1, 1),
            )

        # Invalid page size (> 100)
        with self.assertRaises(ValidationError):
            AdminLeadListQuery(page_size=101)

        # Invalid page (< 1)
        with self.assertRaises(ValidationError):
            AdminLeadListQuery(page=0)

    def test_lead_service_get_admin_leads(self):
        creator = User(
            id=uuid4(),
            name="Lead Creator",
            email="creator@example.com",
            phone_number="9876543213",
            reference_id="CNX-REF-CREATOR",
        )
        lead1 = Lead(
            id=uuid4(),
            lead_id="CNX-20261027-AAA111BBB222",
            created_by_user_id=creator.id,
            referred_by_user_id=None,
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            full_name="JOHN DOE",
            email="john@example.com",
            contact_number="9876543213",
            city="Mumbai",
            loan_amount=Decimal("500000.00"),
            monthly_income=Decimal("80000.00"),
            credit_score=750,
            status=LeadStatus.LEAD_SUBMITTED,
        )
        lead1.created_by = creator
        lead1.referred_by = None
        lead1.created_at = datetime.now(UTC)
        lead1.updated_at = datetime.now(UTC)

        lead2 = Lead(
            id=uuid4(),
            lead_id="CNX-20261027-CCC333DDD444",
            created_by_user_id=creator.id,
            referred_by_user_id=creator.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.BUSINESS_LOAN,
            full_name="JANE SMITH",
            email="jane@example.com",
            contact_number="9876543299",
            city="Bengaluru",
            loan_amount=Decimal("1500000.00"),
            monthly_income=Decimal("150000.00"),
            credit_score=800,
            status=LeadStatus.BANK_PROCESS,
        )
        lead2.created_by = creator
        lead2.referred_by = creator
        lead2.created_at = datetime.now(UTC) - timedelta(days=2)
        lead2.updated_at = datetime.now(UTC) - timedelta(days=2)

        fake_repo = _FakeLeadRepository(leads=[lead1, lead2])
        service = LeadService(
            session=None,
            lead_repository=fake_repo,
            lead_status_history_repository=None,
        )

        result: AdminLeadListResponse = run_coroutine(
            service.get_admin_leads(
                page=1,
                page_size=10,
                search="JOHN",
                status=LeadStatus.LEAD_SUBMITTED,
                loan_type=LoanType.PERSONAL_LOAN,
                start_date=date.today() - timedelta(days=5),
                end_date=date.today(),
            )
        )

        self.assertEqual(result.total, 1)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].lead_id, lead1.lead_id)
        self.assertEqual(result.items[0].full_name, "JOHN DOE")
        self.assertEqual(result.items[0].created_by.email, "creator@example.com")
        self.assertIsNone(result.items[0].referred_by)
        self.assertFalse(result.has_next)
        self.assertFalse(result.has_previous)


class _FakeLeadRepository:
    def __init__(self, leads: list[Lead]):
        self.leads = leads

    async def get_admin_leads_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        status: LeadStatus | None = None,
        loan_type: LoanType | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        filtered = self.leads
        if status:
            filtered = [l for l in filtered if l.status == status]
        if loan_type:
            filtered = [l for l in filtered if l.loan_type == loan_type]
        if search:
            s = search.lower()
            filtered = [
                l for l in filtered
                if s in l.lead_id.lower() or s in l.full_name.lower() or s in l.email.lower()
            ]
        total = len(filtered)
        offset = (page - 1) * page_size
        return filtered[offset : offset + page_size], total


if __name__ == "__main__":
    unittest.main()

