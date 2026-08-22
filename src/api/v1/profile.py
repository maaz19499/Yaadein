from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db
from src.models.event import Event
from src.models.user import User, AuthUser
from src.schemas.auth import UserProfileResponse, UserProfileUpdate

router = APIRouter(tags=["auth"])


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    # Get user email and meta from AuthUser
    auth_user_res = await db.execute(select(AuthUser).where(AuthUser.id == current_user.id))
    auth_user = auth_user_res.scalar_one_or_none()
    
    email = None
    avatar_url = None
    if auth_user and auth_user.raw_user_meta_data:
        email = auth_user.raw_user_meta_data.get("email")
        avatar_url = auth_user.raw_user_meta_data.get("avatar_url")

    # Count events created
    count_res = await db.execute(
        select(func.count(Event.id)).where(Event.host_id == current_user.id)
    )
    events_count = count_res.scalar() or 0

    return UserProfileResponse(
        id=current_user.id,
        email=email or current_user.phone,
        name=current_user.name or (auth_user.raw_user_meta_data.get("name") if auth_user and auth_user.raw_user_meta_data else "User"),
        avatar_url=avatar_url,
        plan="premium" if current_user.role in ("photographer", "admin") else "starter",
        events_created=events_count,
    )


@router.patch("/profile", response_model=UserProfileResponse)
async def update_user_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    if payload.name is not None:
        current_user.name = payload.name

    auth_user_res = await db.execute(select(AuthUser).where(AuthUser.id == current_user.id))
    auth_user = auth_user_res.scalar_one_or_none()

    if auth_user and payload.avatar_url is not None:
        meta = dict(auth_user.raw_user_meta_data or {})
        meta["avatar_url"] = payload.avatar_url
        auth_user.raw_user_meta_data = meta
        db.add(auth_user)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return await get_user_profile(current_user, db)
