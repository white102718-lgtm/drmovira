import html
import logging
import os
import threading
from typing import Any, TypedDict

import requests

from conf import Env, env


API_TOKEN = os.environ["TG_API_TOKEN"]
# 固定 Telegram 群 chat id,三套环境一致,非 secret
TEST_CHAT_ID = "-5261336527"
PROD_CHAT_ID = "-5370529389"


class TgMention(TypedDict, total=False):
    display_name: str
    username: str
    user_id: str


MENTION_MAP: dict[str, TgMention] = {
    # "张三": {"display_name": "张三", "username": "xxx", "user_id": "123456789"},
    # "wzl": {"display_name": "wzl", "username": "xxx", "user_id": "123456789"},
}

MAX_MESSAGE_LENGTH = 4096
REQUEST_TIMEOUT = 15


def _tg_api_url(method: str) -> str:
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


def _build_text_mention(mention: TgMention) -> str | None:
    display_name = html.escape(mention.get("display_name") or "")
    user_id = mention.get("user_id")
    username = mention.get("username")

    if user_id:
        safe_user_id = html.escape(str(user_id), quote=True)
        safe_display = display_name or safe_user_id
        return f'<a href="tg://user?id={safe_user_id}">{safe_display}</a>'

    if username:
        username = username.lstrip("@")
        return f"@{html.escape(username)}"

    return None


def _resolve_mentions(
    mention_keys: list[str] | None = None, mentions: list[TgMention] | None = None
) -> list[TgMention]:
    resolved: list[TgMention] = []
    seen: set[tuple[str, str]] = set()

    for key in mention_keys or []:
        mention = MENTION_MAP.get(key)
        if not mention:
            logging.warning(f"Telegram mention 未配置: {key}")
            continue
        identity = (
            str(mention.get("user_id") or ""),
            str(mention.get("username") or ""),
        )
        if identity == ("", ""):
            logging.warning(f"Telegram mention 配置无效: {key}")
            continue
        if identity in seen:
            continue
        seen.add(identity)
        resolved.append(mention)

    for mention in mentions or []:
        identity = (
            str(mention.get("user_id") or ""),
            str(mention.get("username") or ""),
        )
        if identity == ("", ""):
            logging.warning("Telegram mention 参数无效，缺少 user_id 或 username")
            continue
        if identity in seen:
            continue
        seen.add(identity)
        resolved.append(mention)

    return resolved


def _build_group_message(
    message: str,
    mention_keys: list[str] | None = None,
    mentions: list[TgMention] | None = None,
) -> str:
    body = (message or "").strip()
    if not body:
        return ""

    resolved_mentions = _resolve_mentions(mention_keys=mention_keys, mentions=mentions)
    mention_text = " ".join(
        filter(None, (_build_text_mention(mention) for mention in resolved_mentions))
    )
    safe_body = html.escape(body)

    if mention_text:
        return f"{mention_text}\n\n{safe_body}"
    return safe_body


def _call_tg_api(
    method: str,
    payload: dict[str, Any] | None = None,
    request_timeout: int | float | None = None,
) -> dict[str, Any] | None:
    try:
        response = requests.post(
            _tg_api_url(method),
            json=payload or {},
            timeout=request_timeout or REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            logging.error(
                "Telegram API 调用失败, method=%s, 状态码=%s, 响应=%s",
                method,
                response.status_code,
                response.text,
            )
            return None
        return response.json()
    except Exception:
        logging.exception("Telegram API 调用异常, method=%s", method)
        return None


def send_tg_msg(
    message: str,
    chat_id=None,
    message_thread_id=None,
    parse_mode: str | None = None,
    reply_markup: dict[str, Any] | None = None,
    reply_to_message_id: int | None = None,
):
    if env != Env.PROD:
        chat_id = TEST_CHAT_ID
    chat_id = PROD_CHAT_ID if chat_id is None else chat_id
    text = (message or "").strip()
    if not text:
        return []
    responses = []
    text_chunks = _chunk_text(text)
    for index, chunk in enumerate(text_chunks):
        payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id is not None and index == 0:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup and index == len(text_chunks) - 1:
            payload["reply_markup"] = reply_markup
        response_data = _call_tg_api("sendMessage", payload)
        if response_data:
            responses.append(response_data)
    return responses


def send_tg_group_message(
    message: str,
    mention_keys: list[str] | None = None,
    mentions: list[TgMention] | None = None,
    chat_id=None,
    message_thread_id=None,
    reply_markup: dict[str, Any] | None = None,
):
    formatted_message = _build_group_message(
        message, mention_keys=mention_keys, mentions=mentions
    )
    return send_tg_msg(
        formatted_message,
        chat_id=chat_id,
        parse_mode="HTML",
        message_thread_id=message_thread_id,
        reply_markup=reply_markup,
    )


def reply_tg_message(
    message: str, chat_id, reply_to_message_id: int, message_thread_id: int
):
    return send_tg_msg(
        message,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
    )


def get_tg_updates(
    offset: int | None = None,
    timeout: int = 30,
    allowed_updates: list[str] | None = None,
):
    payload: dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    if allowed_updates is not None:
        payload["allowed_updates"] = allowed_updates
    return _call_tg_api("getUpdates", payload, request_timeout=timeout + 10)


def answer_tg_callback_query(
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
    return _call_tg_api("answerCallbackQuery", payload)


def edit_tg_message_reply_markup(
    chat_id,
    message_id: int,
    reply_markup: dict[str, Any] | None = None,
):
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup or {"inline_keyboard": []},
    }
    return _call_tg_api("editMessageReplyMarkup", payload)


def send_tg_msg_backend(message: str):
    thread = threading.Thread(target=send_tg_msg, args=(message,))
    thread.daemon = True
    thread.start()


def send_tg_group_message_backend(
    message: str,
    mention_keys: list[str] | None = None,
    mentions: list[TgMention] | None = None,
    chat_id=None,
):
    thread = threading.Thread(
        target=send_tg_group_message,
        kwargs={
            "message": message,
            "mention_keys": mention_keys,
            "mentions": mentions,
            "chat_id": chat_id,
        },
    )
    thread.daemon = True
    thread.start()


if __name__ == "__main__":
    send_tg_msg("sss", -4919777167)
