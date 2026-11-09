from app.utils.tg import (
    answer_tg_callback_query,
    edit_tg_message_reply_markup,
    reply_tg_message,
)

TELEGRAM_CALLBACK_PREFIX = "tech_fb_account_status"
TELEGRAM_CALLBACK_ACTION_PROCESSING = "processing"
TELEGRAM_CALLBACK_ACTION_RESOLVED = "resolved"


def parse_tech_fb_account_callback_action(callback_data: str | None) -> str | None:
    if not callback_data or ":" not in callback_data:
        return None

    prefix, action = callback_data.split(":", 1)
    if prefix != TELEGRAM_CALLBACK_PREFIX:
        return None
    if action not in {
        TELEGRAM_CALLBACK_ACTION_PROCESSING,
        TELEGRAM_CALLBACK_ACTION_RESOLVED,
    }:
        return None
    return action


def _ensure_tg_result(result, action: str) -> None:
    if result is None:
        raise RuntimeError(f"Telegram API 调用失败: {action}")
    if isinstance(result, list):
        if not result or any(item.get("ok") is False for item in result if isinstance(item, dict)):
            raise RuntimeError(f"Telegram API 调用失败: {action}")
        return
    if isinstance(result, dict) and result.get("ok") is False:
        raise RuntimeError(f"Telegram API 调用失败: {action}")


async def _handle_callback_query(callback_query: dict) -> None:
    callback_query_id = callback_query.get("id")
    message = callback_query.get("message") or {}
    callback_data = callback_query.get("data")
    action = parse_tech_fb_account_callback_action(callback_data)
    if not callback_query_id or not action:
        return

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    thread_id = message.get("message_thread_id")
    if chat_id is None or message_id is None:
        _ensure_tg_result(
            await answer_tg_callback_query(callback_query_id, text="消息信息缺失"),
            "answerCallbackQuery:missing_message",
        )
        return

    _ensure_tg_result(
        await answer_tg_callback_query(callback_query_id),
        "answerCallbackQuery",
    )
    if action == TELEGRAM_CALLBACK_ACTION_PROCESSING:
        _ensure_tg_result(
            await reply_tg_message(
                "🟡 已标记为解决中",
                chat_id=chat_id,
                reply_to_message_id=message_id,
                message_thread_id=thread_id,
            ),
            "sendMessage:processing",
        )
        return

    if action == TELEGRAM_CALLBACK_ACTION_RESOLVED:
        _ensure_tg_result(
            await reply_tg_message(
                "✅ 已标记为已解决",
                chat_id=chat_id,
                reply_to_message_id=message_id,
                message_thread_id=thread_id,
            ),
            "sendMessage:resolved",
        )
        _ensure_tg_result(
            await edit_tg_message_reply_markup(chat_id=chat_id, message_id=message_id),
            "editMessageReplyMarkup",
        )


async def handle_telegram_update(update: dict) -> None:
    callback_query = update.get("callback_query")
    if callback_query:
        await _handle_callback_query(callback_query)
