from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class Subject(StrEnum):
    PHYSICS = "physics"
    ALGEBRA = "algebra"
    GEOMETRY = "geometry"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    HISTORY = "history"
    RUSSIAN = "russian"
    INFORMATICS = "informatics"
    ENGLISH = "english"
    OTHER = "other"


class ExamType(StrEnum):
    OGE = "oge"
    EGE = "ege"


class CardReviewState(StrEnum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


class StudySessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
