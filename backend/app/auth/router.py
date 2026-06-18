from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request, status

from app.auth.security import create_access_token, decode_access_token
from app.demo_data import DEMO_USERS, user_payload

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(username: str = Form(...), password: str = Form(...)) -> dict[str, str]:
    if password != "demo1234" or username not in DEMO_USERS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(username, {"role": DEMO_USERS[username]["role"]})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/me")
def me(request: Request) -> dict[str, Any]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user_payload(subject)
