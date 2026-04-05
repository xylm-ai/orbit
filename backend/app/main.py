from fastapi import FastAPI
from app.routers import auth, entities, portfolios, documents, extractions
from app.routers.dashboard import router as dashboard_router

app = FastAPI(title="ORBIT API", version="0.1.0")
app.include_router(auth.router)
app.include_router(entities.router)
app.include_router(portfolios.router)
app.include_router(documents.router)
app.include_router(extractions.router)
app.include_router(dashboard_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
