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
from app.enums.user import UserRoleEnum
from app.models.bonus_withdrawal import BonusWithdrawal
from app.models.lead import Lead
from app.models.user import User
from app.schemas.admin_withdrawal import (
    AdminProcessWithdrawalRequest,
    AdminWithdrawalItemResponse,
    AdminWithdrawalListResponse,
    AdminWithdrawalQuery,
    AdminWithdrawalStats,
)
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
        except Exception:
            raise
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


class _FakeWithdrawalRepository:
    def __init__(self, withdrawals=None):
        self.withdrawals = withdrawals or {}

    async def create(self, *, withdrawal: BonusWithdrawal) -> BonusWithdrawal:
        self.withdrawals[withdrawal.id] = withdrawal
        return withdrawal

    async def get_by_id(self, *, withdrawal_id: UUID) -> BonusWithdrawal | None:
        return self.withdrawals.get(withdrawal_id)

    async def get_by_id_with_relations(
        self, *, withdrawal_id: UUID
    ) -> BonusWithdrawal | None:
        return self.withdrawals.get(withdrawal_id)

    async def get_by_lead_id(self, *, lead_id: UUID) -> BonusWithdrawal | None:
        for w in self.withdrawals.values():
            if w.lead_id == lead_id:
                return w
        return None

    async def get_admin_withdrawals_paginated(
        self, *, page: int, page_size: int, status=None, search=None
    ) -> tuple[list[BonusWithdrawal], int]:
        items = list(self.withdrawals.values())
        if status:
            items = [w for w in items if w.status == status]
        if search:
            s = search.lower()
            items = [
                w
                for w in items
                if (w.upi_id and s in w.upi_id.lower())
                or (w.account_holder_name and s in w.account_holder_name.lower())
                or (w.transaction_reference and s in w.transaction_reference.lower())
            ]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    async def get_admin_withdrawal_stats(self) -> dict:
        pending_count = 0
        pending_amount = Decimal("0.00")
        processed_count = 0
        processed_amount = Decimal("0.00")
        rejected_count = 0
        rejected_amount = Decimal("0.00")
        total_tds = Decimal("0.00")

        for w in self.withdrawals.values():
            total_tds += w.tds_amount
            if w.status == WithdrawalStatus.PENDING:
                pending_count += 1
                pending_amount += w.net_bonus
            elif w.status == WithdrawalStatus.PROCESSED:
                processed_count += 1
                processed_amount += w.net_bonus
            elif w.status == WithdrawalStatus.REJECTED:
                rejected_count += 1
                rejected_amount += w.net_bonus

        return {
            "pending_count": pending_count,
            "pending_amount": pending_amount,
            "processed_count": processed_count,
            "processed_amount": processed_amount,
            "rejected_count": rejected_count,
            "rejected_amount": rejected_amount,
            "total_tds_withheld": total_tds,
        }


class _FakeLeadRepository:
    def __init__(self, leads=None):
        self.leads = leads or {}

    async def get_by_lead_id(self, lead_id: str) -> Lead | None:
        for lead in self.leads.values():
            if lead.lead_id == lead_id:
                return lead
        return None

    async def get_by_id(self, lead_id: UUID) -> Lead | None:
        return self.leads.get(lead_id)


