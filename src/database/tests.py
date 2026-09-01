import asyncio
from src import database as db
from src.database.engine import session as db_session


async def test_messages(session):
    chat = await db.get_private_chat(session, 133, 12)
    print(chat)
    # print(chat.messages)
    # # await db.create_private_chat_message(
    # #     session, 2, 1, 12
    # # )
    # chat = await db.get_private_chat(
    #     session, 1
    # )
    # print(chat)
    # print(chat.last_message.created_at)
    # print(chat.messages)

async def main():
    async with db_session() as db_session_:
        await test_messages(db_session_)

if __name__ == "__main__":
    asyncio.run(main())