"""
# 心声 (Inner Voice)

内置心声插件。现在只在主 Agent 被真实触发并完成回复后工作：

- 不再监听普通用户消息，不会在未唤醒/未触发主 Agent 时触发。
- 不再独立调用 `gen_openai_chat_response`，心声由主 Agent 同一次 LLM 响应携带隐藏 marker。
- marker 会在解析/发送前剥离，绝不进入主回复文本或沙盒代码。
- 主 Agent 正常完成后才按概率渲染并发送心声卡片。
"""

import json
import random
import re
import time
from typing import Dict, Optional

from pydantic import Field

from nekro_agent.api import core, i18n
from nekro_agent.api.plugin import ConfigBase, ExtraField, NekroPlugin
from nekro_agent.api.schemas import AgentCtx
from nekro_agent.models.db_chat_channel import DBChatChannel
from nekro_agent.schemas.chat_message import ChatType


plugin = NekroPlugin(
    name="心声插件",
    module_name="inner_voice",
    description="让 Bot 偶尔以图片卡片的形式说出此刻的内心活动",
    version="0.2.0",
    author="Akiyo",
    url="https://github.com/Akiyo-dayo/nekro-plugin-inner-voice",
    i18n_name=i18n.i18n_text(zh_CN="心声插件", en_US="Inner Voice Plugin"),
    i18n_description=i18n.i18n_text(
        zh_CN="让 Bot 偶尔以图片卡片的形式说出此刻的内心活动",
        en_US="Occasionally lets the bot reveal its current inner monologue as an image card",
    ),
)


@plugin.mount_config()
class InnerVoiceConfig(ConfigBase):
    """心声配置"""

    ENABLE_INNER_VOICE: bool = Field(
        default=False,
        title="启用心声",
        description="关闭时完全不触发，不会产生任何模型调用",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="启用心声", en_US="Enable inner voice"),
            i18n_description=i18n.i18n_text(
                zh_CN="关闭时完全不触发，不会产生任何模型调用",
                en_US="When off, nothing is triggered and no model call is made",
            ),
        ).model_dump(),
    )
    TRIGGER_PROBABILITY: float = Field(
        default=0.03,
        title="单条消息的触发概率",
        description="取值 0~1。0.03 表示大约每 33 条消息冒一次心声，实际频率还受冷却时间限制",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="单条消息的触发概率", en_US="Trigger probability per message"),
            i18n_description=i18n.i18n_text(
                zh_CN="取值 0~1，实际频率还受冷却时间限制",
                en_US="Between 0 and 1; the cooldown further limits the real frequency",
            ),
        ).model_dump(),
    )
    MIN_INTERVAL_SECONDS: int = Field(
        default=3600,
        title="同一会话的最小间隔（秒）",
        description="心声贵在偶尔出现，间隔太短会变成刷屏",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="同一会话的最小间隔（秒）", en_US="Minimum interval per session (seconds)"),
            i18n_description=i18n.i18n_text(
                zh_CN="心声贵在偶尔出现，间隔太短会变成刷屏",
                en_US="Inner voice works because it is rare; a short interval turns it into spam",
            ),
        ).model_dump(),
    )
    ENABLE_IN_PRIVATE_CHAT: bool = Field(
        default=False,
        title="在私聊中也触发",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="在私聊中也触发", en_US="Also trigger in private chats"),
        ).model_dump(),
    )
    MODEL_GROUP: str = Field(
        default="",
        title="生成心声使用的模型组",
        description="留空则使用系统主模型组",
        json_schema_extra=ExtraField(
            ref_model_groups=True,
            model_type="chat",
            i18n_title=i18n.i18n_text(zh_CN="生成心声使用的模型组", en_US="Model group for generating inner voice"),
            i18n_description=i18n.i18n_text(
                zh_CN="留空则使用系统主模型组",
                en_US="Leave empty to use the primary model group",
            ),
        ).model_dump(),
    )
    CONTEXT_MESSAGE_COUNT: int = Field(
        default=12,
        title="参考的最近消息条数",
        description="给模型看一小段最近的聊天，心声才会贴着当下的氛围而不是凭空自语",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="参考的最近消息条数", en_US="Recent messages used as context"),
            i18n_description=i18n.i18n_text(
                zh_CN="给模型看一小段最近的聊天，心声才会贴着当下的氛围",
                en_US="A short slice of recent chat keeps the monologue tied to the current mood",
            ),
        ).model_dump(),
    )
    BG_IMAGE_PATH: str = Field(
        default="/app/inner_voice_bg.gif",
        title="背景图路径",
        description="背景图片的绝对路径，支持 PNG/JPG/GIF（GIF只取第一帧），默认 /app/inner_voice_bg.gif",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="背景图路径", en_US="Background image path"),
        ).model_dump(),
    )
    FONT_SIZE: int = Field(
        default=34,
        title="字体大小",
        description="心声卡片的字体大小，建议 24~48",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="字体大小", en_US="Font size"),
        ).model_dump(),
    )
    TEXT_COLOR_R: int = Field(
        default=30,
        title="文字颜色 R",
        description="RGB 颜色中的红色分量，取值 0~255",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="文字颜色 R", en_US="Text color R"),
        ).model_dump(),
    )
    TEXT_COLOR_G: int = Field(
        default=100,
        title="文字颜色 G",
        description="RGB 颜色中的绿色分量，取值 0~255",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="文字颜色 G", en_US="Text color G"),
        ).model_dump(),
    )
    TEXT_COLOR_B: int = Field(
        default=140,
        title="文字颜色 B",
        description="RGB 颜色中的蓝色分量，取值 0~255",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="文字颜色 B", en_US="Text color B"),
        ).model_dump(),
    )
    BOX_LEFT_RATIO: float = Field(
        default=0.43,
        title="文字区域左边界比例",
        description="文字区域左边界占图片宽度的比例，取值 0~1",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="文字区域左边界比例", en_US="Text box left ratio"),
        ).model_dump(),
    )
    BOX_RIGHT_RATIO: float = Field(
        default=0.85,
        title="文字区域右边界比例",
        description="文字区域右边界占图片宽度的比例，取值 0~1",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="文字区域右边界比例", en_US="Text box right ratio"),
        ).model_dump(),
    )
    BOX_TOP_RATIO: float = Field(
        default=0.18,
        title="文字区域上边界比例",
        description="文字区域上边界占图片高度的比例，取值 0~1",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="文字区域上边界比例", en_US="Text box top ratio"),
        ).model_dump(),
    )
    BOX_BOTTOM_RATIO: float = Field(
        default=0.82,
        title="文字区域下边界比例",
        description="文字区域下边界占图片高度的比例，取值 0~1",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="文字区域下边界比例", en_US="Text box bottom ratio"),
        ).model_dump(),
    )


