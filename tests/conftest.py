from collections.abc import AsyncGenerator
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import async_session_maker
from src.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

