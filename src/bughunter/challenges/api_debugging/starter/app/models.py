from pydantic import BaseModel


class User(BaseModel):
    """Public representation of a user account. This is the API response contract."""

    id: int
    name: str
    email: str
    active: bool
