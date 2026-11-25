import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.constants import (
    AcquisitionSource,
    ApplicationType,
    LeadStatus,
    LoanType,
    OTPChannel,
    normalize_acquisition_source,
)
from app.enums.user import UserRoleEnum
from app.models.lead import Lead
from app.models.lead_status_history import LeadStatusHistory
from app.models.user import User
from app.schemas.admin_lead import (
    AdminLeadItemResponse,
    AdminLeadListQuery,
    AdminLeadListResponse,
    AdminLeadStats,
    LeadUserInfo,
)
from app.schemas.auth import RegisterRequest
from app.schemas.lead import LeadRequest
from app.services.auth import AuthService
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


class _FakeDBSession:
    def __init__(self):
        self.added_objects = []
        self.deleted_objects = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added_objects.append(obj)

    async def delete(self, obj):
        self.deleted_objects.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True
        return None

    async def rollback(self):
        self.rolled_back = True
        return None

    async def refresh(self, obj, attribute_names=None):
        return None


class _FakeLeadRepository:
    def __init__(self, leads: list[Lead] | None = None):
        self.leads = leads or []

    async def create(self, *, lead: Lead) -> Lead:
        self.leads.append(lead)
        return lead

    async def get_by_id(self, lead_id: UUID) -> Lead | None:
        for lead in self.leads:
            if lead.id == lead_id:
                return lead
        return None

    async def get_by_lead_id(self, lead_id: str) -> Lead | None:
        for lead in self.leads:
            if lead.lead_id == lead_id:
                return lead
        return None

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
        source: str | None = None,
    ) -> tuple[list[Lead], int]:
        filtered = list(self.leads)
        if search:
            s = search.lower()
            filtered = [
                l for l in filtered
                if s in l.full_name.lower() or s in l.contact_number or s in l.lead_id.lower()
            ]
        if status:
            filtered = [l for l in filtered if l.status == status]
        if loan_type:
            filtered = [l for l in filtered if l.loan_type == loan_type]
        if source:
            filtered = [l for l in filtered if l.source == source]

        total = len(filtered)
        start = (page - 1) * page_size
        return filtered[start : start + page_size], total

    async def get_admin_lead_stats(self) -> dict:
        breakdown: dict[str, int] = {}
        for l in self.leads:
            src = l.source or AcquisitionSource.BROWSER.value
            breakdown[src] = breakdown.get(src, 0) + 1

        return {
            "total": len(self.leads),
            "submitted": sum(1 for l in self.leads if l.status == LeadStatus.LEAD_SUBMITTED),
            "evaluation": sum(1 for l in self.leads if l.status == LeadStatus.CUSTOMER_EVALUATION),
            "underwriting": sum(1 for l in self.leads if l.status in (LeadStatus.DOCUMENTS, LeadStatus.BANK_PROCESS)),
            "disbursed": sum(1 for l in self.leads if l.status == LeadStatus.DISBURSED),
            "rejected": sum(1 for l in self.leads if l.status == LeadStatus.REJECTED),
            "source_breakdown": breakdown,
        }


class _FakeLeadStatusHistoryRepository:
    def __init__(self):
        self.history = []

    async def create(self, *, history: LeadStatusHistory) -> LeadStatusHistory:
        self.history.append(history)
        return history


class _FakeUserRepository:
    def __init__(self, users: list[User] | None = None):
        self.users = users or []

    async def get_by_reference_id(self, *, reference_id: str) -> User | None:
        for u in self.users:
            if u.reference_id == reference_id:
                return u
        return None

    async def get_by_email(self, *, email: str) -> User | None:
        for u in self.users:
            if u.email == email:
                return u
        return None

    async def get_by_phone_number(self, *, phone_number: str) -> User | None:
        for u in self.users:
            if u.phone_number == phone_number:
                return u
        return None

    async def create(self, *, user: User) -> User:
        self.users.append(user)
        return user

    async def delete(self, *, user: User) -> None:
        if user in self.users:
            self.users.remove(user)


class _FakeOTPService:
    def __init__(self):
        self.created_otps = []

    async def create_otp(self, *, user_id: UUID, channel: OTPChannel) -> str:
        otp = "123456"
        self.created_otps.append((user_id, channel, otp))
        return otp


class _FakeNotificationService:
    def __init__(self):
        self.sent = []

    async def send_otp(self, *, channel: OTPChannel, destination: str, otp: str) -> None:
        self.sent.append((channel, destination, otp))


