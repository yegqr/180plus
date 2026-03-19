from __future__ import annotations

import statistics
from typing import Any, Sequence

from sqlalchemy import String, and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models.results import ExamResult
from infrastructure.database.models.random_results import RandomResult

_PREDICTION_WEIGHTS: dict[int, list[float]] = {
    3: [0.5, 0.3, 0.2],
    4: [0.5, 0.3, 0.15, 0.05],
    5: [0.5, 0.3, 0.1, 0.05, 0.05],
}


def _predict_score(scores: list[int | float]) -> int | str:
    """
    Returns a weighted-average prediction score from the last N results.

    Requires at least 5 scores; returns "-" otherwise.
    Variance penalty: high stdev relative to the mean reduces the prediction.
    """
    if len(scores) < 5:
        return "-"
    weights = _PREDICTION_WEIGHTS.get(len(scores), _PREDICTION_WEIGHTS[5])
    weighted_sum = sum(w * s for w, s in zip(weights, scores))
    stdev = statistics.stdev(scores)
    mean_val = statistics.mean(scores)
    sigma_norm = stdev / mean_val if mean_val > 0 else 0
    return int(weighted_sum * (1 - sigma_norm))


class ResultRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_result(
        self,
        user_id: int,
        subject: str,
        year: int,
        session_name: str,
        raw_score: int,
        nmt_score: int,
        duration: int,
    ) -> None:
        self.session.add(
            ExamResult(
                user_id=user_id,
                subject=subject,
                year=year,
                session=session_name,
                raw_score=raw_score,
                nmt_score=nmt_score,
                duration=duration,
            )
        )
        await self.session.commit()

    async def save_random_result(
        self, user_id: int, subject: str, question_id: int, points: int = 1
    ) -> None:
        self.session.add(
            RandomResult(user_id=user_id, subject=subject, question_id=question_id, points=points)
        )
        await self.session.commit()

    async def get_completed_sessions(
        self, user_id: int, subject: str, year: int
    ) -> set[str]:
        stmt = select(ExamResult.session).where(
            and_(
                ExamResult.user_id == user_id,
                ExamResult.subject == subject,
                ExamResult.year == year,
                ExamResult.duration >= 900,
            )
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def get_last_session_result(
        self, user_id: int, subject: str, session_name: str
    ) -> ExamResult | None:
        """Returns the most recent completed result for this session."""
        stmt = (
            select(ExamResult)
            .where(
                and_(
                    ExamResult.user_id == user_id,
                    ExamResult.subject == subject,
                    ExamResult.session == session_name,
                    ExamResult.raw_score > 0,
                )
            )
            .order_by(desc(ExamResult.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar()

    async def _fetch_subject_stats(
        self, valid_filter: Any, subjects: Sequence[str]
    ) -> list[dict[str, Any]]:
        """Per-subject aggregate stats (avg NMT score, prediction)."""
        result: list[dict[str, Any]] = []
        for subj in subjects:
            subj_filter = and_(valid_filter, ExamResult.subject == subj)
            avg_nmt = (
                await self.session.execute(
                    select(func.avg(func.greatest(ExamResult.nmt_score, 100))).where(subj_filter)
                )
            ).scalar() or 0
            last_5 = (
                await self.session.execute(
                    select(func.greatest(ExamResult.nmt_score, 100))
                    .where(subj_filter)
                    .order_by(desc(ExamResult.created_at))
                    .limit(5)
                )
            ).scalars().all()
            result.append({
                "subject": subj,
                "avg":     int(avg_nmt),
                "median":  _predict_score(list(last_5)),
            })
        return result

    async def _fetch_recent_activity(self, user_id: int, valid_filter: Any) -> list:
        """Returns up to 10 most-recent events merged from simulations and random mode."""
        recent_sims = (
            await self.session.execute(
                select(
                    ExamResult.subject,
                    ExamResult.nmt_score.label("score"),
                    ExamResult.created_at,
                    func.cast("sim", String).label("type"),
                )
                .where(valid_filter)
                .order_by(desc(ExamResult.created_at))
                .limit(10)
            )
        ).all()
        recent_rand = (
            await self.session.execute(
                select(
                    RandomResult.subject,
                    RandomResult.points.label("score"),
                    RandomResult.created_at,
                    func.cast("rand", String).label("type"),
                )
                .where(RandomResult.user_id == user_id)
                .order_by(desc(RandomResult.created_at))
                .limit(10)
            )
        ).all()
        return sorted(
            list(recent_sims) + list(recent_rand),
            key=lambda x: x.created_at,
            reverse=True,
        )[:10]

    async def get_user_stats(self, user_id: int) -> dict[str, Any]:
        valid_filter = ExamResult.user_id == user_id

        sim_count = (
            await self.session.execute(select(func.count(ExamResult.id)).where(valid_filter))
        ).scalar() or 0
        sim_correct_count = (
            await self.session.execute(select(func.sum(ExamResult.raw_score)).where(valid_filter))
        ).scalar() or 0
        rand_count = (
            await self.session.execute(
                select(func.sum(RandomResult.points)).where(RandomResult.user_id == user_id)
            )
        ).scalar() or 0
        avg_duration = (
            await self.session.execute(
                select(func.avg(ExamResult.duration)).where(valid_filter)
            )
        ).scalar() or 0

        subjects = (
            await self.session.execute(
                select(ExamResult.subject).where(valid_filter).distinct()
            )
        ).scalars().all()

        return {
            "total_sims":      sim_count,
            "sim_correct":     int(sim_correct_count),
            "rand_correct":    int(rand_count),
            "total_tests":     int(sim_correct_count) + int(rand_count),
            "subject_stats":   await self._fetch_subject_stats(valid_filter, subjects),
            "avg_duration":    int(avg_duration),
            "recent_activity": await self._fetch_recent_activity(user_id, valid_filter),
        }

    async def get_all_results_for_export(self) -> Sequence[ExamResult]:
        """Fetches all simulation results for CSV export (valid completed sessions only)."""
        stmt = (
            select(ExamResult)
            .where(and_(ExamResult.raw_score > 0, ExamResult.duration.between(300, 10800)))
            .order_by(desc(ExamResult.created_at))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
