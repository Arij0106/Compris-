"""Schémas Pydantic des requêtes (les réponses sont renvoyées en dict, format du contrat d'API)."""
from typing import Any, Literal
from pydantic import BaseModel, Field


class AnswerIn(BaseModel):
    student_id: str = "student_1"
    question_id: int
    choice_index: int = Field(ge=0, le=3)
    time_spent: float = 0.0  # secondes


class QuizAnswerItem(BaseModel):
    question_id: int | str
    answer: int


class EvaluateIn(BaseModel):
    course_id: int | str | None = None
    course_ids: list[str | int] | str | None = None
    unit_id: int | str
    answers: list[QuizAnswerItem] = []
    student_id: str = "student_1"


class AnalyzeIn(BaseModel):
    course_ids: list[str | int] | str | None = None
    course_id: int | str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tutor"]
    content: str | None = None
    text: str | None = None

    def get_text(self) -> str:
        return self.content or self.text or ""


class ChatIn(BaseModel):
    message: str
    course_id: int | str | None = None
    course_ids: list[str | int] | str | None = None
    student_id: str = "student_1"
    unit_id: str | int | None = None
    history: list[ChatMessage] = []
    hint_level: int = Field(default=1, ge=1, le=4)  # 1 relance, 2 indice précis, 3 exemple analogue, 4 explication
    mode: Literal["socratic", "feynman"] = "socratic"


class ReviewGradeIn(BaseModel):
    student_id: str = "student_1"
    card_id: int
    quality: int = Field(ge=0, le=5)  # 0 = trou noir ... 5 = parfait
