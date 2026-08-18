from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.errors import AppError, app_error_handler
from app.routers import ingredients, plans, recipes, settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="RatKitchen", lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)

app.include_router(ingredients.router)
app.include_router(plans.router)
app.include_router(recipes.router)
app.include_router(settings.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
