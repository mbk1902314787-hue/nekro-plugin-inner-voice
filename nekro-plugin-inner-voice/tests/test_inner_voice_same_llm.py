from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nekro_agent.schemas.chat_message import ChatType
from plugins.builtin import inner_voice


def setup_function() -> None:
    inner_voice.reset_state()


def test_strip_inner_voice_marker_extracts_and_removes_marker() -> None:
    raw = '''```python
# <NA_INNER_VOICE>{"text":"我才没有在偷偷开心。"}</NA_INNER_VOICE>
await ctx.send_msg_text("主回复")
```'''

    cleaned, body = inner_voice.strip_inner_voice_marker(raw)

    assert body == "我才没有在偷偷开心。"
    assert "NA_INNER_VOICE" not in cleaned
    assert 'await ctx.send_msg_text("主回复")' in cleaned


def test_strip_inner_voice_marker_keeps_response_without_marker() -> None:
    raw = '```python\nawait ctx.send_msg_text("主回复")\n```'

    cleaned, body = inner_voice.strip_inner_voice_marker(raw)

    assert cleaned == raw
    assert body is None


def test_strip_inner_voice_marker_removes_bad_marker_without_sending() -> None:
    raw = '```python\n# <NA_INNER_VOICE>not json</NA_INNER_VOICE>\nawait ctx.send_msg_text("主回复")\n```'

    cleaned, body = inner_voice.strip_inner_voice_marker(raw)

    assert "NA_INNER_VOICE" not in cleaned
    assert 'await ctx.send_msg_text("主回复")' in cleaned
    assert body is None


def test_capture_from_llm_response_only_queues_extracted_body() -> None:
    raw = '```python\n# <NA_INNER_VOICE>{"text":"这次回完再悄悄冒泡。"}</NA_INNER_VOICE>\nawait ctx.send_msg_text("主回复")\n```'

    cleaned = inner_voice.capture_from_llm_response("chat-a", raw)

    assert "NA_INNER_VOICE" not in cleaned
    assert inner_voice._pending_inner_voice["chat-a"] == "这次回完再悄悄冒泡。"


def test_should_trigger_respects_switch_private_probability_cooldown_and_in_flight() -> None:
    base = dict(enabled=True, probability=1.0, min_interval=10.0, allow_private=False, is_group=True, roll=0.0, now=100.0, last_sent_at=None)

    assert inner_voice.should_trigger(**base)
    assert not inner_voice.should_trigger(**{**base, "enabled": False})
    assert not inner_voice.should_trigger(**{**base, "is_group": False})
    assert not inner_voice.should_trigger(**{**base, "roll": 1.0})
    assert not inner_voice.should_trigger(**{**base, "last_sent_at": 95.0})
    assert inner_voice.should_trigger(**{**base, "last_sent_at": 80.0})
    assert not inner_voice.should_trigger(**{**base, "in_flight": True})


@pytest.mark.asyncio
async def test_send_pending_after_agent_reply_sends_after_main_reply(monkeypatch) -> None:
    events: list[str] = ["main_reply_done"]
    inner_voice._pending_inner_voice["chat-a"] = "主回复后才发。"
    monkeypatch.setattr(inner_voice.config, "ENABLE_INNER_VOICE", True)
    monkeypatch.setattr(inner_voice.config, "TRIGGER_PROBABILITY", 1.0)
    monkeypatch.setattr(inner_voice.config, "MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(inner_voice, "fonts_available", lambda: True)
    monkeypatch.setattr(inner_voice, "render_inner_voice_card", lambda body: b"image-bytes")
    monkeypatch.setattr(inner_voice.random, "random", lambda: 0.0)
    monkeypatch.setattr(inner_voice.time, "time", lambda: 123.0)

    async def mixed_forward_file(image: bytes, file_name: str) -> str:
        events.append(f"mixed:{file_name}")
        assert image == b"image-bytes"
        return "/sandbox/inner_voice.png"

    async def send_image(path: str) -> None:
        events.append(f"send:{path}")

    ctx = SimpleNamespace(
        chat_key="chat-a",
        db_chat_channel=SimpleNamespace(chat_type=ChatType.GROUP),
        fs=SimpleNamespace(mixed_forward_file=mixed_forward_file),
        send_image=send_image,
    )

    await inner_voice.send_pending_after_agent_reply(ctx)

    assert events == ["main_reply_done", "mixed:inner_voice_123.png", "send:/sandbox/inner_voice.png"]
    assert inner_voice._pending_inner_voice == {}
    assert inner_voice._last_sent_at["chat-a"] == 123.0


@pytest.mark.asyncio
async def test_send_pending_after_agent_reply_discarded_when_probability_fails(monkeypatch) -> None:
    inner_voice._pending_inner_voice["chat-a"] = "不会发送。"
    monkeypatch.setattr(inner_voice.config, "ENABLE_INNER_VOICE", True)
    monkeypatch.setattr(inner_voice.config, "TRIGGER_PROBABILITY", 0.0)
    monkeypatch.setattr(inner_voice.random, "random", lambda: 0.5)

    ctx = SimpleNamespace(
        chat_key="chat-a",
        db_chat_channel=SimpleNamespace(chat_type=ChatType.GROUP),
        fs=SimpleNamespace(mixed_forward_file=AsyncMock()),
        send_image=AsyncMock(),
    )

    await inner_voice.send_pending_after_agent_reply(ctx)

    ctx.fs.mixed_forward_file.assert_not_awaited()
    ctx.send_image.assert_not_awaited()
    assert inner_voice._pending_inner_voice == {}
