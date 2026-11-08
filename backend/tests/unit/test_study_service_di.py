from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from application.accounts.users.database.models import User
from application.activity.service import StreakService
from application.study.contracts.inputs import StudySessionCreateInput
from application.study.contracts.outputs import StudyNoWorkOutput
from application.study.contracts.types import DailyUsage
from application.study.services.planner import StudyPlanner
from application.study.services.study import StudyService
from common.config.study import StudyConfig
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.not_found import NotFoundError


async def test_study_binds_injected_streak_service_to_current_uow(profile) -> None:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    user = User(**profile.model_dump())
    uow.users.get_by_id.return_value = user
    uow.repo.lock_deck.return_value = object()
    uow.repo.active_for_deck.return_value = None
    uow.repo.membership.return_value = object()
    uow.repo.used.return_value = DailyUsage(frozenset(), frozenset())
    uow.repo.candidate_batch.return_value = []
    uow.repo.candidates_by_ids.return_value = []
    uow.repo.deck_has_cards.return_value = False
    streaks = AsyncMock(spec=StreakService)

    def bind(repo):
        uow.__aenter__.assert_awaited_once()
        uow.commit.assert_not_awaited()
        assert repo is uow.activity
        return streaks

    factory = MagicMock(side_effect=bind)
    planner = MagicMock(wraps=StudyPlanner(StudyConfig()))
    result = await StudyService(
        lambda: uow, streak_factory=factory, planner=planner
    ).open_session(user.id, StudySessionCreateInput(deck_id=1))
    assert isinstance(result, StudyNoWorkOutput)
    assert result.reason == "empty_deck"
    uow.users.get_by_id.assert_awaited_once_with(user.id, no_key_update=True)
    factory.assert_called_once_with(uow.activity)
    streaks.ensure_current.assert_awaited_once_with(user, ANY)
    streaks.recalculate.assert_not_awaited()
    planner.study_day.assert_called_once_with(ANY, user.timezone)
    uow.repo.used.assert_awaited_once()
    uow.commit.assert_awaited_once()


@pytest.mark.parametrize("missing", [True, False])
async def test_study_rejects_missing_or_disabled_user_before_work(
    profile, missing: bool
) -> None:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    if missing:
        uow.users.get_by_id.side_effect = NotFoundError("User with id 7 not found.")
    else:
        user = User(**profile.model_dump())
        user.is_active = False
        uow.users.get_by_id.return_value = user
    factory = MagicMock()
    service = StudyService(
        lambda: uow, streak_factory=factory, planner=StudyPlanner(StudyConfig())
    )
    error = NotFoundError if missing else ForbiddenError
    expected = "User not found\\." if missing else "User is disabled\\."
    with pytest.raises(error, match=expected):
        await service.open_session(7, StudySessionCreateInput(deck_id=1))
    uow.users.get_by_id.assert_awaited_once_with(7, no_key_update=True)
    uow.repo.lock_deck.assert_not_awaited()
    uow.commit.assert_not_awaited()
    factory.assert_not_called()
