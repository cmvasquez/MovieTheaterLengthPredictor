from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Optional


@dataclass
class Prediction:
    predicted_end_date: Optional[date]
    days_total: Optional[int]
    days_elapsed: Optional[int]
    days_remaining: Optional[int]
    confidence: float  # 0..1
    rationale: str


def parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def predict_run_length_days(movie: Dict, today: Optional[date] = None) -> Prediction:
    """Heuristic prediction of theatrical run length in days.

    Inputs: TMDb movie dict with keys: release_date, popularity, vote_count, vote_average.
    """
    today = today or date.today()
    rd = parse_date(movie.get("release_date"))
    if not rd:
        return Prediction(None, None, None, None, 0.2, "Missing release date; cannot predict")

    # Base run length in the US for wide releases tends to be ~35-45 days nowadays under shifting windows.
    base = 38.0

    popularity = float(movie.get("popularity") or 0.0)
    vote_count = float(movie.get("vote_count") or 0.0)
    vote_avg = float(movie.get("vote_average") or 0.0)

    # Normalize heuristics
    pop_bonus = _clamp(popularity / 100.0, 0.0, 0.6) * 30.0  # up to +18 days
    votes_bonus = _clamp(vote_count / 5000.0, 0.0, 0.5) * 20.0  # up to +10 days
    rating_bonus = ((vote_avg - 5.0) / 5.0)  # -1..+1 range roughly
    rating_bonus = _clamp(rating_bonus, -1.0, 1.0) * 8.0  # -8..+8 days

    # Early release penalty if it's already old
    days_since_release = (today - rd).days
    age_penalty = 0.0
    if days_since_release > 60:
        age_penalty = _clamp((days_since_release - 60) / 60.0, 0.0, 1.0) * 15.0  # up to -15 days

    predicted_total = base + pop_bonus + votes_bonus + rating_bonus - age_penalty
    predicted_total = int(round(_clamp(predicted_total, 14.0, 120.0)))  # clamp to [2 weeks, 4 months]

    days_elapsed = max(0, days_since_release)
    days_remaining = max(0, predicted_total - days_elapsed)
    end_date = rd + timedelta(days=predicted_total)

    # Confidence grows with data volume and recency
    confidence = 0.4
    confidence += _clamp(vote_count / 2000.0, 0.0, 0.3)
    confidence += _clamp(popularity / 150.0, 0.0, 0.2)
    if days_elapsed >= 7:
        confidence += 0.05
    confidence = float(_clamp(confidence, 0.2, 0.95))

    rationale = (
        f"base={base:.0f}, pop={popularity:.1f}, votes={vote_count:.0f}, rating={vote_avg:.1f}, "
        f"age_days={days_elapsed}, total≈{predicted_total}"
    )

    return Prediction(
        predicted_end_date=end_date,
        days_total=predicted_total,
        days_elapsed=days_elapsed,
        days_remaining=days_remaining,
        confidence=confidence,
        rationale=rationale,
    )
