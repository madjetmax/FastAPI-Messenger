import asyncio
import uuid
from datetime import datetime, timedelta, UTC
import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.database.models.user import User
from src import database as db
from src.config import settings
from src.celery_tasks import broker as tasks_broker
from src.auth import utils as auth_utils
from tests.conftest import (
    auth_api_url, 
)
from tests.tests_auth.conftest import (
    USER1_USERNAME, USER1_EMAIL,
    USER2_USERNAME, USER2_EMAIL,
)
from tests.tests_auth import conftest

@pytest.mark.asyncio
async def test_post_login_failed(
    asgi_client: AsyncClient, db_session: AsyncSession
):
    # cant login with auth headers
    post_data = {
        "username": "username",
        "password": "password"
    }

    headers = {
        "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0eXBlIjoiYWNjZXNzIiwic3ViIjoiMTIiLCJqdGkiOiIwMTlmMTczMi1mNzc4LTc5YzItOTIyMi00OWQyMTFhYjZmZWIiLCJzZXNzaW9uX2lkIjoiMDE5ZjE3MzItZjc3OC03OWMyLTkyMjItNDljZTA3ZGNkNGIwIiwidXNlcl9pZCI6MTIsImlhdCI6MTc4MjgwMDY0MywiZXhwIjoxNzgyODAwNzAzfQ.PMmGn8NUGzQI-_JUu7smyKhbLVhYzZ_ULMU1ZdhGqqE1VOEbs9k7GxflbG6GMpH3bGBRVw-zNVzX8r6UgQsMuQYC8nDrLUog-A54GYBUpOURnVXozZGz951gv8DCdsbMBy3Lqi_e0Xcs9s69LEAeEpLUSgJ8f1fK06hJvPXpflWkrwz-HKbqIXDPzjYAaCDHv5Hv7gqGjl42kDHv9qyHYU1uyKp_LXPS2zWxCoqBdT0Qzk7YvbExHHsKUet8-slBi98uzpFF5DI5Ox232coGcWcVW7qjxkb2QwtyK-Afn2MXvLlNn6hAuF1Tcbyv33Az4bfw4d9kD0WmetC__6ESsg"
    }

    res = await asgi_client.post(
        auth_api_url + "login",
        json=post_data,
        headers=headers
    )

    assert res.status_code == 403

    # cant login with invalid post data
    post_data = {
        "username": "username",
        "password1": "password"
    }

    res = await asgi_client.post(
        auth_api_url + "login",
        json=post_data,
    )

    assert res.status_code == 422

    # cant login to unexisting user
    post_data = {
        "username": "username",
        "password": "password"
    }

    res = await asgi_client.post(
        auth_api_url + "login",
        json=post_data,
    )
    print(res.json())
    assert res.status_code == 401
    # get and assert res detail
    detail = res.json()["detail"]
    assert detail == "invalid username or password"

    # cant login with uncorrect password
    post_data = {
        "username": USER1_USERNAME,
        "password": "password"
    }

    res = await asgi_client.post(
        auth_api_url + "login",
        json=post_data,
    )

    assert res.status_code == 401
    # get and assert res detail
    detail = res.json()["detail"]
    assert detail == "invalid username or password"

    # cant login with to innactive user
    post_data = {
        "username": USER2_USERNAME,
        "password": "Strong_Password$123"
    }

    res = await asgi_client.post(
        auth_api_url + "login",
        json=post_data,
    )

    assert res.status_code == 403
    # get and assert res detail
    detail = res.json()["detail"]
    assert detail == "user is inactive"


@pytest.mark.asyncio
async def test_post_login_logged_in(
    asgi_client: AsyncClient, db_session: AsyncSession
):
    post_data = {
        "username": USER1_USERNAME,
        "password": "Strong_Password$123"
    }

    res = await asgi_client.post(
        auth_api_url + "login",
        json=post_data,
    )

    assert res.status_code == 200



    # get and assert user session data in response
    res_data = res.json()
    conftest.USER1_SESSION_ID = res_data["session_id"]
    conftest.USER1_ACCESS_TOKEN = res_data["access_token"]
    conftest.USER1_REFRESH_TOKEN = res_data["refresh_token"]

    assert conftest.USER1_SESSION_ID
    assert conftest.USER1_ACCESS_TOKEN
    assert conftest.USER1_REFRESH_TOKEN
    assert res_data["token_type"] == "Bearer"

    # assert tokens expire
    now = datetime.now(UTC)
    assert (
        res_data["access_token_expires_at_seconds"] - (now+settings.auth.access_token_expire).timestamp()
        < 2
    )
    assert (
        res_data["refresh_token_expires_at_seconds"] - (now+settings.auth.refresh_token_expire).timestamp()
        < 2
    )

    # get logged in user in db
    user = await db.get_user_by_username(
        db_session, USER1_USERNAME
    )

    conftest.USER1_ID = user.id

    # get and assert user session in db
    user_session = await db.get_user_session(
        db_session, conftest.USER1_SESSION_ID, user.id
    )

    assert user_session.is_main == False
    assert user_session.user_id == user.id
    assert user_session.expires_at.timestamp() - (now+settings.auth.refresh_token_expire).timestamp() < 2

    # get and assert access token data
    access_payload = auth_utils.decode_jwt(
        conftest.USER1_ACCESS_TOKEN
    )

    assert access_payload["iat"] - now.timestamp() < 2
    assert access_payload["exp"] - (now+settings.auth.access_token_expire).timestamp() < 2
    assert uuid.UUID(access_payload["jti"]) == user_session.refresh_id
    assert access_payload["sub"] == str(user.id)
    assert access_payload["user_id"] == user.id
    assert uuid.UUID(access_payload["session_id"]) == user_session.id

    # get and assert refresh token data
    refresh_payload = auth_utils.decode_jwt(
        conftest.USER1_REFRESH_TOKEN
    )

    assert refresh_payload["iat"] - now.timestamp() < 2
    assert refresh_payload["exp"] - (now+settings.auth.refresh_token_expire).timestamp() < 2
    assert uuid.UUID(refresh_payload["jti"]) == user_session.refresh_id
    assert refresh_payload["sub"] == str(user.id)
    assert refresh_payload["user_id"] == user.id
    assert uuid.UUID(refresh_payload["session_id"]) == user_session.id
