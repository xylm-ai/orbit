import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.services.auth import decode_access_token
from app.config import settings

router = APIRouter()


@router.websocket("/portfolio/live")
async def live_prices(
    websocket: WebSocket,
    token: str = Query(...),
):
    """WebSocket endpoint for live price updates.

    Client connects with ?token=<jwt>. Authenticates, then subscribes to
    Redis pub/sub channel 'orbit:prices'. Pushes JSON messages when prices refresh.
    Message shape: {"type": "price_update", "updated_isins": [...], "timestamp": "..."}
    """
    try:
        decode_access_token(token)
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket.accept()

    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe("orbit:prices")

        async for message in pubsub.listen():
            if message.get("type") == "message":
                data = message.get("data", "{}")
                payload = json.loads(data)
                await websocket.send_json({"type": "price_update", **payload})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await pubsub.unsubscribe("orbit:prices")
            await r.aclose()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
