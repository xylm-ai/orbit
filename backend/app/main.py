from fastapi import FastAPI
from app.routers import auth, entities, portfolios

app = FastAPI(title="ORBIT API", version="0.1.0")
app.include_router(auth.router)
app.include_router(entities.router)
app.include_router(portfolios.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