class AdminWithdrawalTests(unittest.TestCase):
    def setUp(self):
        self.session = _FakeSession()
        self.user_id = uuid4()
        self.admin_id = uuid4()

        self.user = User(
            id=self.user_id,
            name="Rahul Sharma",
            email="rahul.sharma@example.com",
            phone_number="9876543210",
            reference_id="REF12345",
            role=UserRoleEnum.USER,
        )

        self.admin_user = User(
            id=self.admin_id,
            name="Finance Admin",
            email="finance.admin@crednext.com",
            phone_number="9876543211",
            reference_id="ADM001",
            role=UserRoleEnum.ADMIN,
        )

        self.lead_id = uuid4()
        self.lead = Lead(
            id=self.lead_id,
            lead_id="CNX-20261101-ABCD1234EF56",
            created_by_user_id=self.user_id,
            referred_by_user_id=None,
            application_type=ApplicationType.SELF,
            loan_type=LoanType.PERSONAL_LOAN,
            loan_amount=Decimal("1000000.00"),
            monthly_income=Decimal("80000.00"),
            full_name="Borrower One",
            contact_number="9123456780",
            email="borrower.one@example.com",
            city="Bengaluru",
            status=LeadStatus.DISBURSED,
        )
        # Disbursed 20 days ago (cooling passed)
        self.lead.disbursed_at = datetime.now(UTC) - timedelta(days=20)

        self.lead_repo = _FakeLeadRepository({self.lead_id: self.lead})
        self.withdrawal_repo = _FakeWithdrawalRepository()

        self.service = BonusService(
            session=self.session,
            lead_repository=self.lead_repo,
            withdrawal_repository=self.withdrawal_repo,
        )

    def _create_sample_withdrawal(
        self, status=WithdrawalStatus.PENDING
    ) -> BonusWithdrawal:
        w = BonusWithdrawal(
            id=uuid4(),
            lead_id=self.lead.id,
            user_id=self.user.id,
            loan_type=self.lead.loan_type,
            disbursed_amount=Decimal("1000000.00"),
            commission_rate=Decimal("0.010"),
            gross_bonus=Decimal("10000.00"),
            tds_rate=Decimal("0.050"),
            tds_amount=Decimal("500.00"),
            net_bonus=Decimal("9500.00"),
            cooling_period_end_date=datetime.now(UTC) - timedelta(days=2),
            account_holder_name="Rahul Sharma",
            payout_method="upi",
            upi_id="rahul.sharma@okhdfcbank",
            status=status,
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
        w.lead = self.lead
        w.user = self.user
        w.processed_by = None
        self.withdrawal_repo.withdrawals[w.id] = w
        return w

    def test_schema_admin_process_request_validation(self):
        """Verify AdminProcessWithdrawalRequest validates action types."""
        # Valid process
        req = AdminProcessWithdrawalRequest(
            action="process", transaction_reference="UPI/632410889123"
        )
        self.assertEqual(req.action, "process")
        self.assertEqual(req.transaction_reference, "UPI/632410889123")

        # Valid reject
        req_reject = AdminProcessWithdrawalRequest(
            action="reject", rejection_reason="Invalid UPI VPA handle"
        )
        self.assertEqual(req_reject.action, "reject")
        self.assertEqual(req_reject.rejection_reason, "Invalid UPI VPA handle")

        # Invalid action raises ValidationError
        with self.assertRaises(ValidationError):
            AdminProcessWithdrawalRequest(action="invalid_action")

    def test_admin_get_withdrawals_queue_and_stats(self):
        """Admin can list pending requests and view financial stats."""
        w = self._create_sample_withdrawal(status=WithdrawalStatus.PENDING)

        res = run_coroutine(
            self.service.get_admin_withdrawals(page=1, page_size=10, status=None)
        )
        self.assertEqual(res.total, 1)
        self.assertEqual(len(res.items), 1)

        item = res.items[0]
        self.assertEqual(item.lead_id, self.lead.lead_id)
        self.assertEqual(item.net_bonus, Decimal("9500.00"))
        self.assertEqual(item.tds_amount, Decimal("500.00"))
        self.assertEqual(item.upi_id, "rahul.sharma@okhdfcbank")
        self.assertEqual(item.user.name, "Rahul Sharma")
        self.assertTrue(item.is_cooling_period_passed)

        stats = res.stats
        self.assertEqual(stats.pending_count, 1)
        self.assertEqual(stats.pending_amount, Decimal("9500.00"))
        self.assertEqual(stats.total_tds_withheld, Decimal("500.00"))

    def test_admin_process_payout_with_utr(self):
        """Admin marks pending withdrawal as processed with UPI UTR."""
        w = self._create_sample_withdrawal(status=WithdrawalStatus.PENDING)

        payload = AdminProcessWithdrawalRequest(
            action="process",
            transaction_reference="UPI/632410889123",
            notes="Disbursed via ICICI Corporate UPI",
        )

        res = run_coroutine(
            self.service.admin_process_withdrawal(
                withdrawal_id=w.id,
                payload=payload,
                admin_user=self.admin_user,
            )
        )

        self.assertEqual(res.status, WithdrawalStatus.PROCESSED)
        self.assertEqual(res.transaction_reference, "UPI/632410889123")
        self.assertEqual(res.notes, "Disbursed via ICICI Corporate UPI")
        self.assertEqual(res.processed_by_admin_id, self.admin_user.id)
        self.assertIsNotNone(res.processed_at)
        self.assertTrue(self.session.committed)

    def test_admin_process_requires_transaction_reference(self):
        """Processing a payout without UTR raises ConflictError."""
        w = self._create_sample_withdrawal(status=WithdrawalStatus.PENDING)

        payload = AdminProcessWithdrawalRequest(action="process")

        with self.assertRaises(ConflictError) as ctx:
            run_coroutine(
                self.service.admin_process_withdrawal(
                    withdrawal_id=w.id,
                    payload=payload,
                    admin_user=self.admin_user,
                )
            )
        self.assertIn("Transaction reference / UPI UTR is required", str(ctx.exception))

    def test_admin_reject_payout_with_reason(self):
        """Admin declines pending withdrawal with mandatory rejection reason."""
        w = self._create_sample_withdrawal(status=WithdrawalStatus.PENDING)

        payload = AdminProcessWithdrawalRequest(
            action="reject",
            rejection_reason="UPI ID does not match KYC beneficiary name",
            notes="Please re-submit with correct VPA",
        )

        res = run_coroutine(
            self.service.admin_process_withdrawal(
                withdrawal_id=w.id,
                payload=payload,
                admin_user=self.admin_user,
            )
        )

        self.assertEqual(res.status, WithdrawalStatus.REJECTED)
        self.assertEqual(
            res.rejection_reason, "UPI ID does not match KYC beneficiary name"
        )
        self.assertEqual(res.notes, "Please re-submit with correct VPA")
        self.assertEqual(res.processed_by_admin_id, self.admin_user.id)
        self.assertIsNotNone(res.processed_at)

    def test_admin_reject_requires_reason(self):
        """Rejecting a payout without reason raises ConflictError."""
        w = self._create_sample_withdrawal(status=WithdrawalStatus.PENDING)

        payload = AdminProcessWithdrawalRequest(action="reject")

        with self.assertRaises(ConflictError) as ctx:
            run_coroutine(
                self.service.admin_process_withdrawal(
                    withdrawal_id=w.id,
                    payload=payload,
                    admin_user=self.admin_user,
                )
            )
        self.assertIn("Rejection reason is required", str(ctx.exception))

    def test_prevent_double_processing(self):
        """Attempting to process or reject an already finalized request raises ConflictError."""
        w = self._create_sample_withdrawal(status=WithdrawalStatus.PROCESSED)
        w.transaction_reference = "UPI/12345"

        payload = AdminProcessWithdrawalRequest(
            action="process", transaction_reference="UPI/99999"
        )

        with self.assertRaises(ConflictError) as ctx:
            run_coroutine(
                self.service.admin_process_withdrawal(
                    withdrawal_id=w.id,
                    payload=payload,
                    admin_user=self.admin_user,
                )
            )
        self.assertIn("already been finalized", str(ctx.exception))

    def test_user_can_reapply_after_rejection(self):
        """When an admin rejects a withdrawal, user can re-apply with corrected UPI details."""
        # Setup rejected withdrawal
        w = self._create_sample_withdrawal(status=WithdrawalStatus.REJECTED)
        w.rejection_reason = "Invalid VPA"

        # Check that bonus preview marks lead as eligible again
        preview = self.service.calculate_lead_bonus(lead=self.lead, withdrawal=w)
        self.assertTrue(preview.is_withdrawal_eligible)
        self.assertEqual(preview.withdrawal_status, "rejected")

        # User submits corrected UPI request
        req = WithdrawRequest(
            lead_id=self.lead.lead_id,
            upi_id="rahul.new@oksbi",
            account_holder_name="Rahul Sharma",
        )

        res = run_coroutine(
            self.service.request_withdrawal(payload=req, current_user=self.user)
        )

        self.assertEqual(res.status, WithdrawalStatus.PENDING)
        self.assertEqual(res.upi_id, "rahul.new@oksbi")
        self.assertIsNone(res.rejection_reason)
        self.assertIsNone(res.transaction_reference)


if __name__ == "__main__":
    unittest.main()
