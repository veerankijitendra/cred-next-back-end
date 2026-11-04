import unittest
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.constants import ApplicationType, LeadStatus, LoanType
from app.core.reference_id import generate_reference_id
from app.enums.user import UserRoleEnum
from app.models.lead import Lead
from app.models.user import User
from app.schemas.lead import LeadRequest
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


class _FakeUserRepository:
    def __init__(self, users: list[User]):
        self.users = users

    async def get_by_reference_id(self, *, reference_id: str) -> User | None:
        clean = reference_id.strip().upper()
        for u in self.users:
            if u.reference_id.upper() == clean:
                return u
        return None


class _FakeLeadRepository:
    def __init__(self):
        self.leads = []

    async def create(self, lead: Lead) -> Lead:
        self.leads.append(lead)
        return lead


class _FakeHistoryRepository:
    def __init__(self):
        self.items = []

    async def create(self, history):
        self.items.append(history)
        return history


class _FakeSession:
    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def refresh(self, obj, attribute_names=None):
        return None


class ReferralSystemTests(unittest.TestCase):
    def test_generate_reference_id_format(self):
        uid = uuid4()
        ref_id = generate_reference_id(uid)
        self.assertTrue(ref_id.startswith("CNX-REF-"))
        self.assertEqual(len(ref_id), 16)
        self.assertEqual(ref_id, f"CNX-REF-{uid.hex[:8].upper()}")

    def test_self_application_with_referrer_code_attributes_lead(self):
        referrer = User(
            id=uuid4(),
            name="Referring Partner",
            email="partner@example.com",
            phone_number="9876543210",
            reference_id="CNX-REF-PARTNER1",
            role=UserRoleEnum.USER,
        )
        applicant = User(
            id=uuid4(),
            name="Self Applicant",
            email="applicant@example.com",
            phone_number="9876543211",
            reference_id="CNX-REF-APPLIC01",
            role=UserRoleEnum.USER,
        )

        lead_repo = _FakeLeadRepository()
        history_repo = _FakeHistoryRepository()
        user_repo = _FakeUserRepository([referrer, applicant])

        service = LeadService(
            session=_FakeSession(),
            lead_repository=lead_repo,
            lead_status_history_repository=history_repo,
            user_repository=user_repo,
        )

        request = LeadRequest(
            full_name="SELF APPLICANT",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            reference_id=referrer.reference_id,
            contact_number=applicant.phone_number,
            email=applicant.email,
            city="Hyderabad",
            loan_amount=Decimal("300000.00"),
            monthly_income=Decimal("50000.00"),
            credit_score=750,
        )

        created_lead = run_coroutine(
            service.create_lead(lead_request=request, user=applicant)
        )

        self.assertEqual(created_lead.created_by_user_id, applicant.id)
        # Lead is attributed to the referring partner!
        self.assertEqual(created_lead.referred_by_user_id, referrer.id)
        self.assertEqual(created_lead.application_type, ApplicationType.SELF)

    def test_self_application_with_own_code_does_not_self_refer(self):
        applicant = User(
            id=uuid4(),
            name="Self Applicant",
            email="applicant@example.com",
            phone_number="9876543211",
            reference_id="CNX-REF-APPLIC01",
            role=UserRoleEnum.USER,
        )

        lead_repo = _FakeLeadRepository()
        history_repo = _FakeHistoryRepository()
        user_repo = _FakeUserRepository([applicant])

        service = LeadService(
            session=_FakeSession(),
            lead_repository=lead_repo,
            lead_status_history_repository=history_repo,
            user_repository=user_repo,
        )

        request = LeadRequest(
            full_name="SELF APPLICANT",
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            reference_id=applicant.reference_id,  # entering own code
            contact_number=applicant.phone_number,
            email=applicant.email,
            city="Hyderabad",
            loan_amount=Decimal("300000.00"),
            monthly_income=Decimal("50000.00"),
            credit_score=750,
        )

        created_lead = run_coroutine(
            service.create_lead(lead_request=request, user=applicant)
        )

        self.assertEqual(created_lead.created_by_user_id, applicant.id)
        self.assertIsNone(created_lead.referred_by_user_id)

    def test_partner_submitting_referral_lead_without_code_auto_attributes_to_partner(self):
        partner = User(
            id=uuid4(),
            name="DSA Agent",
            email="dsa@example.com",
            phone_number="9876543299",
            reference_id="CNX-REF-DSA00001",
            role=UserRoleEnum.USER,
        )

        lead_repo = _FakeLeadRepository()
        history_repo = _FakeHistoryRepository()
        user_repo = _FakeUserRepository([partner])

        service = LeadService(
            session=_FakeSession(),
            lead_repository=lead_repo,
            lead_status_history_repository=history_repo,
            user_repository=user_repo,
        )

        # Partner submits on behalf of client without typing reference_id
        request = LeadRequest(
            full_name="CLIENT BORROWER",
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.BUSINESS_LOAN,
            reference_id=None,
            contact_number="9123456789",  # different phone
            email="client@example.com",
            city="Bengaluru",
            loan_amount=Decimal("1500000.00"),
            monthly_income=Decimal("120000.00"),
            credit_score=780,
        )

        created_lead = run_coroutine(
            service.create_lead(lead_request=request, user=partner)
        )

        self.assertEqual(created_lead.created_by_user_id, partner.id)
        # Automatically attributed to the DSA partner!
        self.assertEqual(created_lead.referred_by_user_id, partner.id)
        self.assertEqual(created_lead.application_type, ApplicationType.REFERRAL)


if __name__ == "__main__":
    unittest.main()