config = plugin.get_config(InnerVoiceConfig)

INNER_VOICE_MARKER_RE = re.compile(
    r"^[ \t]*(?:#\s*)?<NA_INNER_VOICE>(.*?)</NA_INNER_VOICE>[ \t]*(?:\r?\n)?",
    re.DOTALL | re.MULTILINE,
)
MAX_INNER_VOICE_LENGTH = 120

FONT_PATH = "/app/可能是萝莉体第二版（本篇和注释）.TTF"
BG_PATH = "/app/inner_voice_bg.gif"

def render_voice_card(text: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    import io
    try:
        bg = Image.open(config.BG_IMAGE_PATH)
        bg.seek(0)
        img = bg.convert("RGBA").copy()
    except Exception:
        img = Image.new("RGBA", (1400, 560), color=(255, 220, 235, 255))
    width, height = img.size
    font_size = config.FONT_SIZE
    small_font_size = max(16, font_size - 10)
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
        small_font = ImageFont.truetype(FONT_PATH, small_font_size)
    except Exception:
        font = ImageFont.load_default()
        small_font = font
    # 文字区域：右侧空白区域
    box_left = int(width * config.BOX_LEFT_RATIO)
    box_right = int(width * config.BOX_RIGHT_RATIO)
    box_top = int(height * config.BOX_TOP_RATIO)
    box_bottom = int(height * config.BOX_BOTTOM_RATIO)
    max_width = box_right - box_left - 40
    # 换行处理
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    words = list(text)
    lines = []
    current = ""
    for ch in words:
        test = current + ch
        bbox = dummy.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    line_height = font_size + 10
    total_h = len(lines) * line_height
    # 半透明白色背景框
    draw = ImageDraw.Draw(img, "RGBA")
    pad = 20
    text_start_y = box_top + (box_bottom - box_top - total_h) // 2
    rect_left = box_left - pad
    rect_top = text_start_y - pad
    rect_right = box_right + pad
    rect_bottom = text_start_y + total_h + pad
    draw.rounded_rectangle(
        [(rect_left, rect_top), (rect_right, rect_bottom)],
        radius=15,
        fill=(255, 255, 255, 180)
    )
    # 绘制文字（深青蓝色）
    y = text_start_y
    for line in lines:
        bbox = dummy.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        cx = box_left + (max_width - line_w) // 2
        draw.text((cx, y), line, font=font, fill=(config.TEXT_COLOR_R, config.TEXT_COLOR_G, config.TEXT_COLOR_B, 255))
        y += line_height
    # 右下角"心声"标签
    tag = "心声"
    tag_bbox = dummy.textbbox((0, 0), tag, font=small_font)
    tag_w = tag_bbox[2] - tag_bbox[0] + 24
    tag_h = tag_bbox[3] - tag_bbox[1] + 12
    tag_x = rect_right - tag_w - 10
    tag_y = rect_bottom - tag_h - 10
    draw.rounded_rectangle(
        [(tag_x, tag_y), (tag_x + tag_w, tag_y + tag_h)],
        radius=10,
        fill=(255, 255, 255, 200),
        outline=(200, 150, 180, 255),
        width=2
    )
    draw.text((tag_x + 12, tag_y + 6), tag, font=small_font, fill=(180, 80, 120, 255))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()

_INJECT_PROMPT = """
如果且仅如果你已经决定本轮需要回复用户，可以顺手为“心声插件”生成一句隐藏心声。

输出要求：
1. 心声必须来自本次同一个 LLM 响应，禁止再调用任何模型或插件函数生成。
2. 在最终 Python 代码块开头附近加入一行严格 marker，格式只能是：
# <NA_INNER_VOICE>{"text":"一句第一人称心声，不超过60字"}</NA_INNER_VOICE>
3. marker 是给系统读取的隐藏数据，不是聊天内容；不要把它传给 send_msg_text，不要解释它。
4. 如果没有合适心声，可以不输出 marker。
5. marker 后仍按正常方式写 Python 代码并发送主回复。
""".strip()

_last_sent_at: Dict[str, float] = {}
_pending_inner_voice: Dict[str, str] = {}


def reset_state() -> None:
    """清空冷却与待发送状态，仅供测试使用"""
    _last_sent_at.clear()
    _pending_inner_voice.clear()


def strip_inner_voice_marker(text: str) -> tuple[str, Optional[str]]:
    """剥离主 LLM 响应里的隐藏心声 marker。"""
    found: Optional[str] = None

    def repl(match: re.Match[str]) -> str:
        nonlocal found
        if found is None:
            try:
                payload = json.loads(match.group(1).strip())
                value = str(payload.get("text", "")).strip()
                if value:
                    found = value[:MAX_INNER_VOICE_LENGTH]
            except Exception as exc:  # noqa: BLE001
                core.logger.warning(f"心声 marker 解析失败，已剥离但不发送: {exc}")
        return ""

    cleaned = INNER_VOICE_MARKER_RE.sub(repl, text)
    return cleaned, found


def capture_from_llm_response(chat_key: str, raw_response: str) -> str:
    """从主 Agent 同轮 LLM 响应中提取心声，并返回剥离后的响应。"""
    cleaned, body = strip_inner_voice_marker(raw_response)
    if body:
        _pending_inner_voice[chat_key] = body
        core.logger.debug(f"[{chat_key}] 已从主 LLM 响应捕获隐藏心声")
    return cleaned


def should_trigger(
    *,
    enabled: bool,
    probability: float,
    min_interval: float,
    allow_private: bool,
    is_group: bool,
    roll: float,
    now: float,
    last_sent_at: Optional[float],
    in_flight: bool = False,
) -> bool:
    if not enabled:
        return False
    if not is_group and not allow_private:
        return False
    if in_flight:
        return False
    if roll >= probability:
        return False
    return last_sent_at is None or (now - last_sent_at) >= min_interval


@plugin.mount_prompt_inject_method(
    name="inner_voice_same_llm",
    description="让主 Agent 在同一次 LLM 响应中携带隐藏心声 marker",
)
async def inject_inner_voice_prompt(_ctx: AgentCtx) -> str:
    if not config.ENABLE_INNER_VOICE:
        return ""
    return _INJECT_PROMPT


async def send_pending_after_agent_reply(ctx: AgentCtx) -> None:
    """主 Agent 正常结束且主回复已发送后调用。"""
    chat_key = ctx.chat_key
    body = _pending_inner_voice.pop(chat_key, None)
    if not body:
        return
    core.logger.info(f"[{chat_key}] 心声原始文本(len={len(body)}): {body!r}")
    try:
        db_chat_channel = ctx.db_chat_channel or await DBChatChannel.get_or_none(chat_key=chat_key)
        if db_chat_channel is None:
            core.logger.debug(f"[{chat_key}] 无数据库聊天频道，丢弃待发送心声")
            return
        now = time.time()
        if not should_trigger(
            enabled=config.ENABLE_INNER_VOICE,
            probability=config.TRIGGER_PROBABILITY,
            min_interval=config.MIN_INTERVAL_SECONDS,
            allow_private=config.ENABLE_IN_PRIVATE_CHAT,
            is_group=db_chat_channel.chat_type == ChatType.GROUP,
            roll=random.random(),  # noqa: S311
            now=now,
            last_sent_at=_last_sent_at.get(chat_key),
        ):
            core.logger.debug(f"[{chat_key}] 心声概率/冷却判定未通过")
            return
        from nekro_agent.api.message import send_image
        import os as _os
        from nekro_agent.tools.path_convertor import get_upload_file_path
        img_bytes = render_voice_card(body)
        tmp_path = get_upload_file_path(chat_key, use_suffix=".png", seed=f"inner_voice_{chat_key}")
        with open(tmp_path, "wb") as f:
            f.write(img_bytes)
        sandbox_path = f"/app/uploads/{_os.path.basename(tmp_path)}"
        try:
            await send_image(chat_key, sandbox_path, ctx)
        finally:
            _os.unlink(tmp_path)
        _last_sent_at[chat_key] = now
        core.logger.info(f"[{chat_key}] 主回复完成后已发送心声卡片")
    except Exception as exc:  # noqa: BLE001
        core.logger.warning(f"[{chat_key}] 发送心声失败，本次跳过: {exc}")


@plugin.mount_cleanup_method()
async def clean_up() -> None:
    """清理插件"""
    reset_state()
