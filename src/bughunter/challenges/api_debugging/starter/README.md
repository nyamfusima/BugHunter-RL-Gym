# User Directory service

A small FastAPI service that exposes the company user directory.

## Endpoints

| Method | Path               | Description                                         |
|--------|--------------------|-----------------------------------------------------|
| GET    | `/health`          | Liveness check. Returns `{"status": "ok"}`.         |
| GET    | `/users`           | All users in signup order. Optional `?active=` filter. |
| GET    | `/users/{user_id}` | A single user by ID.                                |

A user is returned as `{"id": int, "name": str, "email": str, "active": bool}`.

## Layout

- `app/main.py`: HTTP routes
- `app/repository.py`: data access
- `app/data.py`: seed records
- `app/models.py`: response models
- `tests/`: test suite (run with `pytest`)
