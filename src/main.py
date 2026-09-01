import logging 
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn

from src.middlewares import base as base_middlewares
from src.config import settings
from src.celery_tasks import broker as tasks_broker

from src.auth  import views as auth_views
from src.chats import views as chats_views

# on app start
@asynccontextmanager
async def app_lifespan(app: FastAPI):
    # start celery broker
    # tasks_broker.app.start()

    # start listen channels for ws redis pubsub
    # await chats_views.ws_manager.pubsub_manager.start_listen_channels()
    
    yield

    # chast ws manager pubsub
    await chats_views.ws_manager.pubsub_manager.unsubscribe_all_channels()
    # start celery broker
    # tasks_broker.app.close()

app = FastAPI(
    title=settings.project_name,
    openapi_url=f"{settings.api_v1}/openapi.json",
    lifespan=app_lifespan
)
# include routers
app.include_router(
    auth_views.router,
    prefix=settings.api_v1
)
app.include_router(
    chats_views.router,
    prefix=settings.api_v1
)
# set middlewares
app.add_middleware(
    base_middlewares.BaseDBSessionMiddleware
)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    uvicorn.run(app, port=8000)