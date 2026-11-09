import logging

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.core.security import public
from app.services.tg_callback_service import handle_telegram_update
from app.utils.tg import TG_WEBHOOK_SECRET

router = APIRouter(prefix="/telegram", tags=["telegram webhook"])


@router.post("/webhook")
@public
async def telegram_webhook(request: Request):
    if not TG_WEBHOOK_SECRET:
        logging.error("Telegram webhook secret 未配置")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": "webhook secret not configured"},
        )

    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != TG_WEBHOOK_SECRET:
        logging.warning("Telegram webhook secret 校验失败")
        return JSONResponse(
            status_code=403,
            content={"ok": False, "message": "invalid secret"},
        )

    try:
        payload = await request.json()
    except Exception:
        logging.exception("Telegram webhook 请求体解析失败")
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "invalid json"},
        )

    try:
        await handle_telegram_update(payload)
    except Exception:
        logging.exception("Telegram webhook 处理失败")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": "handler failed"},
        )

    return JSONResponse(status_code=200, content={"ok": True})
