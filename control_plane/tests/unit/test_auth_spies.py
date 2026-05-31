import uuid
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from app.auth.schemas import RegisterPasswordRequest
from app.auth.user_auth_service import UserAuthService
from app.auth.user_repository import UserAccountRecord, UserAuthRepository


@pytest.mark.asyncio
async def test_register_calls_repo_create():
    repo = MagicMock(spec=UserAuthRepository)
    repo.get_user_by_email = AsyncMock(return_value=None)
    created = UserAccountRecord(
        user_id=str(uuid.uuid4()), email="a@x.com", password_hash="scrypt$x$y"
    )
    repo.create_user = AsyncMock(return_value=created)
    repo.get_user_by_id = AsyncMock(return_value=created)
    repo.list_social_providers = AsyncMock(return_value=[])

    svc = UserAuthService(repository=repo)
    await svc.register_password(RegisterPasswordRequest(email="A@X.com", password="password123"))

    repo.create_user.assert_awaited_once()
    repo.create_user.assert_awaited_with(email="a@x.com", password_hash=ANY)
