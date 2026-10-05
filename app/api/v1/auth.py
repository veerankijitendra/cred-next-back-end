from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.constants import OTPChannel
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    ResendOTPRequest,
    TokenResponse,
    UserResponse,
    VerifyOTPRequest,
)
from app.services.auth import AuthService
from app.services.notification import NotificationService
from app.services.otp import OTPService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    data: RegisterRequest, session: AsyncSession = Depends(get_db)
) -> RegisterResponse:
    service = AuthService(session=session)

    result = await service.register_user(data=data)

    return result


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    data: LoginRequest, session: AsyncSession = Depends(get_db)
) -> TokenResponse:
    service = AuthService(session=session)

    (access_token, refresh_token) = await service.login_user(
        email=data.email, password=data.password
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh(data: RefreshTokenRequest, session: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token)

    if payload.get("type") == "refresh":
        raise UnauthorizedError(message="Invalid refresh token")

    user_id = payload.get("sub")

    if not user_id:
        raise UnauthorizedError(message="Invalid refresh token")

    service = AuthService(session=session)

    access_token, new_refresh_token = await service.refresh_tokens(
        user_id=user_id, refresh_token=data.refresh_token
    )

    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post("/verify-otp", status_code=status.HTTP_200_OK)
async def verify_otp(data: VerifyOTPRequest, session: AsyncSession = Depends(get_db)):
    user_repository = UserRepository(session=session)

    user = await user_repository.get_by_id(user_id=data.user_id)

    if not user:
        raise UnauthorizedError(message="Invalid verification request")

    if user.is_verified:
        return {"success": True, "message": "Account is already verified."}

    otp_service = OTPService(session=session)

    await otp_service.verify(user_id=user.id, channel=data.channel, otp=data.otp)

    user.is_verified = True

    await session.commit()

    return {
        "success": True,
        "message": "Account verified successfully",
    }


@router.post("/resend-otp")
async def resend_otp(data: ResendOTPRequest, session: AsyncSession = Depends(get_db)):
    user_repository = UserRepository(session=session)

    user = await user_repository.get_by_id(user_id=data.user_id)

    if not user:
        raise UnauthorizedError(message="Invalid verification request")

    if user.is_verified:
        return {"success": True, "message": "Account is already verified"}

    otp_service = OTPService(session=session)

    otp = await otp_service.resend(user_id=user.id, channel=data.channel)

    notification_service = NotificationService()

    destination = user.phone_number if data.channel == OTPChannel.PHONE else user.email

    await notification_service.send_otp(
        destination=destination, otp=otp, channel=data.channel
    )

    await session.commit()

    return {"success": True, "message": "OTP sent successfully"}
