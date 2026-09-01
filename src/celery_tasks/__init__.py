import asyncio
from celery import shared_task
from datetime import datetime, timedelta, UTC 
from asgiref.sync import async_to_sync

from sqlalchemy.ext.asyncio import AsyncSession

from src.celery_tasks.broker import app
from src.services.emailing import send_email
from src import database as db
from src.database.engine import celery_tasks_session as db_session
from src.config import settings

# * auth
@app.task(ignore_result=True)
def send_user_verification_code_email(email: str, code: str):
    send_email(
        email, 
        "Verify Your Account",
        f"Here's the code to verify your account: {code}",
    )

@app.task(ignore_result=True)
def send_password_reset_code_email(email: str, code: str):
    send_email(
        email, 
        "Reset Password",
        f"Here's the code to reset password: {code}",
    )

@app.task(ignore_result=True)
def send_email_reset_code_email(new_email: str, code: str):
    send_email(
        new_email, 
        "Reset Email",
        f"Here's the code to set this email as current: {code}",
    )


# deleting users
async def async_delete_inactive_users():
    # set db session
    async with db_session() as db_session_:
        # set created before date to delete only expired user
        created_before_date = (
            # user creation date
            (datetime.now(UTC) - settings.auth.registered_user_delete_schedule_timdelta)
        )

        # delete in db
        await db.delete_inactive_registered_users(
            db_session_, created_before_date
        )

@shared_task()
def delete_inactive_users():
    # set async deleting as sync function
    sync_deleting = async_to_sync(async_delete_inactive_users)
    sync_deleting()
    print("deleting")