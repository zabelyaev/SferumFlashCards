from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from application.flashcards.cards.database.models import Card
    from application.study.database.models import CardReview

type StudyCandidate = tuple[Card, CardReview | None]


@dataclass(frozen=True)
class CandidateMetadata:
    card_id: int
    order_index: int
    due_date: datetime | None

    @property
    def is_new(self) -> bool:
        return self.due_date is None
