#!/usr/bin/env python3

import argparse
import asyncio
import json
import logging
import sys

import websocket

# ---------------------------------------------------------------------------
# Forward message to device WebSocket
# ---------------------------------------------------------------------------

def send_to_device(ws_url: str, chat_id: str, content: str) -> bool:
    """Send one message to EmbedClaw's WebSocket (JSON: type=message, channel=feishu)."""
    try:
        ws = websocket.create_connection(ws_url, timeout=5)
        payload = {
            "type": "message",
            "content": content,
            "chat_id": chat_id,
            "channel": "feishu",
        }
        ws.send(json.dumps(payload, ensure_ascii=False))
        ws.close()
        return True
    except Exception as e:
        logging.error("Send to device %s failed: %s", ws_url, e)
        return False


# ---------------------------------------------------------------------------
# Feishu event handling (long connection via lark-oapi)
# ---------------------------------------------------------------------------

def _patch_asyncio_for_websockets_9() -> bool:
    """Allow websockets 9.x to run on Python 3.10+ by dropping deprecated loop=."""
    if sys.version_info < (3, 10):
        return False

    try:
        import websockets
    except ImportError:
        return False

    version = getattr(websockets, "__version__", "")
    if not version:
        return False

    try:
        major = int(version.split(".", 1)[0])
    except ValueError:
        return False

    if major >= 10 or getattr(asyncio, "_embedclaw_loop_kw_patched", False):
        return False

    def wrap_callable(func):
        def wrapper(*args, **kwargs):
            kwargs.pop("loop", None)
            return func(*args, **kwargs)
        return wrapper

    for name in ("sleep", "wait", "wait_for"):
        setattr(asyncio, name, wrap_callable(getattr(asyncio, name)))

    for name in ("Lock", "Event", "Condition", "Semaphore"):
        setattr(asyncio, name, wrap_callable(getattr(asyncio, name)))

    asyncio._embedclaw_loop_kw_patched = True
    return True

def run_with_lark_oapi(app_id: str, app_secret: str, device_ws_url: str) -> None:
    patched = _patch_asyncio_for_websockets_9()

    from lark_oapi import EventDispatcherHandler
    from lark_oapi.ws import Client as WSClient

    # Build reply target: p2p -> open_id:xxx, group -> chat_id:xxx
    def build_chat_id(event_ctx) -> str:
        event_data = getattr(event_ctx, "event", None)
        sender = getattr(event_data, "sender", None)
        sender_id = getattr(sender, "sender_id", None)
        open_id = getattr(sender_id, "open_id", "") or ""
        message = getattr(event_data, "message", None)
        chat_type = getattr(message, "chat_type", None) or "p2p"
        chat_id = getattr(message, "chat_id", None) or ""
        if chat_type == "p2p" and open_id:
            return f"open_id:{open_id}"
        if chat_id:
            return f"chat_id:{chat_id}"
        return f"open_id:{open_id}" if open_id else ""

    def extract_text(event_ctx) -> str:
        event_data = getattr(event_ctx, "event", None)
        message = getattr(event_data, "message", None)
        if message is None:
            return ""
        if getattr(message, "message_type", None) not in (None, "text"):
            return ""
        content_str = getattr(message, "content", None) or "{}"
        try:
            content = json.loads(content_str)
            return content.get("text", content_str)
        except json.JSONDecodeError:
            return content_str

    def handler(data) -> None:
        chat_id = build_chat_id(data)
        text = extract_text(data)
        if not chat_id or not text:
            return
        logging.info("Feishu message -> device: chat_id=%s len=%d", chat_id, len(text))
        send_to_device(device_ws_url, chat_id, text)

    dispatcher = EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(handler).build()

    logging.info("Starting Feishu long-connection relay -> %s", device_ws_url)
    logging.info("In Feishu console use '使用长连接接收事件' and subscribe 'im.message.receive_v1'")
    if patched:
        logging.info("Applied asyncio compatibility patch for websockets<10 on Python 3.10+")

    client = WSClient(app_id, app_secret, event_handler=dispatcher)
    client.start()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(description="Feishu long-connection relay for EmbedClaw (no public IP)")
    ap.add_argument("--app_id", required=True, help="Feishu app_id (e.g. cli_xxx)")
    ap.add_argument("--app_secret", required=True, help="Feishu app_secret")
    ap.add_argument(
        "--device_ws",
        default="ws://192.168.31.33:18789",
        help="Device WebSocket URL (default: ws://192.168.31.33:18789)",
    )
    args = ap.parse_args()

    run_with_lark_oapi(args.app_id, args.app_secret, args.device_ws.rstrip("/"))


if __name__ == "__main__":
    main()
