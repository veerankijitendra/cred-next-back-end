import asyncio
import sys
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from pydantic import ValidationError

from app.core.constants import (
    ApplicationType,
    LeadStatus,
    LoanType,
    WithdrawalStatus,
)
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.working_days import add_working_days, calculate_remaining_working_days
from app.enums.user import UserRoleEnum
from app.models.bonus_withdrawal import BonusWithdrawal
from app.models.lead import Lead
from app.models.user import User
from app.schemas.bonus import WithdrawRequest
from app.services.bonus import BonusService


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


class _FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True
        return None

    async def rollback(self):
        self.rolled_back = True
        return None

    async def refresh(self, obj, attribute_names=None):
        return None


class _FakeLeadRepository:
    def __init__(self, leads: list[Lead]):
        self.leads = {l.lead_id: l for l in leads}
        self.leads_by_id = {l.id: l for l in leads}

    async def get_by_lead_id(self, *, lead_id: str) -> Lead | None:
        return self.leads.get(lead_id)

    async def get_by_id(self, lead_id: UUID) -> Lead | None:
        return self.leads_by_id.get(lead_id)


class _FakeWithdrawalRepository:
    def __init__(self, withdrawals: list[BonusWithdrawal] | None = None):
        self.withdrawals_by_lead = {w.lead_id: w for w in withdrawals or []}
        self.withdrawals = list(withdrawals or [])

    async def create(self, *, withdrawal: BonusWithdrawal) -> BonusWithdrawal:
        self.withdrawals_by_lead[withdrawal.lead_id] = withdrawal
        self.withdrawals.append(withdrawal)
        return withdrawal

    async def get_by_lead_id(self, *, lead_id: UUID) -> BonusWithdrawal | None:
        return self.withdrawals_by_lead.get(lead_id)

    async def get_by_lead_ids(self, *, lead_ids: list[UUID]) -> dict[UUID, BonusWithdrawal]:
        return {lid: self.withdrawals_by_lead[lid] for lid in lead_ids if lid in self.withdrawals_by_lead}

    async def get_user_withdrawals(self, *, user_id: UUID) -> list[BonusWithdrawal]:
        return [w for w in self.withdrawals if w.user_id == user_id]

    async def get_user_withdrawals_paginated(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[BonusWithdrawal], int]:
        user_w = [w for w in self.withdrawals if w.user_id == user_id]
        return user_w[(page - 1) * page_size : page * page_size], len(user_w)


