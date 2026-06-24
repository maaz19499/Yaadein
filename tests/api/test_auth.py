from datetime import datetime, timedelta, timezone
import uuid
import jwt
import pytest
from fastapi import FastAPI, Depends, status
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.api.deps import get_current_user, get_db
from src.models.user import User

# Setup dummy app for JWT dependency testing
test_app = FastAPI()


@test_app.get("/test-user")
def get_user_route(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "phone": current_user.phone,
        "name": current_user.name,
        "role": current_user.role,
    }


# Dummy User data for matching
MOCK_USER_ID = uuid.uuid4()
MOCK_PHONE = "+919876543210"
MOCK_NAME = "Test User"
MOCK_ROLE = "host"


# Mock DB class to simulate database calls
class MockAsyncSession:
    def __init__(self, should_find_user: bool = True):
        self.should_find_user = should_find_user

    async def execute(self, statement):
        class MockResult:
            def __init__(self, user):
                self.user = user

            def scalar_one_or_none(self):
                return self.user

        if self.should_find_user:
            user = User(
                id=MOCK_USER_ID,
                phone=MOCK_PHONE,
                name=MOCK_NAME,
                role=MOCK_ROLE,
            )
            return MockResult(user)
        else:
            return MockResult(None)


@pytest.fixture
def client_with_user():
    # Dependency override to return a database session that finds the user
    def override_get_db():
        yield MockAsyncSession(should_find_user=True)

    test_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


@pytest.fixture
def client_without_user():
    # Dependency override to return a database session that does not find the user
    def override_get_db():
        yield MockAsyncSession(should_find_user=False)

    test_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def create_token(payload: dict, secret: str = settings.SUPABASE_JWT_SECRET) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


def test_auth_success(client_with_user):
    payload = {
        "sub": str(MOCK_USER_ID),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "role": "authenticated",
    }
    token = create_token(payload)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client_with_user.get("/test-user", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(MOCK_USER_ID)
    assert data["phone"] == MOCK_PHONE
    assert data["name"] == MOCK_NAME
    assert data["role"] == MOCK_ROLE


def test_auth_missing_header(client_with_user):
    response = client_with_user.get("/test-user")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "detail" in response.json()


def test_auth_invalid_signature(client_with_user):
    payload = {
        "sub": str(MOCK_USER_ID),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    token = create_token(payload, secret="invalid_secret")
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client_with_user.get("/test-user", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Signature verification failed" in response.json()["detail"]


def test_auth_expired_token(client_with_user):
    payload = {
        "sub": str(MOCK_USER_ID),
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
    }
    token = create_token(payload)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client_with_user.get("/test-user", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Signature has expired" in response.json()["detail"]


def test_auth_missing_sub(client_with_user):
    payload = {
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    token = create_token(payload)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client_with_user.get("/test-user", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "missing 'sub' claim" in response.json()["detail"]


def test_auth_user_not_found(client_without_user):
    payload = {
        "sub": str(MOCK_USER_ID),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    token = create_token(payload)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client_without_user.get("/test-user", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "User profile not found in public.users" in response.json()["detail"]
