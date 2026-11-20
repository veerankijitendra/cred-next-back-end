from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.db.session import get_db
from app.models.user import User
from app.repositories.bonus_withdrawal import BonusWithdrawalRepository
from app.repositories.lead import LeadRepository
from app.schemas.admin_withdrawal import (
    AdminProcessWithdrawalRequest,
    AdminWithdrawalItemResponse,
    AdminWithdrawalListResponse,
    AdminWithdrawalQuery,
    AdminWithdrawalStats,
)
from app.services.bonus import BonusService

router = APIRouter(prefix="/admin/withdrawals", tags=["Admin - Withdrawals & Payouts"])


def get_bonus_service(session: AsyncSession = Depends(get_db)) -> BonusService:
    return BonusService(
        session=session,
        lead_repository=LeadRepository(session=session),
        withdrawal_repository=BonusWithdrawalRepository(session=session),
    )


@router.get("", response_model=AdminWithdrawalListResponse)
async def get_admin_withdrawals(
    query: AdminWithdrawalQuery = Depends(),
    current_admin: User = Depends(require_admin),
    service: BonusService = Depends(get_bonus_service),
) -> AdminWithdrawalListResponse:
    """Retrieve a paginated list of all partner/borrower withdrawal requests.

    Supports status filters ('pending', 'processed', 'rejected') and search by
    lead ID, borrower/user name, phone number, UPI ID, or transaction reference.
    Accessible only by administrators.
    """
    return await service.get_admin_withdrawals(
        page=query.page,
        page_size=query.page_size,
        status=query.status,
        search=query.search,
    )


@router.get("/stats", response_model=AdminWithdrawalStats)
async def get_admin_withdrawal_stats(
    current_admin: User = Depends(require_admin),
    service: BonusService = Depends(get_bonus_service),
) -> AdminWithdrawalStats:
    """Retrieve aggregate payout statistics: pending payout volume, processed

    disbursements, and cumulative TDS withheld for tax filing. Accessible only
    by administrators.
    """
    return await service.get_admin_withdrawal_stats()


@router.get("/{withdrawal_id}", response_model=AdminWithdrawalItemResponse)
async def get_admin_withdrawal_by_id(
    withdrawal_id: UUID,
    current_admin: User = Depends(require_admin),
    service: BonusService = Depends(get_bonus_service),
) -> AdminWithdrawalItemResponse:
    """Retrieve complete audit details for a specific withdrawal request.

    Accessible only by administrators.
    """
    return await service.get_admin_withdrawal_by_id(withdrawal_id=withdrawal_id)


@router.patch(
    "/{withdrawal_id}/process",
    response_model=AdminWithdrawalItemResponse,
    status_code=status.HTTP_200_OK,
)
async def admin_process_withdrawal(
    withdrawal_id: UUID,
    payload: AdminProcessWithdrawalRequest,
    current_admin: User = Depends(require_admin),
    service: BonusService = Depends(get_bonus_service),
) -> AdminWithdrawalItemResponse:
    """Process a withdrawal request:

    - action='process': Disburse funds and record UPI UTR / Transaction Reference.
    - action='reject': Decline request with mandatory rejection reason.
    Accessible only by administrators.
    """
    return await service.admin_process_withdrawal(
        withdrawal_id=withdrawal_id,
        payload=payload,
        admin_user=current_admin,
    )
