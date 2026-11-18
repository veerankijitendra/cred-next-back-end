import logging
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    BONUS_COOLING_PERIOD_WORKING_DAYS,
    BONUS_RATES_BY_LOAN_TYPE,
    TDS_RATE,
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
from app.repositories.bonus_withdrawal import BonusWithdrawalRepository
from app.repositories.lead import LeadRepository
from app.schemas.bonus import (
    BonusBreakdownResponse,
    DisbursedLeadBonusItem,
    UserWithdrawalsSummaryResponse,
    WithdrawalItemResponse,
    WithdrawRequest,
)

logger = logging.getLogger(__name__)


class BonusService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        lead_repository: LeadRepository,
        withdrawal_repository: BonusWithdrawalRepository,
    ) -> None:
        self.session = session
        self.lead_repository = lead_repository
        self.withdrawal_repository = withdrawal_repository

    @staticmethod
    def calculate_lead_bonus(
        *,
        lead: Lead,
        withdrawal: BonusWithdrawal | None = None,
        now: datetime | None = None,
    ) -> BonusBreakdownResponse:
        current_time = now or datetime.now(UTC)
        disbursed_amt = lead.loan_amount
        disbursed_dt = lead.disbursed_at or lead.updated_at or current_time

        commission_rate = BONUS_RATES_BY_LOAN_TYPE.get(
            lead.loan_type, Decimal("0.010")
        )
        gross_bonus = (disbursed_amt * commission_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        tds_amount = (gross_bonus * TDS_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        net_bonus = gross_bonus - tds_amount

        cooling_end = add_working_days(disbursed_dt, BONUS_COOLING_PERIOD_WORKING_DAYS)
        is_cooling_passed = current_time >= cooling_end
        remaining_days = calculate_remaining_working_days(cooling_end, current_time)

        if withdrawal:
            withdrawal_status = withdrawal.status.value
        elif is_cooling_passed:
            withdrawal_status = "ready_for_withdrawal"
        else:
            withdrawal_status = "cooling_period"

        is_eligible = (
            is_cooling_passed
            and (withdrawal is None)
            and (lead.status == LeadStatus.DISBURSED)
        )

        return BonusBreakdownResponse(
            lead_id=lead.lead_id,
            loan_type=lead.loan_type,
            loan_type_label=str(lead.loan_type).replace("_", " ").title(),
            disbursed_amount=disbursed_amt,
            disbursed_at=disbursed_dt,
            commission_rate=commission_rate,
            commission_percent_label=f"{commission_rate * 100:.1f}%",
            gross_bonus=gross_bonus,
            tds_rate=TDS_RATE,
            tds_percent_label=f"{TDS_RATE * 100:.0f}%",
            tds_amount=tds_amount,
            net_bonus=net_bonus,
            cooling_period_working_days=BONUS_COOLING_PERIOD_WORKING_DAYS,
            cooling_period_end_date=cooling_end,
            remaining_working_days=remaining_days,
            is_withdrawal_eligible=is_eligible,
            withdrawal_status=withdrawal_status,
            withdrawal_id=withdrawal.id if withdrawal else None,
        )

    async def get_lead_bonus_preview(
        self, *, lead_id: str, current_user: User
    ) -> BonusBreakdownResponse:
        lead = await self.lead_repository.get_by_lead_id(lead_id=lead_id.strip())
        if lead is None:
            raise NotFoundError("Lead was not found.")

        # Authorization: Must be beneficiary (referred_by or direct applicant) or Admin
        is_beneficiary = (
            lead.referred_by_user_id == current_user.id
            or (lead.referred_by_user_id is None and lead.created_by_user_id == current_user.id)
            or current_user.role in {UserRoleEnum.ADMIN, UserRoleEnum.SUPER_ADMIN}
        )
        if not is_beneficiary:
            raise ForbiddenError(message="You are not authorized to view the bonus for this lead.")

        if lead.status != LeadStatus.DISBURSED:
            raise ConflictError(
                "Lead is not yet disbursed. Bonus is only credited upon successful disbursal."
            )

        withdrawal = await self.withdrawal_repository.get_by_lead_id(lead_id=lead.id)
        return self.calculate_lead_bonus(lead=lead, withdrawal=withdrawal)

    async def request_withdrawal(
        self, *, payload: WithdrawRequest, current_user: User
    ) -> WithdrawalItemResponse:
        lead = await self.lead_repository.get_by_lead_id(lead_id=payload.lead_id.strip())
        if lead is None:
            raise NotFoundError("Lead was not found.")

        # Authorization: Must be beneficiary
        is_beneficiary = (
            lead.referred_by_user_id == current_user.id
            or (lead.referred_by_user_id is None and lead.created_by_user_id == current_user.id)
        )
        if not is_beneficiary:
            raise ForbiddenError(message="You are not authorized to withdraw the bonus for this lead.")

        # Status check
        if lead.status != LeadStatus.DISBURSED:
            raise ConflictError("Lead is not yet disbursed.")

        # Double-withdrawal prevention
        existing = await self.withdrawal_repository.get_by_lead_id(lead_id=lead.id)
        if existing:
            raise ConflictError(
                f"A withdrawal request for this lead has already been submitted (Status: {existing.status.value})."
            )

        # 7 Working Days Cooling Period check
        now = datetime.now(UTC)
        disbursed_dt = lead.disbursed_at or lead.updated_at or now
        cooling_end = add_working_days(disbursed_dt, BONUS_COOLING_PERIOD_WORKING_DAYS)
        if now < cooling_end:
            remaining_days = calculate_remaining_working_days(cooling_end, now)
            raise ConflictError(
                f"Bonus withdrawal is locked during the 7-working-day cooling period. "
                f"Eligible on {cooling_end.strftime('%Y-%m-%d')} ({remaining_days} working days remaining)."
            )

        # Calculate bonus details
        disbursed_amt = lead.loan_amount
        commission_rate = BONUS_RATES_BY_LOAN_TYPE.get(lead.loan_type, Decimal("0.010"))
        gross_bonus = (disbursed_amt * commission_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        tds_amount = (gross_bonus * TDS_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        net_bonus = gross_bonus - tds_amount

        withdrawal = BonusWithdrawal(
            id=uuid4(),
            lead_id=lead.id,
            user_id=current_user.id,
            loan_type=lead.loan_type,
            disbursed_amount=disbursed_amt,
            commission_rate=commission_rate,
            gross_bonus=gross_bonus,
            tds_rate=TDS_RATE,
            tds_amount=tds_amount,
            net_bonus=net_bonus,
            cooling_period_end_date=cooling_end,
            account_holder_name=payload.account_holder_name,
            payout_method=payload.payout_method,
            upi_id=payload.upi_id,
            account_number=payload.account_number,
            ifsc_code=payload.ifsc_code,
            status=WithdrawalStatus.PENDING,
        )

        try:
            await self.withdrawal_repository.create(withdrawal=withdrawal)
            await self.session.commit()
            await self.session.refresh(withdrawal)

            logger.info(
                "Bonus withdrawal requested",
                extra={
                    "event": "bonus.withdrawal_requested",
                    "withdrawal_id": str(withdrawal.id),
                    "lead_id": lead.lead_id,
                    "user_id": str(current_user.id),
                    "payout_method": withdrawal.payout_method,
                    "upi_id": withdrawal.upi_id,
                    "net_bonus": str(net_bonus),
                },
            )

            return WithdrawalItemResponse(
                id=withdrawal.id,
                lead_id=lead.lead_id,
                loan_type=withdrawal.loan_type,
                disbursed_amount=withdrawal.disbursed_amount,
                commission_rate=withdrawal.commission_rate,
                gross_bonus=withdrawal.gross_bonus,
                tds_rate=withdrawal.tds_rate,
                tds_amount=withdrawal.tds_amount,
                net_bonus=withdrawal.net_bonus,
                status=withdrawal.status,
                payout_method=withdrawal.payout_method,
                upi_id=withdrawal.upi_id,
                account_number=withdrawal.account_number,
                ifsc_code=withdrawal.ifsc_code,
                account_holder_name=withdrawal.account_holder_name,
                cooling_period_end_date=withdrawal.cooling_period_end_date,
                created_at=withdrawal.created_at,
                transaction_reference=withdrawal.transaction_reference,
            )
        except Exception:
            await self.session.rollback()
            raise

    async def get_user_disbursed_leads(
        self, *, current_user: User
    ) -> list[DisbursedLeadBonusItem]:
        # Query all disbursed leads where user is beneficiary
        stmt = (
            select(Lead)
            .where(
                Lead.status == LeadStatus.DISBURSED,
                or_(
                    Lead.referred_by_user_id == current_user.id,
                    (Lead.referred_by_user_id.is_(None) & (Lead.created_by_user_id == current_user.id)),
                ),
            )
            .order_by(Lead.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        leads = list(result.scalars().all())

        lead_ids = [l.id for l in leads]
        withdrawals_map = await self.withdrawal_repository.get_by_lead_ids(lead_ids=lead_ids)

        items = []
        for lead in leads:
            withdrawal = withdrawals_map.get(lead.id)
            bonus_calc = self.calculate_lead_bonus(lead=lead, withdrawal=withdrawal)
            items.append(
                DisbursedLeadBonusItem(
                    lead_id=lead.lead_id,
                    borrower_name=lead.full_name,
                    loan_type=lead.loan_type,
                    disbursed_amount=lead.loan_amount,
                    disbursed_at=lead.disbursed_at or lead.updated_at or datetime.now(UTC),
                    bonus=bonus_calc,
                )
            )
        return items

    async def get_user_withdrawals_summary(
        self, *, current_user: User
    ) -> UserWithdrawalsSummaryResponse:
        disbursed_items = await self.get_user_disbursed_leads(current_user=current_user)
        withdrawals = await self.withdrawal_repository.get_user_withdrawals(
            user_id=current_user.id
        )

        total_earned = Decimal("0.00")
        total_tds = Decimal("0.00")
        pending_cooling = Decimal("0.00")
        available_withdrawal = Decimal("0.00")
        eligible_leads_count = 0

        for item in disbursed_items:
            bonus = item.bonus
            total_earned += bonus.net_bonus
            total_tds += bonus.tds_amount

            if bonus.is_withdrawal_eligible:
                available_withdrawal += bonus.net_bonus
                eligible_leads_count += 1
            elif bonus.withdrawal_status == "cooling_period":
                pending_cooling += bonus.net_bonus

        total_withdrawn = Decimal("0.00")
        for w in withdrawals:
            if w.status in {WithdrawalStatus.APPROVED, WithdrawalStatus.PROCESSED}:
                total_withdrawn += w.net_bonus

        return UserWithdrawalsSummaryResponse(
            total_earned_bonus=total_earned,
            total_tds_deducted=total_tds,
            total_withdrawn=total_withdrawn,
            pending_cooling_bonus=pending_cooling,
            available_for_withdrawal=available_withdrawal,
            eligible_leads_count=eligible_leads_count,
        )

    async def get_user_withdrawals_history(
        self, *, current_user: User, page: int = 1, page_size: int = 20
    ) -> tuple[list[WithdrawalItemResponse], int]:
        withdrawals, total = await self.withdrawal_repository.get_user_withdrawals_paginated(
            user_id=current_user.id, page=page, page_size=page_size
        )
        lead_ids = [w.lead_id for w in withdrawals]
        stmt = select(Lead).where(Lead.id.in_(lead_ids))
        res = await self.session.execute(stmt)
        leads_map = {l.id: l.lead_id for l in res.scalars().all()}

        items = [
            WithdrawalItemResponse(
                id=w.id,
                lead_id=leads_map.get(w.lead_id, str(w.lead_id)),
                loan_type=w.loan_type,
                disbursed_amount=w.disbursed_amount,
                commission_rate=w.commission_rate,
                gross_bonus=w.gross_bonus,
                tds_rate=w.tds_rate,
                tds_amount=w.tds_amount,
                net_bonus=w.net_bonus,
                status=w.status,
                payout_method=w.payout_method,
                upi_id=w.upi_id,
                account_number=w.account_number,
                ifsc_code=w.ifsc_code,
                account_holder_name=w.account_holder_name,
                cooling_period_end_date=w.cooling_period_end_date,
                created_at=w.created_at,
                transaction_reference=w.transaction_reference,
            )
            for w in withdrawals
        ]
        return items, total
