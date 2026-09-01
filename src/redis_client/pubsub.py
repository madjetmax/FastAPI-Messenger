import asyncio
import json
from typing import Callable, Awaitable
from logging import getLogger
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from src.redis_client import get_redis
from src.config import settings
from src.utils.enums import WSRedisPubSubMessageType

logger = getLogger(__name__)

class RedisPubSubManager:
    CHANNELS_PREFIX = "channels:"
    def __init__(self, on_channel_message: Callable[[int, dict], Awaitable[None]]):
        # messages handlers
        self.on_channel_message: Callable[[int, dict], Awaitable[None]] = on_channel_message

        self.redis: Redis = get_redis(db=settings.redis_pubsub.redis_client_pubsub_db)
        self.pubsub: PubSub = self.redis.pubsub()
        self._listen_channels_task: asyncio.Task = None
    
    # channels
    async def publish(self, channel_id: str, message: str):
        print("publishing:", message, "to:", f"{self.CHANNELS_PREFIX}{channel_id}")

        await self.redis.publish(f"{self.CHANNELS_PREFIX}{channel_id}", message)
    async def unsubscribe_all_channels(self):
        logger.info("unsubscribing all channels")
        # unsubscrite all channels
        await self.pubsub.unsubscribe()
        # cancel listener task
        if self._listen_channels_task is not None:
            self._listen_channels_task.cancel()

    async def subscribe(self, channel_id: str):
        # subcribe with pubsub
        await self.pubsub.subscribe(f"{self.CHANNELS_PREFIX}{channel_id}") 

        # start listen channels if no listen task  
        self.start_listen_channels()    
        
        logger.info("subscribed channel: %s", channel_id)

    async def unsubscribe(self, channel_id: str):
        # unsubcribe with pubsub
        await self.pubsub.unsubscribe(f"{self.CHANNELS_PREFIX}{channel_id}")       
        logger.info("unsubscribed channel: %s", channel_id)

    # listening
    def start_listen_channels(self):
        # create and add listener task
        if self._listen_channels_task is None:
            self._listen_channels_task = asyncio.create_task(
                self._listen_channels()
            )

    async def _listen_channels(self):
        try:
            logger.info("start listenning channels")
            # tasks group
            async with asyncio.TaskGroup() as tg:
                # loop messages in pubsub
                async for message in self.pubsub.listen():
                    print("pubsub message:", message)
                    message_type = message.get("type")

                    # skip subscribe message
                    if message_type == WSRedisPubSubMessageType.SUBSCRIBE:
                        continue

                    message_data: dict = json.loads(message.get("data", "{}"))
                    # get message channel
                    channel: str = message.get("channel")
                    channel_id = channel.removeprefix(self.CHANNELS_PREFIX)
                    # handle message for channel
                    tg.create_task(self.on_channel_message(int(channel_id), message_data))
        except Exception as ex:
            logger.exception("error on listeting channels: %s", ex)
        