class BonusAndWithdrawalTests(unittest.TestCase):
    def setUp(self):
        self.partner = User(
            id=uuid4(),
            name="Partner Agent",
            email="partner@example.com",
            phone_number="9876543210",
            reference_id="CNX-REF-PART01",
            role=UserRoleEnum.USER,
        )
        self.other_user = User(
            id=uuid4(),
            name="Unrelated User",
            email="other@example.com",
            phone_number="9876543299",
            reference_id="CNX-REF-OTHER",
            role=UserRoleEnum.USER,
        )

    # 1. Verification of Working Days logic
    def test_working_days_skips_weekends(self):
        disbursed = datetime(2026, 11, 4, 10, 0, 0, tzinfo=UTC)
        cooling_end = add_working_days(disbursed, 7)
        self.assertEqual(cooling_end.date(), datetime(2026, 11, 13).date())
        self.assertEqual(cooling_end.weekday(), 4)

        now_day_4 = datetime(2026, 11, 10, 10, 0, 0, tzinfo=UTC)
        remaining = calculate_remaining_working_days(cooling_end, now_day_4)
        self.assertEqual(remaining, 3)

        now_after = datetime(2026, 11, 14, 10, 0, 0, tzinfo=UTC)
        self.assertEqual(calculate_remaining_working_days(cooling_end, now_after), 0)

    # 2. Verification of calculation for Personal Loan (10L PL Example)
    def test_personal_loan_bonus_and_tds_calculation(self):
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261104-PL0000000001",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.PERSONAL_LOAN,
            full_name="JOHN DOE",
            email="john@example.com",
            contact_number="9876543211",
            city="Mumbai",
            loan_amount=Decimal("1000000.00"),  # 10 Lakhs
            monthly_income=Decimal("80000.00"),
            status=LeadStatus.DISBURSED,
            disbursed_at=datetime(2026, 11, 4, 10, 0, tzinfo=UTC),
        )

        calc = BonusService.calculate_lead_bonus(lead=lead)
        self.assertEqual(calc.commission_rate, Decimal("0.010"))
        self.assertEqual(calc.commission_percent_label, "1.0%")
        self.assertEqual(calc.gross_bonus, Decimal("10000.00"))
        self.assertEqual(calc.tds_rate, Decimal("0.050"))
        self.assertEqual(calc.tds_percent_label, "5%")
        self.assertEqual(calc.tds_amount, Decimal("500.00"))
        self.assertEqual(calc.net_bonus, Decimal("9500.00"))

    # 3. Verification of calculation for Business Loan (1%)
    def test_business_loan_bonus_calculation(self):
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261104-BL0000000001",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.BUSINESS_LOAN,
            full_name="BUSINESS CORP",
            email="biz@example.com",
            contact_number="9876543212",
            city="Delhi",
            loan_amount=Decimal("1500000.00"),  # 15 Lakhs
            monthly_income=Decimal("150000.00"),
            status=LeadStatus.DISBURSED,
            disbursed_at=datetime(2026, 11, 4, 10, 0, tzinfo=UTC),
        )

        calc = BonusService.calculate_lead_bonus(lead=lead)
        self.assertEqual(calc.commission_rate, Decimal("0.010"))
        self.assertEqual(calc.gross_bonus, Decimal("15000.00"))
        self.assertEqual(calc.tds_amount, Decimal("750.00"))
        self.assertEqual(calc.net_bonus, Decimal("14250.00"))

    # 4. Verification of calculation for Loan Against Property (0.5%)
    def test_lap_bonus_calculation(self):
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261104-LAP00000001",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.LOAN_AGAINST_PROPERTY,
            full_name="PROPERTY OWNER",
            email="prop@example.com",
            contact_number="9876543213",
            city="Chennai",
            loan_amount=Decimal("2000000.00"),  # 20 Lakhs
            monthly_income=Decimal("200000.00"),
            status=LeadStatus.DISBURSED,
            disbursed_at=datetime(2026, 11, 4, 10, 0, tzinfo=UTC),
        )

        calc = BonusService.calculate_lead_bonus(lead=lead)
        self.assertEqual(calc.commission_rate, Decimal("0.005"))
        self.assertEqual(calc.commission_percent_label, "0.5%")
        self.assertEqual(calc.gross_bonus, Decimal("10000.00"))
        self.assertEqual(calc.tds_amount, Decimal("500.00"))
        self.assertEqual(calc.net_bonus, Decimal("9500.00"))

    # 5. Verification of calculation for Home Loan (0.2%)
    def test_home_loan_bonus_calculation(self):
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261104-HL0000000001",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.HOUSING_LOAN,
            full_name="HOME BUYER",
            email="home@example.com",
            contact_number="9876543214",
            city="Pune",
            loan_amount=Decimal("5000000.00"),  # 50 Lakhs
            monthly_income=Decimal("250000.00"),
            status=LeadStatus.DISBURSED,
            disbursed_at=datetime(2026, 11, 4, 10, 0, tzinfo=UTC),
        )

        calc = BonusService.calculate_lead_bonus(lead=lead)
        self.assertEqual(calc.commission_rate, Decimal("0.002"))
        self.assertEqual(calc.commission_percent_label, "0.2%")
        self.assertEqual(calc.gross_bonus, Decimal("10000.00"))
        self.assertEqual(calc.tds_amount, Decimal("500.00"))
        self.assertEqual(calc.net_bonus, Decimal("9500.00"))

    # 6. Preview during cooling period shows locked status
    def test_preview_during_cooling_period(self):
        disbursed_date = datetime.now(UTC) - timedelta(days=2)  # only 2 days ago
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261116-RECENT00001",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.PERSONAL_LOAN,
            full_name="RECENT APPLICANT",
            email="recent@example.com",
            contact_number="9876543215",
            city="Hyderabad",
            loan_amount=Decimal("1000000.00"),
            monthly_income=Decimal("70000.00"),
            status=LeadStatus.DISBURSED,
            disbursed_at=disbursed_date,
        )

        lead_repo = _FakeLeadRepository([lead])
        withdrawal_repo = _FakeWithdrawalRepository([])
        service = BonusService(
            session=_FakeSession(),
            lead_repository=lead_repo,
            withdrawal_repository=withdrawal_repo,
        )

        preview = run_coroutine(
            service.get_lead_bonus_preview(lead_id=lead.lead_id, current_user=self.partner)
        )
        self.assertFalse(preview.is_withdrawal_eligible)
        self.assertEqual(preview.withdrawal_status, "cooling_period")
        self.assertGreater(preview.remaining_working_days, 0)

    # 7. Withdrawal attempt during cooling period is blocked
    def test_withdrawal_blocked_during_cooling_period(self):
        disbursed_date = datetime.now(UTC) - timedelta(days=2)
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261116-LOCKED00001",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.PERSONAL_LOAN,
            full_name="LOCKED BORROWER",
            email="locked@example.com",
            contact_number="9876543216",
            city="Bengaluru",
            loan_amount=Decimal("1000000.00"),
            monthly_income=Decimal("70000.00"),
            status=LeadStatus.DISBURSED,
            disbursed_at=disbursed_date,
        )

        lead_repo = _FakeLeadRepository([lead])
        withdrawal_repo = _FakeWithdrawalRepository([])
        service = BonusService(
            session=_FakeSession(),
            lead_repository=lead_repo,
            withdrawal_repository=withdrawal_repo,
        )

        req = WithdrawRequest(
            lead_id=lead.lead_id,
            upi_id="partner@okhdfcbank",
            account_holder_name="PARTNER AGENT",
        )

        with self.assertRaises(ConflictError) as ctx:
            run_coroutine(
                service.request_withdrawal(payload=req, current_user=self.partner)
            )
        self.assertIn("cooling period", str(ctx.exception))

    # 8. Successful UPI withdrawal after 7 working days cooling period
    def test_successful_upi_withdrawal_after_cooling_period(self):
        disbursed_date = datetime.now(UTC) - timedelta(days=20)  # well past 7 working days
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261020-ELIGIBLE001",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.PERSONAL_LOAN,
            full_name="MATURED BORROWER",
            email="matured@example.com",
            contact_number="9876543217",
            city="Kolkata",
            loan_amount=Decimal("1000000.00"),  # 10L
            monthly_income=Decimal("70000.00"),
            status=LeadStatus.DISBURSED,
            disbursed_at=disbursed_date,
        )

        lead_repo = _FakeLeadRepository([lead])
        withdrawal_repo = _FakeWithdrawalRepository([])
        fake_session = _FakeSession()
        service = BonusService(
            session=fake_session,
            lead_repository=lead_repo,
            withdrawal_repository=withdrawal_repo,
        )

        # 1. Preview shows ready_for_withdrawal
        preview = run_coroutine(
            service.get_lead_bonus_preview(lead_id=lead.lead_id, current_user=self.partner)
        )
        self.assertTrue(preview.is_withdrawal_eligible)
        self.assertEqual(preview.withdrawal_status, "ready_for_withdrawal")
        self.assertEqual(preview.remaining_working_days, 0)

        # 2. Submit UPI withdrawal
        req = WithdrawRequest(
            lead_id=lead.lead_id,
            upi_id="customer.partner@okhdfcbank",
            account_holder_name="PARTNER AGENT",
        )
        res = run_coroutine(
            service.request_withdrawal(payload=req, current_user=self.partner)
        )
        self.assertEqual(res.lead_id, lead.lead_id)
        self.assertEqual(res.gross_bonus, Decimal("10000.00"))
        self.assertEqual(res.tds_amount, Decimal("500.00"))
        self.assertEqual(res.net_bonus, Decimal("9500.00"))
        self.assertEqual(res.status, WithdrawalStatus.PENDING)
        self.assertEqual(res.payout_method, "upi")
        self.assertEqual(res.upi_id, "customer.partner@okhdfcbank")
        self.assertEqual(res.account_holder_name, "PARTNER AGENT")
        self.assertTrue(fake_session.committed)

    # 9. Duplicate withdrawal attempt is prevented
    def test_duplicate_withdrawal_prevented(self):
        disbursed_date = datetime.now(UTC) - timedelta(days=20)
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261020-ALREADY001",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.PERSONAL_LOAN,
            full_name="ALREADY WITHDRAWN",
            email="already@example.com",
            contact_number="9876543218",
            city="Jaipur",
            loan_amount=Decimal("1000000.00"),
            monthly_income=Decimal("70000.00"),
            status=LeadStatus.DISBURSED,
            disbursed_at=disbursed_date,
        )

        existing_withdrawal = BonusWithdrawal(
            id=uuid4(),
            lead_id=lead.id,
            user_id=self.partner.id,
            loan_type=lead.loan_type,
            disbursed_amount=lead.loan_amount,
            commission_rate=Decimal("0.010"),
            gross_bonus=Decimal("10000.00"),
            tds_rate=Decimal("0.050"),
            tds_amount=Decimal("500.00"),
            net_bonus=Decimal("9500.00"),
            cooling_period_end_date=disbursed_date,
            payout_method="upi",
            upi_id="partner@okhdfcbank",
            account_holder_name="PARTNER AGENT",
            status=WithdrawalStatus.PENDING,
        )

        lead_repo = _FakeLeadRepository([lead])
        withdrawal_repo = _FakeWithdrawalRepository([existing_withdrawal])
        service = BonusService(
            session=_FakeSession(),
            lead_repository=lead_repo,
            withdrawal_repository=withdrawal_repo,
        )

        req = WithdrawRequest(
            lead_id=lead.lead_id,
            upi_id="partner@okhdfcbank",
            account_holder_name="PARTNER AGENT",
        )

        with self.assertRaises(ConflictError) as ctx:
            run_coroutine(
                service.request_withdrawal(payload=req, current_user=self.partner)
            )
        self.assertIn("already been submitted", str(ctx.exception))

    # 10. Non-disbursed lead raises conflict error
    def test_non_disbursed_lead_rejected(self):
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261104-INPROCESS01",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.PERSONAL_LOAN,
            full_name="IN PROCESS USER",
            email="inprocess@example.com",
            contact_number="9876543219",
            city="Ahmedabad",
            loan_amount=Decimal("1000000.00"),
            monthly_income=Decimal("70000.00"),
            status=LeadStatus.BANK_PROCESS,  # not disbursed
        )

        lead_repo = _FakeLeadRepository([lead])
        withdrawal_repo = _FakeWithdrawalRepository([])
        service = BonusService(
            session=_FakeSession(),
            lead_repository=lead_repo,
            withdrawal_repository=withdrawal_repo,
        )

        with self.assertRaises(ConflictError) as ctx:
            run_coroutine(
                service.get_lead_bonus_preview(lead_id=lead.lead_id, current_user=self.partner)
            )
        self.assertIn("not yet disbursed", str(ctx.exception))

    # 11. Unrelated user unauthorized to access bonus
    def test_unrelated_user_forbidden(self):
        lead = Lead(
            id=uuid4(),
            lead_id="CNX-20261104-OTHERUSER01",
            created_by_user_id=self.partner.id,
            referred_by_user_id=self.partner.id,
            application_type=ApplicationType.REFERRAL,
            loan_type=LoanType.PERSONAL_LOAN,
            full_name="PRIVATE LEAD",
            email="priv@example.com",
            contact_number="9876543220",
            city="Surat",
            loan_amount=Decimal("1000000.00"),
            monthly_income=Decimal("70000.00"),
            status=LeadStatus.DISBURSED,
            disbursed_at=datetime.now(UTC) - timedelta(days=20),
        )

        lead_repo = _FakeLeadRepository([lead])
        withdrawal_repo = _FakeWithdrawalRepository([])
        service = BonusService(
            session=_FakeSession(),
            lead_repository=lead_repo,
            withdrawal_repository=withdrawal_repo,
        )

        with self.assertRaises(ForbiddenError):
            run_coroutine(
                service.get_lead_bonus_preview(lead_id=lead.lead_id, current_user=self.other_user)
            )

    # 12. UPI ID format validation
    def test_upi_id_format_validation(self):
        # Valid UPI IDs
        valid_upis = [
            "customer@okhdfcbank",
            "9876543210@paytm",
            "john.doe@ybl",
            "partner-123@axisbank",
            "user_name@ibl",
        ]
        for upi in valid_upis:
            req = WithdrawRequest(
                lead_id="CNX-20261104-VALID001",
                upi_id=upi,
                account_holder_name="TEST USER",
            )
            self.assertEqual(req.upi_id, upi.lower())

        # Invalid UPI IDs
        invalid_upis = [
            "notaupi",
            "@nobank",
            "missingbank@",
            "has space@bank",
            "invalid#char@bank",
        ]
        for upi in invalid_upis:
            with self.assertRaises(ValidationError):
                WithdrawRequest(
                    lead_id="CNX-20261104-VALID001",
                    upi_id=upi,
                    account_holder_name="TEST USER",
                )


if __name__ == "__main__":
    unittest.main()
