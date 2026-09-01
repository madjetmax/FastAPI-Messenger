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
async def test_post_refresh_tokens_failed(
    asgi_client: AsyncClient, db_session: AsyncSession
):
    # cant refresh with access token
    headers = {
        "Authorization": f"Bearer {conftest.USER1_ACCESS_TOKEN}"
    }
    res = await asgi_client.post(
        auth_api_url + "refresh",
        headers=headers
    )
    assert res.status_code == 401

    # get and assert res detail
    assert res.json()["detail"] == "token type is not refresh"

    # cant refresh with invalid token
    headers = {
        "Authorization": f"Bearer {conftest.USER1_REFRESH_TOKEN+"r"}"
    }
    res = await asgi_client.post(
        auth_api_url + "refresh",
        headers=headers
    )

    assert res.status_code == 401
    # get and assert res detail
    assert res.json()["detail"] == "token is invalid"

@pytest.mark.asyncio
async def test_post_refresh_tokens_refreshed(
    asgi_client: AsyncClient, db_session: AsyncSession
):
    # get current user session
    old_user_session = await db.get_user_session(
        db_session, conftest.USER1_SESSION_ID, conftest.USER1_ID
    )
    db_session.expunge(old_user_session)

    headers = {
        "Authorization": f"Bearer {conftest.USER1_REFRESH_TOKEN}"
    }
    res = await asgi_client.post(
        auth_api_url + "refresh",
        headers=headers
    )
    res_data = res.json()

    assert res.status_code == 200

    # get and set res data
    conftest.USER1_SESSION_ID = res_data["session_id"]
    conftest.USER1_ACCESS_TOKEN = res_data["access_token"]
    conftest.USER1_REFRESH_TOKEN = res_data["refresh_token"]

    # get and assert updated user session
    updated_user_session = await db.get_user_session(
        db_session, conftest.USER1_SESSION_ID, conftest.USER1_ID
    )

    assert uuid.UUID(conftest.USER1_SESSION_ID) == old_user_session.id == updated_user_session.id
    assert old_user_session.refresh_id != updated_user_session.refresh_id
    assert old_user_session.expires_at < updated_user_session.expires_at
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

    # get and assert refresh token data
    refresh_payload = auth_utils.decode_jwt(
        conftest.USER1_REFRESH_TOKEN
    )

    assert refresh_payload["iat"] - now.timestamp() < 2
    assert refresh_payload["exp"] - (now+settings.auth.refresh_token_expire).timestamp() < 2
    assert refresh_payload["exp"] == int(updated_user_session.expires_at.timestamp())
    assert uuid.UUID(refresh_payload["jti"]) == updated_user_session.refresh_id
    assert refresh_payload["sub"] == str(conftest.USER1_ID)
    assert refresh_payload["user_id"] == conftest.USER1_ID
    assert uuid.UUID(refresh_payload["session_id"]) == updated_user_session.id == old_user_session.id

@pytest.mark.asyncio
async def test_post_refresh_tokens_refrehs_expired(
    asgi_client: AsyncClient, db_session: AsyncSession
):
    # cant refresh with access token
    headers = {
        "Authorization": f"Bearer {conftest.USER1_REFRESH_TOKEN}"
    }

    # mock now as now + expire date
    with patch("src.auth.jwt_bearer.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.return_value = datetime.now(UTC) + settings.auth.refresh_token_expire
        res = await asgi_client.post(
            auth_api_url + "refresh",
            headers=headers
        )

        assert res.status_code == 401
        # get and assert res detail
        assert res.json()["detail"] == "token expired"

        # get and assert user session deleted in db
        user_session = await db.get_user_session(
            db_session, conftest.USER1_SESSION_ID, conftest.USER1_ID
        )

        assert user_session is None