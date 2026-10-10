from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.constants import OTPChannel
from app.core.config import settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    LoginRequest,
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


def _require_trusted_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is None or origin.rstrip("/") not in settings.trusted_origins:
        raise ForbiddenError(message="A trusted Origin header is required.")


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.use_secure_refresh_cookie,
        samesite=settings.refresh_cookie_samesite,
        path="/api/v1/auth",
        domain=settings.refresh_cookie_domain,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.use_secure_refresh_cookie,
        samesite=settings.refresh_cookie_samesite,
        path="/api/v1/auth",
        domain=settings.refresh_cookie_domain,
    )


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
    data: LoginRequest, request: Request, response: Response, session: AsyncSession = Depends(get_db)
) -> TokenResponse:
    _require_trusted_origin(request)
    service = AuthService(session=session)

    access_token, refresh_token = await service.login_user(
        email=data.email, password=data.password
    )

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh(request: Request, response: Response, session: AsyncSession = Depends(get_db)):
    _require_trusted_origin(request)
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        raise UnauthorizedError(message="Refresh session is required.")
    service = AuthService(session=session)
    access_token, new_refresh_token = await service.refresh_tokens(refresh_token=refresh_token)
    _set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_db)):
    _require_trusted_origin(request)
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    await AuthService(session=session).logout_user(refresh_token=refresh_token)
    _clear_refresh_cookie(response)
    return {"success": True, "message": "Session logged out."}


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

    delivered = await notification_service.send_otp(
        destination=destination, otp=otp, channel=data.channel
    )

    await session.commit()

    if not delivered:
        return {"success": False, "message": "OTP delivery is not configured."}
    return {"success": True, "message": "OTP sent successfully"}
