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
from tests.conftest import (
    auth_api_url, 
)
from tests.tests_auth.conftest import (
    USER1_USERNAME, USER1_EMAIL,
    USER2_USERNAME, USER2_EMAIL,
)

@pytest.mark.asyncio
async def test_post_register_failed(
    asgi_client: AsyncClient, db_session: AsyncSession
):
    
    # * assert cant register with invalid data
    reg_data = {
        "username": "us",
        "first_name": "",
        "last_name": "last"*20,
        "email": "myemail",
        "password": "pass",
    }

    res = await asgi_client.post(
        auth_api_url + "register",
        json=reg_data
    )
    assert res.status_code == 422

    res_data = res.json()
    # loop detail fields errors
    for field in res_data["detail"]:
        field_name = field["loc"][0]
        if field_name == "username":
            assert field["type"] == "string_too_short"
        elif field_name == "first_name":
            assert field["type"] == "missing"
        elif field_name == "last_name":
            assert field["type"] == "string_too_long"
        elif field_name == "email":
            assert field["type"] == "value_error"
        elif field_name == "password":
            assert field["type"] == "string_too_short"

    # * assert can't register with weak password
    reg_data = {
        "username": "username_correct",
        "first_name": "first_name",
        "email": "myemail@test.com",
        "password": "password",
    }

    res = await asgi_client.post(
        auth_api_url + "register",
        json=reg_data
    )
    assert res.status_code == 422

    res_data = res.json()
    print(res_data)
    assert res_data["detail"][0]["msg"] == "Value error, Password is not strong"
    
USER_VALIDATION_CODE1 = "123CODE456"
USER_VALIDATION_CODE2 = "123CODE457"

@pytest.mark.asyncio
async def test_post_register_registered(
    asgi_client: AsyncClient, redis: Redis,
):
    # tasks_broker.app.start()
    # * assert can register with valid data
    reg_data = {
        "username": USER1_USERNAME,
        "first_name": "first_name",
        "email": USER1_EMAIL,
        "password": "Strong_Password$123",
    }
    
    with patch("src.auth.views.get_uuid_code", return_value=USER_VALIDATION_CODE1):
        res = await asgi_client.post(
            auth_api_url + "register",
            json=reg_data
        )
        assert res.status_code == 200

        # assert verification code added in redis
        hashed_user_verification_code = await redis.get(
            f"user_verification:{USER1_USERNAME}"
        )
        assert auth_utils.verify_password(USER_VALIDATION_CODE1, hashed_user_verification_code)

        # create additinal user 
        reg_data = {
            "username": USER2_USERNAME,
            "first_name": "first_name",
            "email": USER2_EMAIL,
            "password": "Strong_Password$123",
        }
    
        with patch("src.auth.views.get_uuid_code", return_value="111CODE222"):
            res = await asgi_client.post(
                auth_api_url + "register",
                json=reg_data
            )
            assert res.status_code == 200

            # assert verification code added in redis
            hashed_user_verification_code = await redis.get(
                f"user_verification:{USER2_USERNAME}"
            )
            assert auth_utils.verify_password("111CODE222", hashed_user_verification_code)
        
        with patch("src.auth.views.get_uuid_code", return_value=USER_VALIDATION_CODE2):
            # assert additional user rewritten in db
            reg_data = {
                "username": USER2_USERNAME,
                "first_name": "first_name",
                "email": USER2_EMAIL,
                "password": "Strong_Password$123",
            }
            
            # with patch("src.auth.views.get_uuid_code", return_value=USER_VALIDATION_CODE1):
            res = await asgi_client.post(
                auth_api_url + "register",
                json=reg_data
            )
            assert res.status_code == 200

