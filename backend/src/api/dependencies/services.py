from typing import Annotated

from fastapi import Depends

from api.dependencies.database import SessionFactoryDep
from application.accounts.auth.service import AuthService
from application.accounts.database.sqla_uow import SQLAUnitOfWorkFactory
from application.accounts.database.uow import AccountsUnitOfWorkFactory
from application.accounts.users.service import UserService
from application.activity.service import StreakService
from application.flashcards.cards.service import CardService
from application.flashcards.database.sqla_uow import SQLAFlashcardsUnitOfWorkFactory
from application.flashcards.database.uow import FlashcardsUnitOfWorkFactory
from application.flashcards.decks.service import DeckService
from application.flashcards.library.service import LibraryService
from application.study.database.sqla_uow import SQLAStudyUnitOfWorkFactory
from application.study.services.planner import StudyPlanner
from application.study.services.study import StudyService
from common.config import settings


def get_accounts_uow_factory(
    session_factory: SessionFactoryDep,
) -> AccountsUnitOfWorkFactory:
    return SQLAUnitOfWorkFactory(session_factory)


def get_auth_service() -> AuthService:
    return AuthService(settings.auth.app_key)  # type: ignore


def get_user_service(uow_factory: AccountsUnitOfWorkFactoryDep) -> UserService:
    return UserService(uow_factory, streak_factory=StreakService)


def get_flashcards_uow_factory(
    session_factory: SessionFactoryDep,
) -> FlashcardsUnitOfWorkFactory:
    return SQLAFlashcardsUnitOfWorkFactory(session_factory)


def get_deck_service(uow_factory: FlashcardsUnitOfWorkFactoryDep) -> DeckService:
    return DeckService(uow_factory)


def get_card_service(uow_factory: FlashcardsUnitOfWorkFactoryDep) -> CardService:
    return CardService(uow_factory)


def get_library_service(uow_factory: FlashcardsUnitOfWorkFactoryDep) -> LibraryService:
    return LibraryService(uow_factory)


def get_study_service(session_factory: SessionFactoryDep) -> StudyService:
    return StudyService(
        SQLAStudyUnitOfWorkFactory(session_factory),
        streak_factory=StreakService,
        planner=StudyPlanner(settings.study),
    )


type AccountsUnitOfWorkFactoryDep = Annotated[
    AccountsUnitOfWorkFactory, Depends(get_accounts_uow_factory)
]
type AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
type UserServiceDep = Annotated[UserService, Depends(get_user_service)]
type FlashcardsUnitOfWorkFactoryDep = Annotated[
    FlashcardsUnitOfWorkFactory, Depends(get_flashcards_uow_factory)
]
type DeckServiceDep = Annotated[DeckService, Depends(get_deck_service)]
type CardServiceDep = Annotated[CardService, Depends(get_card_service)]
type LibraryServiceDep = Annotated[LibraryService, Depends(get_library_service)]
type StudyServiceDep = Annotated[StudyService, Depends(get_study_service)]
