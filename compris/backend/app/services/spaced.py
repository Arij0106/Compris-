"""Répétition espacée — algorithme SM-2."""
from datetime import date, timedelta

from app.models import ReviewCard


def apply_sm2(card: ReviewCard, quality: int, today: date | None = None) -> ReviewCard:
    today = today or date.today()
    q = max(0, min(5, quality))
    if q < 3:
        card.repetitions = 0
        card.interval_days = 1
    else:
        if card.repetitions == 0:
            card.interval_days = 1
        elif card.repetitions == 1:
            card.interval_days = 6
        else:
            card.interval_days = max(1, round(card.interval_days * card.ease))
        card.repetitions += 1
    card.ease = max(1.3, card.ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    card.due_date = today + timedelta(days=card.interval_days)
    return card
