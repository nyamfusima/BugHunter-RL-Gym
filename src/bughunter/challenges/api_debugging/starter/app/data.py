"""Seed data for the user directory.

Records are kept in signup order. User IDs are assigned by the accounts service and are
not guaranteed to be contiguous: deleted accounts leave gaps.
"""

from app.models import User

USERS: list[User] = [
    User(id=1, name="Ada Lovelace", email="ada@example.com", active=True),
    User(id=2, name="Alan Turing", email="alan@example.com", active=True),
    User(id=4, name="Grace Hopper", email="grace@example.com", active=False),
    User(id=7, name="Edsger Dijkstra", email="edsger@example.com", active=True),
    User(id=9, name="Barbara Liskov", email="barbara@example.com", active=True),
]
