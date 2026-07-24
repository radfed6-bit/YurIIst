from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import codes, articles, search
from src.shared.database import init_db

app = FastAPI(title="Legal Bot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(codes.router)
app.include_router(articles.router)
app.include_router(search.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
