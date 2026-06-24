import uuid
import jwt
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.database import get_db as get_db
from src.models.user import User
from src.models.guest import Guest

security = HTTPBearer()


class UploadIdentity:
    def __init__(
        self,
        event_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        guest_session_id: uuid.UUID | None = None,
    ):
        self.event_id = event_id
        self.user_id = user_id
        self.guest_session_id = guest_session_id


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        # Decode the Supabase JWT locally
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={
                "verify_aud": False
            },  # Supabase uses custom audience claims (e.g. 'authenticated')
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing 'sub' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch corresponding user profile from public.users
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile not found in public.users.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_upload_identity(
    authorization: str | None = Header(None),
    x_guest_session_id: str | None = Header(None, alias="X-Guest-Session-ID"),
    x_event_id: str | None = Header(None, alias="X-Event-ID"),
    db: AsyncSession = Depends(get_db),
) -> UploadIdentity:
    # 1. Check if standard JWT is provided
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token payload is missing 'sub' claim.",
                )
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User profile not found in public.users.",
                )
            return UploadIdentity(user_id=user.id)
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Could not validate credentials: {str(e)}",
            )

    # 2. Check if Guest Headers are provided
    if x_guest_session_id and x_event_id:
        try:
            guest_session_uuid = uuid.UUID(x_guest_session_id)
            event_uuid = uuid.UUID(x_event_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid UUID format in headers.",
            )

        # Verify guest exists for this event
        guest_result = await db.execute(
            select(Guest).where(
                Guest.event_id == event_uuid,
                Guest.guest_session_id == guest_session_uuid,
            )
        )
        guest = guest_result.scalar_one_or_none()
        if not guest:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Guest session not registered for this event.",
            )

        return UploadIdentity(event_id=event_uuid, guest_session_id=guest_session_uuid)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide either standard Bearer JWT or guest headers (X-Guest-Session-ID and X-Event-ID).",
    )
