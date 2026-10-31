from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.dependency import CurrentUser
from app.auth.schema import TokenOUT, UserIN, UserOUT
from app.auth.service import (
    create_session_tokens,
    revoke_refresh_token,
    user_login,
    user_registration,
    verify_and_rotate_refresh_token,
)
from app.core.settings import settings
from db.config import sessiondb

router = APIRouter(tags=["auth"], prefix="/auth")

REFRESH_COOKIE_PATH = "/auth"  # the refresh token is only ever sent to auth endpoints


def _set_auth_cookies(response: Response, tokens: dict) -> None:
    response.set_cookie(
        key="access_token",
        value=tokens["access_token"],
        httponly=True,
        samesite="lax",
        secure=settings.PRODUCTION,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        samesite="lax",
        secure=settings.PRODUCTION,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path=REFRESH_COOKIE_PATH)


def _client_info(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None), request.headers.get("user-agent")


@router.post("/register", response_model=UserOUT, status_code=status.HTTP_201_CREATED)
async def register_user(session: sessiondb, user: UserIN):
    return await user_registration(session, user)


@router.post("/login", response_model=TokenOUT)
async def login(
    session: sessiondb,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    user = await user_login(session, form_data.username, form_data.password)
    tokens = await create_session_tokens(session, user, *_client_info(request))

    response = JSONResponse(
        content={"access_token": tokens["access_token"], "token_type": tokens["token_type"]}
    )
    _set_auth_cookies(response, tokens)
    return response


@router.post("/refresh", response_model=TokenOUT)
async def refresh(session: sessiondb, request: Request):
    plain_token = request.cookies.get("refresh_token")
    new_tokens = (
        await verify_and_rotate_refresh_token(session, plain_token, *_client_info(request))
        if plain_token
        else None
    )

    if not new_tokens:
        # HTTPException would drop the cookie deletions, so build the response by hand
        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or expired refresh token"},
        )
        _clear_auth_cookies(response)
        return response

    response = JSONResponse(
        content={"access_token": new_tokens["access_token"], "token_type": new_tokens["token_type"]}
    )
    _set_auth_cookies(response, new_tokens)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session: sessiondb, request: Request):
    plain_token = request.cookies.get("refresh_token")
    if plain_token:
        await revoke_refresh_token(session, plain_token)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserOUT)
async def get_current_active_user(current_user: CurrentUser):
    return current_user
