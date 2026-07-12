from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import SessionLocal, create_tables
from app.routers import (
    activity,
    canon,
    auto_runs,
    chapters,
    characters,
    creative,
    deconstruction,
    export,
    generation_runs,
    loop_runs,
    model_providers,
    multi_chapter_runs,
    novels,
    projects,
    prompts,
    references,
    story_engineering,
    story_map,
    tasks,
    world_rules,
)
from app.services.prompt_store import seed_prompt_templates
from app.services.task_queue import task_queue
from app.workflow.runner import loop_queue
from app.services.multi_chapter import multi_chapter_queue
from app.services.deconstruction import deconstruction_queue
from app.services.story_map import story_map_extract_queue


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_tables()
    with SessionLocal() as db:
        seed_prompt_templates(db)
    task_queue.start()
    loop_queue.start()
    multi_chapter_queue.start()
    deconstruction_queue.start()
    story_map_extract_queue.start()
    yield


app = FastAPI(
    title="Novel Local AI API",
    version="1.1.0",
    description="Local-first novel writing, context building and model generation API.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [
    projects.router,
    novels.router,
    chapters.router,
    characters.router,
    world_rules.router,
    model_providers.router,
    multi_chapter_runs.router,
    creative.router,
    generation_runs.router,
    auto_runs.router,
    references.router,
    story_engineering.router,
    deconstruction.router,
    story_map.router,
    activity.router,
    loop_runs.router,
    tasks.router,
    canon.router,
    prompts.router,
    export.router,
]:
    app.include_router(router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
