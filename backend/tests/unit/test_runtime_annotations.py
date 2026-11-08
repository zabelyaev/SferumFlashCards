import inspect
from annotationlib import Format
from unittest.mock import AsyncMock, create_autospec

import pytest

from application.accounts.auth.service import AuthService
from application.accounts.users.service import UserService
from application.activity.service import StreakService
from application.flashcards.cards.service import CardService
from application.flashcards.decks.service import DeckService
from application.flashcards.library.service import LibraryService
from application.study.optimization.engine import FsrsOptimizer
from application.study.optimization.service import FsrsOptimizationService
from application.study.services.planner import StudyPlanner
from application.study.services.study import StudyService

SERVICES = [
    AuthService,
    UserService,
    StreakService,
    CardService,
    DeckService,
    LibraryService,
    FsrsOptimizer,
    FsrsOptimizationService,
    StudyPlanner,
    StudyService,
]


@pytest.mark.parametrize("service", SERVICES, ids=lambda service: service.__name__)
def test_service_signatures_do_not_evaluate_type_checking_imports(service) -> None:

    inspect.signature(service, annotation_format=Format.VALUE)
    for member in vars(service).values():
        if isinstance(member, staticmethod):
            member = member.__func__
        if inspect.isfunction(member):
            inspect.signature(member, annotation_format=Format.VALUE)


@pytest.mark.parametrize("service", SERVICES, ids=lambda service: service.__name__)
@pytest.mark.parametrize("autospec", [False, True], ids=["spec", "autospec"])
def test_services_support_mock_introspection(service, autospec: bool) -> None:
    mock = (
        create_autospec(service, instance=True) if autospec else AsyncMock(spec=service)
    )
    assert isinstance(mock, service)
    for name, method in inspect.getmembers(service, inspect.isfunction):
        if not name.startswith("_"):
            assert isinstance(getattr(mock, name), AsyncMock) == (
                inspect.iscoroutinefunction(method)
            )
