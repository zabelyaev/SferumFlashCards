from application.accounts.users.database.models import User
from application.activity.database.models import UserDailyActivity
from application.flashcards.cards.database.models import Card
from application.flashcards.decks.database.models import Deck
from application.flashcards.library.database.models import UserDeck
from application.study.database.models import (
    CardReview,
    LearningCycle,
    ReviewLog,
    StudyDailyCard,
    StudyDailyUsage,
    StudySession,
    StudySessionCard,
)
from common.database import Base


def test_application_table_names_remain_unchanged() -> None:
    names = {
        User: "users",
        UserDailyActivity: "user_daily_activity",
        Card: "cards",
        Deck: "decks",
        UserDeck: "user_decks",
        CardReview: "card_reviews",
        LearningCycle: "learning_cycles",
        ReviewLog: "review_logs",
        StudySession: "study_sessions",
        StudySessionCard: "study_session_cards",
        StudyDailyCard: "study_daily_cards",
        StudyDailyUsage: "study_daily_usage",
    }
    for model, expected in names.items():
        assert model.__tablename__ == expected
        assert model.__table__.name == expected
    assert set(Base.metadata.tables) == set(names.values())


def test_table_name_suffix_can_be_overridden() -> None:
    class ActivitySummary(Base):
        __abstract__ = True
        _need_s_in_tn_ = False

    class CardSummary(Base):
        __abstract__ = True

    assert ActivitySummary.__tablename__ == "activity_summary"
    assert CardSummary.__tablename__ == "card_summarys"
