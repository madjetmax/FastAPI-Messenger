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
async def test_post_get_me_failed(
    asgi_client: AsyncClient, db_session: AsyncSession
):
    # cant get me without access token
    res = await asgi_client.get(
        auth_api_url + "me"
    )

    assert res.status_code == 401
    # get and assert res detail
    assert res.json()["detail"] == "Not authenticated"

    # cant get me with invalid access token
    headers = {
        "Authorization": f"Bearer {conftest.USER1_ACCESS_TOKEN+"r"}"
    }
    res = await asgi_client.get(
        auth_api_url + "me",
        headers=headers
    )

    assert res.status_code == 401
    # get and assert res detail
    assert res.json()["detail"] == "token is invalid"

    # cant get me with refresh token
    headers = {
        "Authorization": f"Bearer {conftest.USER1_REFRESH_TOKEN}"
    }
    res = await asgi_client.get(
        auth_api_url + "me",
        headers=headers
    )

    assert res.status_code == 401
    # get and assert res detail
    assert res.json()["detail"] == "token type is not access"

@pytest.mark.asyncio
async def test_post_get_me(
    asgi_client: AsyncClient, db_session: AsyncSession
):
    # assert can get me with correct access token
    headers = {
        "Authorization": f"Bearer {conftest.USER1_ACCESS_TOKEN}"
    }
    res = await asgi_client.get(
        auth_api_url + "me",
        headers=headers
    )

    assert res.status_code == 200

    # get me from db
    user = await db.get_user_by_username(
        db_session, USER1_USERNAME
    )

    # get and assert res data
    res_data = res.json()
    assert res_data["id"] == user.id
    assert res_data["username"] == user.username == USER1_USERNAME
    assert res_data["created_at"]

@pytest.mark.asyncio
async def test_post_get_me_access_expired(
    asgi_client: AsyncClient, db_session: AsyncSession
):
    # assert can't get me with expired access token
    headers = {
        "Authorization": f"Bearer {conftest.USER1_ACCESS_TOKEN}"
    }

    # mock now as now + expire date
    with patch("src.auth.jwt_bearer.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.return_value = datetime.now(UTC) + settings.auth.access_token_expire
        res = await asgi_client.get(
            auth_api_url + "me",
            headers=headers
        )

        assert res.status_code == 401
        # get and assert res detail
        assert res.json()["detail"] == "token expired"