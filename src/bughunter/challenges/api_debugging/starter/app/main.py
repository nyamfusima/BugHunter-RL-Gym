from fastapi import FastAPI, HTTPException

from app.models import User
from app.repository import repository

app = FastAPI(title="User Directory", version="1.3.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/users", response_model=list[User])
def list_users(active: bool | None = None) -> list[User]:
    return repository.list_users(active=active)


@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: int) -> User:
    user = repository.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
