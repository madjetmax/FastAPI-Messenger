import asyncio
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
from tests.conftest import auth_api_url
from tests.tests_auth.conftest import (
    USER1_USERNAME, USER1_EMAIL,
    USER2_USERNAME, USER2_EMAIL,
)

USER1_PASSWORD_RESET_CODE = "321CODE765"
USER2_PASSWORD_RESET_CODE = "324CODE960"

@pytest.mark.asyncio
async def test_post_password_reset_request_failed(
    asgi_client: AsyncClient, db_session: AsyncSession, redis: Redis
):
    # * assert no user with uncorrect username and email
    post_data = {
        "username": USER1_USERNAME,
        "email": "fakeemail@test.com"
    }
    res = await asgi_client.post(
        auth_api_url + "reset_passoword/reqest",
        json=post_data
    )
    print(res.json())
    assert res.status_code == 200

    # get and assert no user password reset in redis
    assert int(await redis.get(f"password_reset_requests:{USER1_USERNAME}")) == 1
    assert await redis.get(f"password_reset:{USER1_USERNAME}") is None
    assert await redis.get(f"password_reset_tries:{USER1_USERNAME}") is None

@pytest.mark.asyncio
async def test_post_password_reset_request_requested(
    asgi_client: AsyncClient, db_session: AsyncSession,
    redis: Redis
):
    post_data = {
        "username": USER1_USERNAME,
        "email": USER1_EMAIL
    }
    # assert requested with moked reset code
    with patch("src.auth.views.get_uuid_code", return_value=USER1_PASSWORD_RESET_CODE):
        res = await asgi_client.post(
            auth_api_url + "reset_passoword/reqest",
            json=post_data
        )

        assert res.status_code == 200

        # get and assert reset code in redis
        key = f"password_reset:{USER1_USERNAME}"
        hashed_code = await redis.get(key)

        assert auth_utils.verify_password(USER1_PASSWORD_RESET_CODE, hashed_code)

    # request password reset for additional user
    post_data = {
        "username": USER2_USERNAME,
        "email": USER2_EMAIL
    }
    # assert requested with moked reset code
    with patch("src.auth.views.get_uuid_code", return_value=USER2_PASSWORD_RESET_CODE):
        res = await asgi_client.post(
            auth_api_url + "reset_passoword/reqest",
            json=post_data
        )

        assert res.status_code == 200

        # get and assert reset code in redis
        key = f"password_reset:{USER2_USERNAME}"
        hashed_code = await redis.get(key)

        assert auth_utils.verify_password(USER2_PASSWORD_RESET_CODE, hashed_code)


@pytest.mark.asyncio
async def test_post_password_reset_failed(
    asgi_client: AsyncClient, db_session: AsyncSession,
    redis: Redis
):
    # cant reset by not requested username
    post_data = {
        "username": "username_uncorrect",
        "new_password": "new_passworD123&",
        "code": USER1_PASSWORD_RESET_CODE
    }

    res = await asgi_client.post(
        auth_api_url + "reset_passoword",
        json=post_data
    )

    assert res.status_code == 403

    # get and assert no code data in redis
    assert await redis.get(f"password_reset:username_uncorrect") is None
    assert await redis.get(f"password_reset_tries:username_uncorrect") is None

    # cant reset with uncorrect code
    post_data = {
        "username": USER1_USERNAME,
        "new_password": "new_passworD123",
        "code": "111CODE222"
    }

    res = await asgi_client.post(
        auth_api_url + "reset_passoword",
        json=post_data
    )

    assert res.status_code == 403

    # assert reset tries count
    assert int(await redis.get(f"password_reset_tries:{USER1_USERNAME}")) == 1

    # assert password not reset in db
    with patch("src.auth.views.db.reset_user_password", new=AsyncMock(return_value=False)):

        post_data = {
            "username": USER1_USERNAME,
            "new_password": "new_passworD123",
            "code": USER1_PASSWORD_RESET_CODE
        }
        res = await asgi_client.post(
            auth_api_url + "reset_passoword",
            json=post_data
        )
        # assert can't verify reset password in db
        assert res.status_code == 403

        # assert reset tries count
        assert  int(await redis.get(f"password_reset_tries:{USER1_USERNAME}")) == 2

    
    # * try to reset for additional user (user2)
    for try_ in range(1, 8 + 1):
        post_data = {
            "username": USER2_USERNAME,
            "new_password": "new_passworD123",
            "code": "111CODE222"
        }
        res = await asgi_client.post(
            auth_api_url + "reset_passoword",
            json=post_data
        )

        assert res.status_code == 403

        res_data = res.json()
        res_detail = res_data["detail"]

        # assert too many tries
        if try_ >= 6:
            assert res_detail == f"can't reset password for {USER2_USERNAME}, too many tries, try later"

        # assert code just uncorrect
        else:
            assert res_detail == f"can't reset password for {USER2_USERNAME}"