class LeadSourceTrackingTests(unittest.TestCase):
    def test_normalize_acquisition_source(self):
        # Canonical names
        self.assertEqual(normalize_acquisition_source("BrightFitness"), AcquisitionSource.BRIGHT_FITNESS.value)
        self.assertEqual(normalize_acquisition_source("V-Card"), AcquisitionSource.V_CARD.value)
        self.assertEqual(normalize_acquisition_source("P-Card"), AcquisitionSource.P_CARD.value)
        self.assertEqual(normalize_acquisition_source("SH"), AcquisitionSource.SH.value)
        self.assertEqual(normalize_acquisition_source("Browser"), AcquisitionSource.BROWSER.value)

        # Case-insensitivity & aliases
        self.assertEqual(normalize_acquisition_source("brightfitness"), "BrightFitness")
        self.assertEqual(normalize_acquisition_source("BRIGHT_FITNESS"), "BrightFitness")
        self.assertEqual(normalize_acquisition_source("vcard"), "V-Card")
        self.assertEqual(normalize_acquisition_source("v-card"), "V-Card")
        self.assertEqual(normalize_acquisition_source("pcard"), "P-Card")
        self.assertEqual(normalize_acquisition_source("p-card"), "P-Card")
        self.assertEqual(normalize_acquisition_source("sh"), "SH")
        self.assertEqual(normalize_acquisition_source("browser"), "Browser")

        # Whitespace handling
        self.assertEqual(normalize_acquisition_source("  BrightFitness  "), "BrightFitness")
        self.assertEqual(normalize_acquisition_source("  vcard  "), "V-Card")

        # Default fallback for unknown / empty / None
        self.assertEqual(normalize_acquisition_source(None), AcquisitionSource.BROWSER.value)
        self.assertEqual(normalize_acquisition_source(""), AcquisitionSource.BROWSER.value)
        self.assertEqual(normalize_acquisition_source("   "), AcquisitionSource.BROWSER.value)
        self.assertEqual(normalize_acquisition_source("google"), AcquisitionSource.BROWSER.value)
        self.assertEqual(normalize_acquisition_source("unknown-channel"), AcquisitionSource.BROWSER.value)

    def test_lead_request_source_validation(self):
        # Default source is Browser when omitted
        req1 = LeadRequest(
            full_name="JOHN DOE",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            contact_number="9876543210",
            email="john@example.com",
            city="Mumbai",
            loan_amount=Decimal("500000"),
            monthly_income=Decimal("50000"),
            credit_score=750,
        )
        self.assertEqual(req1.source, "Browser")

        # Explicit known source
        req2 = LeadRequest(
            full_name="JOHN DOE",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            contact_number="9876543210",
            email="john@example.com",
            city="Mumbai",
            loan_amount=Decimal("500000"),
            monthly_income=Decimal("50000"),
            credit_score=750,
            source="BrightFitness",
        )
        self.assertEqual(req2.source, "BrightFitness")

        # Trims whitespace and preserves custom source strings for service-layer DB resolution
        req3 = LeadRequest(
            full_name="JOHN DOE",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            contact_number="9876543210",
            email="john@example.com",
            city="Mumbai",
            loan_amount=Decimal("500000"),
            monthly_income=Decimal("50000"),
            credit_score=750,
            source="  GoldGym  ",
        )
        self.assertEqual(req3.source, "GoldGym")

        # Empty/blank source defaults to Browser
        req4 = LeadRequest(
            full_name="JOHN DOE",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            contact_number="9876543210",
            email="john@example.com",
            city="Mumbai",
            loan_amount=Decimal("500000"),
            monthly_income=Decimal("50000"),
            credit_score=750,
            source="   ",
        )
        self.assertEqual(req4.source, "Browser")

    def test_register_request_source_validation(self):
        req1 = RegisterRequest(
            name="Alice Smith",
            email="alice@example.com",
            phone_number="9876543210",
            password="Password123!",
        )
        self.assertEqual(req1.source, "Browser")

        req2 = RegisterRequest(
            name="Alice Smith",
            email="alice@example.com",
            phone_number="9876543210",
            password="Password123!",
            source="  GoldGym  ",
        )
        self.assertEqual(req2.source, "GoldGym")

        req3 = RegisterRequest(
            name="Alice Smith",
            email="alice@example.com",
            phone_number="9876543210",
            password="Password123!",
            source="SH",
        )
        self.assertEqual(req3.source, "SH")

    def test_create_lead_with_source(self):
        session = _FakeDBSession()
        lead_repo = _FakeLeadRepository()
        history_repo = _FakeLeadStatusHistoryRepository()
        user_repo = _FakeUserRepository()

        user = User(
            id=uuid4(),
            name="Lead Submitter",
            email="submitter@example.com",
            phone_number="9876543210",
            reference_id="CNX-REF-1234",
        )

        service = LeadService(
            session=session,
            lead_repository=lead_repo,
            lead_status_history_repository=history_repo,
            user_repository=user_repo,
        )

        # 1. Create lead with explicit source "BrightFitness"
        req = LeadRequest(
            full_name="JOHN DOE",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            contact_number="9876543210",
            email="john@example.com",
            city="Mumbai",
            loan_amount=Decimal("500000"),
            monthly_income=Decimal("50000"),
            credit_score=750,
            source="brightfitness",
        )

        created_lead = run_coroutine(service.create_lead(lead_request=req, user=user))
        self.assertEqual(created_lead.source, "BrightFitness")
        self.assertEqual(len(lead_repo.leads), 1)
        self.assertEqual(lead_repo.leads[0].source, "BrightFitness")

        # 2. Create lead without source (defaults to Browser)
        req2 = LeadRequest(
            full_name="JANE DOE",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            contact_number="9876543210",
            email="jane@example.com",
            city="Pune",
            loan_amount=Decimal("300000"),
            monthly_income=Decimal("40000"),
            credit_score=720,
        )
        created_lead2 = run_coroutine(service.create_lead(lead_request=req2, user=user))
        self.assertEqual(created_lead2.source, "Browser")

    def test_auth_register_user_with_source(self):
        session = _FakeDBSession()
        user_repo = _FakeUserRepository()
        otp_svc = _FakeOTPService()
        notif_svc = _FakeNotificationService()

        service = AuthService(session=session, otp_service=otp_svc, notification_service=notif_svc)
        service.user_repository = user_repo

        # Register user with source "P-Card"
        reg_req = RegisterRequest(
            name="Bob User",
            email="bob@example.com",
            phone_number="9876543211",
            password="Password123!",
            source="pcard",
        )

        resp = run_coroutine(service.register_user(data=reg_req))
        self.assertIsNotNone(resp.user_id)
        self.assertEqual(len(user_repo.users), 1)
        self.assertEqual(user_repo.users[0].source, "P-Card")

    def test_admin_lead_source_filter_and_stats(self):
        creator = User(
            id=uuid4(),
            name="Lead Creator",
            email="creator@example.com",
            phone_number="9876543210",
            reference_id="CNX-REF-CREATOR",
        )

        leads = [
            Lead(
                id=uuid4(),
                lead_id="CNX-1",
                created_by_user_id=creator.id,
                referred_by_user_id=None,
                application_type=ApplicationType.SELF,
                loan_type=LoanType.PERSONAL_LOAN,
                full_name="ALICE",
                email="alice@example.com",
                contact_number="9876543210",
                city="Delhi",
                loan_amount=Decimal("100000"),
                monthly_income=Decimal("20000"),
                status=LeadStatus.LEAD_SUBMITTED,
                source="BrightFitness",
            ),
            Lead(
                id=uuid4(),
                lead_id="CNX-2",
                created_by_user_id=creator.id,
                referred_by_user_id=None,
                application_type=ApplicationType.SELF,
                loan_type=LoanType.BUSINESS_LOAN,
                full_name="BOB",
                email="bob@example.com",
                contact_number="9876543211",
                city="Mumbai",
                loan_amount=Decimal("200000"),
                monthly_income=Decimal("30000"),
                status=LeadStatus.CUSTOMER_EVALUATION,
                source="V-Card",
            ),
            Lead(
                id=uuid4(),
                lead_id="CNX-3",
                created_by_user_id=creator.id,
                referred_by_user_id=None,
                application_type=ApplicationType.SELF,
                loan_type=LoanType.PERSONAL_LOAN,
                full_name="CHARLIE",
                email="charlie@example.com",
                contact_number="9876543212",
                city="Chennai",
                loan_amount=Decimal("300000"),
                monthly_income=Decimal("40000"),
                status=LeadStatus.DISBURSED,
                source="BrightFitness",
            ),
            Lead(
                id=uuid4(),
                lead_id="CNX-4",
                created_by_user_id=creator.id,
                referred_by_user_id=None,
                application_type=ApplicationType.SELF,
                loan_type=LoanType.PERSONAL_LOAN,
                full_name="DAVID",
                email="david@example.com",
                contact_number="9876543213",
                city="Bengaluru",
                loan_amount=Decimal("400000"),
                monthly_income=Decimal("50000"),
                status=LeadStatus.LEAD_SUBMITTED,
                source="Browser",
            ),
        ]
        for l in leads:
            l.created_by = creator
            l.referred_by = None
            l.created_at = datetime.now(UTC)
            l.updated_at = datetime.now(UTC)

        repo = _FakeLeadRepository(leads=leads)
        service = LeadService(session=None, lead_repository=repo, lead_status_history_repository=None)

        # 1. Query with source filter "BrightFitness"
        res = run_coroutine(service.get_admin_leads(source="BrightFitness"))
        self.assertEqual(res.total, 2)
        self.assertEqual(len(res.items), 2)
        for item in res.items:
            self.assertEqual(item.source, "BrightFitness")

        # 2. Check source_breakdown in stats
        self.assertIsNotNone(res.stats.source_breakdown)
        self.assertEqual(res.stats.source_breakdown.get("BrightFitness"), 2)
        self.assertEqual(res.stats.source_breakdown.get("V-Card"), 1)
        self.assertEqual(res.stats.source_breakdown.get("Browser"), 1)
        self.assertEqual(res.stats.total, 4)

        # 3. Query with source filter "V-Card"
        res_vcard = run_coroutine(service.get_admin_leads(source="V-Card"))
        self.assertEqual(res_vcard.total, 1)
        self.assertEqual(res_vcard.items[0].lead_id, "CNX-2")
        self.assertEqual(res_vcard.items[0].source, "V-Card")

        # 4. Query without source filter returns all 4
        res_all = run_coroutine(service.get_admin_leads())
        self.assertEqual(res_all.total, 4)


if __name__ == "__main__":
    unittest.main()