@pytest.mark.asyncio
async def test_post_register_cant_activate(
    asgi_client: AsyncClient, db_session: AsyncSession, redis: Redis,
):
    post_data = {
        "username": "username_uncorrect",
        "email": "myemail@test.com",
        "code": USER_VALIDATION_CODE1,
    }
    res = await asgi_client.post(
        auth_api_url + "register_verification",
        json=post_data
    )
    # assert can't verify unexisting user
    assert res.status_code == 403

    # assert no user verification in redis
    key = f"user_verification:username_uncorrect"
    assert await redis.get(key) is None

    # assert user not exists in db
    user = await db.get_user_by_username(
        db_session, "username_uncorrect"
    )
    assert user is None

    # assert user verify tries count
    tries_count = await redis.get("user_verification_tries:username_uncorrect") 
    assert tries_count is None

    post_data = {
        "username": USER1_USERNAME,
        "email": USER1_EMAIL,
        "code": "122CODE990",
    }
    res = await asgi_client.post(
        auth_api_url + "register_verification",
        json=post_data
    )
    # assert can't verify with uncorrect code
    assert res.status_code == 403

    # assert user verify tries count
    tries_count = await redis.get(f"user_verification_tries:{USER1_USERNAME}") 
    assert int(tries_count) == 1

    with patch("src.auth.views.db.set_user_active", new=AsyncMock(return_value=False)):

        post_data = {
            "username": USER1_USERNAME,
            "email": USER1_EMAIL,
            "code": USER_VALIDATION_CODE1,
        }
        res = await asgi_client.post(
            auth_api_url + "register_verification",
            json=post_data
        )
        # assert can't verify user if not updated in db
        assert res.status_code == 403

        # assert user verify tries count
        tries_count = await redis.get(f"user_verification_tries:{USER1_USERNAME}") 
        assert int(tries_count) == 2

    # * try to activate second user
    for try_ in range(1, 8 + 1):
        post_data = {
            "username": USER2_USERNAME,
            "email": USER1_EMAIL,
            "code": "122CODE990",
        }
        res = await asgi_client.post(
            auth_api_url + "register_verification",
            json=post_data
        )

        assert res.status_code == 403

        res_data = res.json()
        res_detail = res_data["detail"]

        # assert too many tries
        if try_ >= 6:
            assert res_detail == "can't verify user, too many tries, try later"

        # assert code just uncorrect
        else:
            assert res_detail == "can't verify user"

@pytest.mark.asyncio
async def test_post_register_activated(
    asgi_client: AsyncClient, db_session: AsyncSession, redis: Redis,
):
    post_data = {
        "username": USER1_USERNAME,
        "email": USER1_EMAIL,
        "code": USER_VALIDATION_CODE1,
    }
    res = await asgi_client.post(
        auth_api_url + "register_verification",
        json=post_data
    )
    # assert user verified 
    assert res.status_code == 200

    # get and assert return session data
    res_data = res.json()

    session_id = res_data["session_id"]
    assert session_id is not None

    assert res_data["access_token"] is not None
    assert res_data["refresh_token"] 
    assert res_data["token_type"] == "Bearer"

    # assert token expiration is about now
    now = datetime.now(UTC)

    assert (
        # check dates seconds diff
        int((now+settings.auth.access_token_expire).timestamp()) - res_data["access_token_expires_at_seconds"] 
        < 2
    )
    assert (
        # check dates seconds diff
        int((now+settings.auth.refresh_token_expire).timestamp()) - res_data["refresh_token_expires_at_seconds"] 
        < 2
    ) 

    # assert code data deleted in redis
    key = f"user_verification:{USER1_USERNAME}"
    assert await redis.get(key) is None  

    key = f"user_verification_tries:{USER1_USERNAME}"
    assert await redis.get(key) is None  

    # assert user activated in db
    user = await db.get_user_by_username(
        db_session, USER1_USERNAME
    )

    assert user.is_active == True

    # assert user session edded in db
    user_sessioin = await db.get_user_session(db_session, session_id, user.id)
    assert user_sessioin is not None
    assert user_sessioin.is_main == True

@pytest.mark.asyncio
async def test_post_register_user_already_exists(
    asgi_client: AsyncClient, redis: Redis,
):
    # tasks_broker.app.start()
    # * assert can't register
    reg_data = {
        "username": USER1_USERNAME,
        "first_name": "first_name",
        "email": USER1_EMAIL,
        "password": "Strong_Password$123",
    }
    
    res = await asgi_client.post(
        auth_api_url + "register",
        json=reg_data
    )

    assert res.status_code == 409

    # assert no user verification code in redis
    key = f"user_verification:{USER1_USERNAME}"
    assert await redis.get(key) is None  