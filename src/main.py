from fastapi import FastAPI
import uvicorn

from src.auth import views as auth_views
from src.middlewares import base as base_middlewares
from src.config import settings

app = FastAPI(
    title=settings.project_name,
    openapi_url=f"{settings.api_v1}/openapi.json"
)
# include routers
app.include_router(
    auth_views.router,
    prefix=settings.api_v1
)
# set middlewares
app.add_middleware(
    base_middlewares.BaseDBSessionMiddleware
)

if __name__ == "__main__":
    uvicorn.run(app, port=8000)