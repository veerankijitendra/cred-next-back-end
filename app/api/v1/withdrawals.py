from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.db.session import get_db
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
from app.services.bonus import BonusService

router = APIRouter(prefix="/withdrawals", tags=["Withdrawals & Bonus"])


def get_bonus_service(session: AsyncSession = Depends(get_db)) -> BonusService:
    return BonusService(
        session=session,
        lead_repository=LeadRepository(session=session),
        withdrawal_repository=BonusWithdrawalRepository(session=session),
    )


@router.get(
    "/lead/{lead_id}",
    response_model=BonusBreakdownResponse,
    status_code=status.HTTP_200_OK,
)
async def get_lead_bonus_preview(
    lead_id: str,
    current_user: User = Depends(get_current_user),
    service: BonusService = Depends(get_bonus_service),
) -> BonusBreakdownResponse:
    """Fetch bonus breakdown, TDS deduction, and 7-working-day cooling period

    status for a disbursed lead.
    """
    return await service.get_lead_bonus_preview(
        lead_id=lead_id, current_user=current_user
    )


@router.post(
    "",
    response_model=WithdrawalItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_bonus_withdrawal(
    payload: WithdrawRequest,
    current_user: User = Depends(get_current_user),
    service: BonusService = Depends(get_bonus_service),
) -> WithdrawalItemResponse:
    """Submit a bonus withdrawal request for an eligible disbursed lead.

    Enforces 7 working days cooling period and prevents duplicate withdrawals.
    """
    return await service.request_withdrawal(
        payload=payload, current_user=current_user
    )


@router.get(
    "/summary",
    response_model=UserWithdrawalsSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_withdrawals_summary(
    current_user: User = Depends(get_current_user),
    service: BonusService = Depends(get_bonus_service),
) -> UserWithdrawalsSummaryResponse:
    """Get the authenticated user's lifetime earned bonus, TDS deductions,

    pending cooling amounts, and available balance for withdrawal.
    """
    return await service.get_user_withdrawals_summary(current_user=current_user)


@router.get(
    "/disbursed-leads",
    response_model=list[DisbursedLeadBonusItem],
    status_code=status.HTTP_200_OK,
)
async def get_disbursed_leads_with_bonus(
    current_user: User = Depends(get_current_user),
    service: BonusService = Depends(get_bonus_service),
) -> list[DisbursedLeadBonusItem]:
    """List all disbursed leads for the user with calculated bonuses and

    withdrawal readiness.
    """
    return await service.get_user_disbursed_leads(current_user=current_user)


@router.get(
    "/history",
    response_model=list[WithdrawalItemResponse],
    status_code=status.HTTP_200_OK,
)
async def get_withdrawals_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: BonusService = Depends(get_bonus_service),
) -> list[WithdrawalItemResponse]:
    """Get paginated history of past bonus withdrawal requests."""
    items, _ = await service.get_user_withdrawals_history(
        current_user=current_user, page=page, page_size=page_size
    )
    return items
