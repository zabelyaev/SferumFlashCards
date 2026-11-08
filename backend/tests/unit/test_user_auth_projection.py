from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.dependencies.auth import CurrentUserDep
from api.dependencies.services import get_user_service
from application.accounts.users.contracts.outputs import CurrentUserOutput
from application.accounts.users.service import UserService
from application.activity.service import StreakService
from main import create_app


async def test_current_user_dependency_keeps_fastapi_request_cache() -> None:
    app = FastAPI()
    service = AsyncMock(spec=UserService)
    service.get_current.return_value = CurrentUserOutput(id=7, is_active=True)
    app.dependency_overrides[get_user_service] = lambda: service

    @app.get("/cached-user")
    async def cached_user(
        first: CurrentUserDep, second: CurrentUserDep
    ) -> dict[str, int]:
        assert first is second
        return {"id": first.id}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(2):
            response = await client.get("/cached-user", headers={"X-VK-User-ID": "123"})
            assert response.status_code == 200
            assert response.json() == {"id": 7}
    assert service.get_current.await_count == 2


@pytest.mark.parametrize("active", [None, False, True])
async def test_profile_auth_accepts_projection_and_preserves_statuses(
    active: bool | None, app_headers, profile
) -> None:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.users.find_current_by_vk_id.return_value = (
        None if active is None else CurrentUserOutput(id=7, is_active=active)
    )
    service = UserService(lambda: uow, streak_factory=StreakService)
    service.get_profile = AsyncMock(return_value=profile)
    app = create_app()
    app.dependency_overrides[get_user_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/users/me/profile", headers={**app_headers, "X-VK-User-ID": "123"}
        )
    assert response.status_code == (401 if active is None else 200 if active else 403)
    uow.users.find_current_by_vk_id.assert_awaited_once_with(123)
    uow.users.find_by_vk_id.assert_not_awaited()
    if active:
        service.get_profile.assert_awaited_once_with(7)
        assert response.json() == profile.model_dump(mode="json")
    else:
        service.get_profile.assert_not_awaited()
