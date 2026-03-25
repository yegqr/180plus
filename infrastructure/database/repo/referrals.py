from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import func, select

from infrastructure.database.models.referrals import ReferralLink
from infrastructure.database.models.stats import JoinStat
from infrastructure.database.repo.base import BaseRepo


class ReferralRepo(BaseRepo):

    async def create_referral(
        self,
        code: str,
        name: str,
        created_by: int,
        owner_user_id: int | None = None,
    ) -> ReferralLink:
        link = ReferralLink(
            code=code,
            name=name,
            created_by=created_by,
            owner_user_id=owner_user_id,
        )
        self.session.add(link)
        await self.session.flush()
        return link

    async def get_by_code(self, code: str) -> ReferralLink | None:
        result = await self.session.execute(
            select(ReferralLink).where(ReferralLink.code == code)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[ReferralLink]:
        result = await self.session.execute(
            select(ReferralLink).order_by(ReferralLink.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_owner(self, owner_user_id: int) -> list[ReferralLink]:
        result = await self.session.execute(
            select(ReferralLink)
            .where(ReferralLink.owner_user_id == owner_user_id)
            .order_by(ReferralLink.created_at.desc())
        )
        return list(result.scalars().all())

    async def has_referral_links(self, owner_user_id: int) -> bool:
        result = await self.session.execute(
            select(func.count(ReferralLink.id))
            .where(ReferralLink.owner_user_id == owner_user_id)
        )
        return (result.scalar() or 0) > 0

    async def set_owner(self, code: str, owner_user_id: int | None) -> None:
        link = await self.get_by_code(code)
        if link:
            link.owner_user_id = owner_user_id

    async def toggle_active(self, code: str) -> bool:
        link = await self.get_by_code(code)
        if link:
            link.is_active = not link.is_active
            return link.is_active
        return False

    async def delete(self, code: str) -> None:
        link = await self.get_by_code(code)
        if link:
            await self.session.delete(link)

    async def get_stats_for_code(self, code: str) -> dict[str, int]:
        """Returns join counts for today, this Mon-Sun week, calendar month, all time."""
        source = f"ref_{code}"
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

        today_start = datetime.datetime(now.year, now.month, now.day)
        week_start = today_start - datetime.timedelta(days=now.weekday())  # Monday
        month_start = datetime.datetime(now.year, now.month, 1)

        async def _count(since: datetime.datetime | None) -> int:
            q = select(func.count(JoinStat.id)).where(JoinStat.source == source)
            if since is not None:
                q = q.where(JoinStat.created_at >= since)
            r = await self.session.execute(q)
            return r.scalar() or 0

        return {
            "today": await _count(today_start),
            "week": await _count(week_start),
            "month": await _count(month_start),
            "total": await _count(None),
        }

    async def get_all_with_stats(self) -> list[dict[str, Any]]:
        """Returns all referral links with their stats. Used for admin dashboard."""
        links = await self.get_all()
        result = []
        for link in links:
            stats = await self.get_stats_for_code(link.code)
            result.append({"link": link, "stats": stats})
        return result

    async def get_owner_links_with_stats(self, owner_user_id: int) -> list[dict[str, Any]]:
        """Returns links owned by a user with their stats. Used for referrer panel."""
        links = await self.get_by_owner(owner_user_id)
        result = []
        for link in links:
            stats = await self.get_stats_for_code(link.code)
            result.append({"link": link, "stats": stats})
        return result
