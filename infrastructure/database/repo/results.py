from sqlalchemy import select, and_, func, desc, String
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.models.results import ExamResult
from infrastructure.database.models.random_results import RandomResult
import statistics

class ResultRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_result(self, user_id: int, subject: str, year: int, session_name: str, 
                          raw_score: int, nmt_score: int, duration: int):
        result = ExamResult(
            user_id=user_id,
            subject=subject,
            year=year,
            session=session_name,
            raw_score=raw_score,
            nmt_score=nmt_score,
            duration=duration
        )
        self.session.add(result)
        await self.session.commit()

    async def save_random_result(self, user_id: int, subject: str, question_id: int, points: int = 1):
        result = RandomResult(
            user_id=user_id,
            subject=subject,
            question_id=question_id,
            points=points
        )
        self.session.add(result)
        await self.session.commit()

    async def get_completed_sessions(self, user_id: int, subject: str, year: int) -> set[str]:
        stmt = select(ExamResult.session).where(
            and_(
                ExamResult.user_id == user_id,
                ExamResult.subject == subject,
                ExamResult.year == year,
                ExamResult.duration >= 900
            )
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def get_last_session_result(self, user_id: int, subject: str, session_name: str) -> ExamResult | None:
        """Returns the most recent COMPLETED result for this session."""
        stmt = select(ExamResult).where(
            and_(
                ExamResult.user_id == user_id,
                ExamResult.subject == subject,
                ExamResult.session == session_name,
                ExamResult.raw_score > 0 # Assume completed if score > 0
            )
        ).order_by(desc(ExamResult.created_at)).limit(1)
        
        result = await self.session.execute(stmt)
        return result.scalar()

    async def get_user_stats(self, user_id: int):
        # Filter condition: Show ALL results (even 0 score, short duration)
        # We rely on simulation.py to only save meaningful sessions (at least 1 answer).
        valid_sim_filter = (ExamResult.user_id == user_id)

        # 1. Total Simulations
        sim_stmt = select(func.count(ExamResult.id)).where(valid_sim_filter)
        sim_count = (await self.session.execute(sim_stmt)).scalar() or 0

        # 2. Correct Questions in Simulations (Sum of raw_score)
        raw_score_stmt = select(func.sum(ExamResult.raw_score)).where(valid_sim_filter)
        sim_correct_count = (await self.session.execute(raw_score_stmt)).scalar() or 0

        # 3. Total Random Correct (Sum of points)
        rand_stmt = select(func.sum(RandomResult.points)).where(RandomResult.user_id == user_id)
        rand_count = (await self.session.execute(rand_stmt)).scalar() or 0

        # 4. Per Subject Stats
        subj_stmt = select(ExamResult.subject).where(valid_sim_filter).distinct()
        subjects = (await self.session.execute(subj_stmt)).scalars().all()

        subject_stats = []
        for subj in subjects:
            subj_filter = and_(
                valid_sim_filter,
                ExamResult.subject == subj
            )

            # Avg score (treat any score < 100 as 100)
            avg_stmt = select(func.avg(func.greatest(ExamResult.nmt_score, 100))).where(subj_filter)
            avg_nmt = (await self.session.execute(avg_stmt)).scalar() or 0

            # Last 5 for median (NMT scores, treat < 100 as 100)
            last_5_stmt = select(func.greatest(ExamResult.nmt_score, 100)).where(
                subj_filter
            ).order_by(desc(ExamResult.created_at)).limit(5)
            last_5_scores = (await self.session.execute(last_5_stmt)).scalars().all()
            
            # Prediction Model Logic
            # Only if we have at least 5 attempts to calculate stdev and trend
            prediction_score = "-"
            if len(last_5_scores) >= 5:
                scores = last_5_scores # Newest first: [s1, s2, s3, s4, s5]
                n = len(scores)
                
                # Weights assignment
                # If 5: [0.5, 0.3, 0.1, 0.05, 0.05] or similar custom logic
                # Formula requirement: w_i.
                # Let's dynamically assign weights prioritizing recent ones.
                # Simple exponential decay or custom per user request: "last 0.5, pre-last 0.3, pre-pre-last... remainder"
                
                weights = []
                if n == 3:
                    weights = [0.5, 0.3, 0.2]
                elif n == 4:
                     weights = [0.5, 0.3, 0.15, 0.05]
                else: 
                     # n >= 5. Last 5 were fetched.
                     weights = [0.5, 0.3, 0.1, 0.05, 0.05]
                
                # Calculate Weighted Sum (S_w)
                # scores are Newest->Oldest. weights align with them (0.5 for newest).
                weighted_sum = sum(w * s for w, s in zip(weights, scores))
                
                # Calculate Normalized Standard Deviation (Sigma_norm)
                stdev = statistics.stdev(scores)
                mean_val = statistics.mean(scores)
                
                sigma_norm = 0
                if mean_val > 0:
                    sigma_norm = stdev / mean_val
                
                # Formula: P = S_w * (1 - sigma_norm)
                # Limit - sigma_norm shouldn't make it negative or too low drastically?
                # Usually (1 - sigma) implies penalty for volatility.
                # If sigma is large (e.g. scores 120, 180, 120), stdev is ~34, mean 140. sigma ~ 0.24. 
                # P = ... * 0.76.
                
                predicted_val = weighted_sum * (1 - sigma_norm)
                prediction_score = int(predicted_val)

            subject_stats.append({
                "subject": subj,
                "avg": int(avg_nmt),
                "median": prediction_score
            })

        # 5. Average Duration
        duration_stmt = select(func.avg(ExamResult.duration)).where(valid_sim_filter)
        avg_duration = (await self.session.execute(duration_stmt)).scalar() or 0

        # 6. Recent Activity Log (last 10)
        # Fetch simulations
        recent_sims_stmt = select(
            ExamResult.subject, 
            ExamResult.nmt_score.label("score"), 
            ExamResult.created_at,
            func.cast("sim", String).label("type")
        ).where(valid_sim_filter).order_by(desc(ExamResult.created_at)).limit(10)
        recent_sims = (await self.session.execute(recent_sims_stmt)).all()

        # Fetch randoms
        recent_rand_stmt = select(
            RandomResult.subject,
            RandomResult.points.label("score"),
            RandomResult.created_at,
            func.cast("rand", String).label("type")
        ).where(RandomResult.user_id == user_id).order_by(desc(RandomResult.created_at)).limit(10)
        recent_rand = (await self.session.execute(recent_rand_stmt)).all()

        # Merge and sort
        all_activity = sorted(
            list(recent_sims) + list(recent_rand),
            key=lambda x: x.created_at,
            reverse=True
        )[:10]

        return {
            "total_sims": sim_count,
            "sim_correct": int(sim_correct_count),
            "rand_correct": int(rand_count),
            "total_tests": int(sim_correct_count) + int(rand_count),
            "subject_stats": subject_stats,
            "avg_duration": int(avg_duration),
            "recent_activity": all_activity
        }

    async def get_all_results_for_export(self):
        """
        Fetches all simulation results for CSV export.
        """
        # Filter for valid completed simulations (> 5 min)
        stmt = select(ExamResult).where(
            and_(
                ExamResult.raw_score > 0,
                ExamResult.duration.between(300, 10800)
            )
        ).order_by(desc(ExamResult.created_at))
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
