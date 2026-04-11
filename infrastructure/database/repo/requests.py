from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.repo.users import UserRepo
from infrastructure.database.setup import create_engine


@dataclass
class RequestsRepo:
    """
    Repository for handling database operations. This class holds all the repositories for the database models.

    You can add more repositories as properties to this class, so they will be easily accessible.
    """

    session: AsyncSession

    @property
    def users(self) -> UserRepo:
        """
        The User repository sessions are required to manage user operations.
        """
        return UserRepo(self.session)

    @property
    def questions(self) -> "QuestionRepo":
        from infrastructure.database.repo.questions import QuestionRepo
        return QuestionRepo(self.session)

    @property
    def results(self) -> "ResultRepo":
        from infrastructure.database.repo.results import ResultRepo
        return ResultRepo(self.session)

    @property
    def settings(self) -> "SettingsRepo":
        from infrastructure.database.repo.settings import SettingsRepo
        return SettingsRepo(self.session)

    @property
    def join_requests(self) -> "JoinRequestsRepo":
        from infrastructure.database.repo.join_requests import JoinRequestsRepo
        return JoinRequestsRepo(self.session)

    @property
    def stats(self) -> "StatsRepo":
        from infrastructure.database.repo.stats import StatsRepo
        return StatsRepo(self.session)

    @property
    def logs(self) -> "LogsRepo":
        from infrastructure.database.repo.logs import LogsRepo
        return LogsRepo(self.session)
    @property
    def materials(self) -> "MaterialRepo":
        from infrastructure.database.repo.materials import MaterialRepo
        return MaterialRepo(self.session)

    @property
    def audit(self) -> "AuditRepo":
        from infrastructure.database.repo.audit import AuditRepo
        return AuditRepo(self.session)

    @property
    def events(self) -> "EventRepo":
        from infrastructure.database.repo.events import EventRepo
        return EventRepo(self.session)

    @property
    def referrals(self) -> "ReferralRepo":
        from infrastructure.database.repo.referrals import ReferralRepo
        return ReferralRepo(self.session)


if __name__ == "__main__":
    from infrastructure.database.setup import create_session_pool
    from tgbot.config import Config

    async def example_usage(config: Config):
        """
        Example usage function for the RequestsRepo class.
        Use this function as a guide to understand how to utilize RequestsRepo for managing user data.
        Pass the config object to this function for initializing the database resources.
        :param config: The config object loaded from your configuration.
        """
        engine = create_engine(config.db)
        session_pool = create_session_pool(engine)

        async with session_pool() as session:
            repo = RequestsRepo(session)

            # Replace user details with the actual values
            user = await repo.users.get_or_create_user(
                user_id=12356,
                full_name="John Doe",
                language="en",
                username="johndoe",
            )
