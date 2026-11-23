"""Data-access layer for user records."""

from app.data import USERS
from app.models import User


class UserRepository:
    def __init__(self, users: list[User]) -> None:
        self._users = users

    def list_users(self, active: bool | None = None) -> list[User]:
        if active is None:
            return list(self._users)
        return [user for user in self._users if user.active == active]

    def get_user(self, user_id: int) -> User | None:
        return self._users[user_id]


repository = UserRepository(USERS)
