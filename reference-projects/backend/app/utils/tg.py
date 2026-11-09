import logging
from typing import Any
import aiohttp


API_TOKEN = "REDACTED_REFERENCE_SECRET"
TG_WEBHOOK_SECRET = "REDACTED_REFERENCE_SECRET"

MAX_MESSAGE_LENGTH = 4096
REQUEST_TIMEOUT = 15


class TelegramConfigError(RuntimeError):
    pass


def _tg_api_url(method: str) -> str:
    if not API_TOKEN:
        raise TelegramConfigError("未配置 TG_BOT_TOKEN")
    return f"https://api.telegram.org/bot{API_TOKEN}/{method}"


def _chunk_text(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")

    return chunks


async def _call_tg_api(
    method: str,
    payload: dict[str, Any] | None = None,
    request_timeout: int | float | None = None,
) -> dict[str, Any] | None:
    timeout = aiohttp.ClientTimeout(total=request_timeout or REQUEST_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(_tg_api_url(method), json=payload or {}) as response:
                if response.status != 200:
                    response_text = await response.text()
                    logging.error(
                        "Telegram API 调用失败, method=%s, 状态码=%s, 响应=%s",
                        method,
                        response.status,
                        response_text,
                    )
                    return None
                return await response.json()
    except TelegramConfigError:
        raise
    except Exception:
        logging.exception("Telegram API 调用异常, method=%s", method)
        return None


async def _post_tg_text(
    text: str,
    chat_id=None,
    message_thread_id=None,
    reply_markup: dict[str, Any] | None = None,
    reply_to_message_id: int | None = None,
) -> list[dict[str, Any]]:
    if not text:
        return []

    responses: list[dict[str, Any]] = []
    text_chunks = _chunk_text(text.strip())

    for index, chunk in enumerate(text_chunks):
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
        }
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        if reply_to_message_id is not None and index == 0:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup and index == len(text_chunks) - 1:
            payload["reply_markup"] = reply_markup

        response_data = await _call_tg_api("sendMessage", payload)
        if response_data:
            responses.append(response_data)

    return responses


async def send_tg_msg(message: str, chat_id=None):
    return await _post_tg_text((message or "").strip(), chat_id=chat_id)


async def reply_tg_message(
    message: str,
    chat_id,
    reply_to_message_id: int,
    message_thread_id: int | None = None,
):
    return await _post_tg_text(
        (message or "").strip(),
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
    )


async def answer_tg_callback_query(
    callback_query_id: str,
    text: str | None = None,
    show_alert: bool = False,
):
    payload: dict[str, Any] = {
        "callback_query_id": callback_query_id,
        "show_alert": show_alert,
    }
    if text:
        payload["text"] = text
    return await _call_tg_api("answerCallbackQuery", payload)


async def edit_tg_message_reply_markup(
    chat_id,
    message_id: int,
    reply_markup: dict[str, Any] | None = None,
):
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup or {"inline_keyboard": []},
    }
    return await _call_tg_api("editMessageReplyMarkup", payload)
