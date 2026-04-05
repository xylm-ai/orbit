from fastapi import FastAPI
from app.routers import auth

app = FastAPI(title="ORBIT API", version="0.1.0")
app.include_router(auth.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
