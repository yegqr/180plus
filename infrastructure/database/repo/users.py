from typing import Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import update, func

from infrastructure.database.models import User
from infrastructure.database.repo.base import BaseRepo


class UserRepo(BaseRepo):
    async def get_or_create_user(
        self,
        user_id: int,
        full_name: str,
        language: str,
        is_admin: bool = False,
        username: Optional[str] = None,
    ):
        """
        Creates or updates a new user in the database and returns the user object.
        :param user_id: The user's ID.
        :param full_name: The user's full name.
        :param language: The user's language.
        :param is_admin: Whether the user is an admin.
        :param username: The user's username. It's an optional parameter.
        :return: User object, None if there was an error while making a transaction.
        """

        stmt = insert(User).values(
            user_id=user_id,
            username=username,
            full_name=full_name,
            language=language,
            is_admin=is_admin,
        )

        insert_stmt = stmt.on_conflict_do_update(
            index_elements=[User.user_id],
            set_=dict(
                username=username,
                full_name=full_name,
                # We don't overwrite is_admin from on_conflict because
                # admins might be added/removed via DB/Bot later.
                # EXCEPT if they are in the hardcoded config list.
                is_admin=stmt.excluded.is_admin if is_admin else User.is_admin,
                updated_at=func.now(),
            ),
        ).returning(User)

        result = await self.session.execute(insert_stmt)

        await self.session.commit()
        return result.scalar_one()

    async def update_subject(self, user_id: int, subject: str):
        """
        Updates the selected subject for a user.
        :param user_id: The user's ID.
        :param subject: The new subject.
        """
        stmt = update(User).where(User.user_id == user_id).values(selected_subject=subject)
        await self.session.execute(stmt)
        await self.session.commit()

    async def promote_admin(self, user_id: int):
        stmt = update(User).where(User.user_id == user_id).values(is_admin=True)
        await self.session.execute(stmt)
        await self.session.commit()

    async def demote_admin(self, user_id: int):
        stmt = update(User).where(User.user_id == user_id).values(is_admin=False)
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_admins(self):
        from sqlalchemy import select
        stmt = select(User).where(User.is_admin == True)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_user_by_id(self, user_id: int):
        from sqlalchemy import select
        stmt = select(User).where(User.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_stats(self):
        from sqlalchemy import select, func, and_
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        week_start = today_start - timedelta(days=7)

        total_users_stmt = select(func.count(User.user_id))
        total_users = (await self.session.execute(total_users_stmt)).scalar() or 0

        # For "active today", we look at updated_at in User model
        today_active_stmt = select(func.count(User.user_id)).where(User.updated_at >= today_start)
        today_active = (await self.session.execute(today_active_stmt)).scalar() or 0

        week_active_stmt = select(func.count(User.user_id)).where(User.updated_at >= week_start)
        week_active = (await self.session.execute(week_active_stmt)).scalar() or 0

        return {
            "total": total_users,
            "today": today_active,
            "week": week_active
        }

    async def update_daily_sub(self, user_id: int, enabled: bool):
        stmt = update(User).where(User.user_id == user_id).values(daily_sub=enabled)
        await self.session.execute(stmt)
        await self.session.commit()

    async def update_user_settings(self, user_id: int, settings: dict):
        stmt = update(User).where(User.user_id == user_id).values(settings=settings)
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_users_with_settings(self, user_ids: list[int]) -> list[User]:
        """
        Returns full User objects (including settings) for the given list of user IDs.
        Used for per-thread broadcasts where each user may have different topic_ids.
        """
        from sqlalchemy import select
        if not user_ids:
            return []
        stmt = select(User).where(User.user_id.in_(user_ids))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_users_for_broadcast(self, filter_type: str) -> list[int]:
        from datetime import datetime, timedelta
        from sqlalchemy import select, and_

        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        
        stmt = select(User.user_id)
        
        if filter_type == "all":
            # True all active users (no time limit)
            stmt = stmt.where(User.active == True)

        elif filter_type == "daily_challenge":
            # Active within last 7 days AND Subscribed
            # We keep 7-day filter for daily questions to avoid annoying dead accounts
            week_start = today_start - timedelta(days=7)
            stmt = stmt.where(User.updated_at >= week_start)
            stmt = stmt.where(User.daily_sub == True)
            stmt = stmt.where(User.active == True)
        
        elif filter_type == "active_today":
            stmt = stmt.where(User.updated_at >= today_start)
            stmt = stmt.where(User.active == True)
            
        elif filter_type == "active_week":
            week_start = today_start - timedelta(days=7)
            stmt = stmt.where(User.updated_at >= week_start)
            stmt = stmt.where(User.active == True)

        elif filter_type == "active_month":
            month_start = today_start - timedelta(days=30)
            stmt = stmt.where(User.updated_at >= month_start)
            stmt = stmt.where(User.active == True)
            
        else:
            # Inactive users filters
            # inactive_X_Y means: updated_at < (now - X days) AND updated_at >= (now - Y days - 1_sec_technically)
            # Actually easier: updated_at is OLDER than X days but NEWER than Y days?
            # "Inactive 1-2 days" means last seen 1 to 2 days ago.
            # i.e. NOT seen today.
            # seen <= (today - 1 day) AND seen > (today - 3 days) ?
            
            # Let's align with request: "Inactive for more than 1-2 days"
            # Logic: (now - updated_at).days in [1, 2]
            
            # Let's map days ranges:
            ranges = {
                "inactive_1_2": (1, 2),
                "inactive_3_6": (3, 6),
                "inactive_7_13": (7, 13),
                "inactive_14_20": (14, 20),
                "inactive_21_27": (21, 27),
            }
            
            if filter_type in ranges:
                start_days, end_days = ranges[filter_type]
                # Last seen BEFORE (today - start_days)
                # AND Last seen AFTER (today - end_days - 1)
                
                # Example 1-2 days inactive.
                # If today is 23rd.
                # Inactive 1 day: last seen 22nd.
                # Inactive 2 days: last seen 21st.
                # Range: [21st, 22nd].
                # upper_bound (latest allowed) = now - 1 day
                # lower_bound (earliest allowed) = now - 3 days (excluded) or just (now - 2 days - 24h)
                
                upper_bound = today_start - timedelta(days=start_days) + timedelta(days=1) # End of that day
                lower_bound = today_start - timedelta(days=end_days)
                
                stmt = stmt.where(and_(
                    User.updated_at < upper_bound,
                    User.updated_at >= lower_bound
                ))
            
            elif filter_type == "inactive_28_plus":
                # Updated at < today - 28 days
                threshold = today_start - timedelta(days=28)
                stmt = stmt.where(User.updated_at < threshold)

        result = await self.session.execute(stmt)
        return result.scalars().all()
