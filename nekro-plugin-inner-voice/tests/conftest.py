import sys
import types
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pydantic_mod = types.ModuleType("pydantic")
def Field(default=None, **kwargs):
    return default
class BaseModel:
    def __init__(self, **data):
        for key, value in data.items():
            setattr(self, key, value)
pydantic_mod.Field = Field
pydantic_mod.BaseModel = BaseModel
sys.modules.setdefault("pydantic", pydantic_mod)

class _Logger:
    def debug(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass

core = types.SimpleNamespace(logger=_Logger())

def i18n_text(**kwargs):
    return kwargs.get("zh_CN") or kwargs.get("en_US") or next(iter(kwargs.values()), "")

i18n = types.SimpleNamespace(i18n_text=i18n_text)

api_mod = types.ModuleType("nekro_agent.api")
api_mod.core = core
api_mod.i18n = i18n
sys.modules["nekro_agent"] = types.ModuleType("nekro_agent")
sys.modules["nekro_agent.api"] = api_mod

plugin_mod = types.ModuleType("nekro_agent.api.plugin")

class ConfigBase(BaseModel):
    pass

class ExtraField(BaseModel):
    def __init__(self, **data):
        self._data = data
    def model_dump(self):
        return self._data

class NekroPlugin:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
    def mount_config(self):
        def deco(cls):
            return cls
        return deco
    def get_config(self, cls):
        return cls()
    def mount_prompt_inject_method(self, **kwargs):
        def deco(fn):
            return fn
        return deco
    def mount_cleanup_method(self):
        def deco(fn):
            return fn
        return deco

plugin_mod.ConfigBase = ConfigBase
plugin_mod.ExtraField = ExtraField
plugin_mod.NekroPlugin = NekroPlugin
sys.modules["nekro_agent.api.plugin"] = plugin_mod

schemas_api_mod = types.ModuleType("nekro_agent.api.schemas")
class AgentCtx: pass
schemas_api_mod.AgentCtx = AgentCtx
sys.modules["nekro_agent.api.schemas"] = schemas_api_mod

models_pkg = types.ModuleType("nekro_agent.models")
sys.modules["nekro_agent.models"] = models_pkg
chat_channel_mod = types.ModuleType("nekro_agent.models.db_chat_channel")
class DBChatChannel:
    @classmethod
    async def get_or_none(cls, **kwargs):
        return None
chat_channel_mod.DBChatChannel = DBChatChannel
sys.modules["nekro_agent.models.db_chat_channel"] = chat_channel_mod

schemas_pkg = types.ModuleType("nekro_agent.schemas")
sys.modules["nekro_agent.schemas"] = schemas_pkg
chat_message_mod = types.ModuleType("nekro_agent.schemas.chat_message")
class ChatType(Enum):
    GROUP = "group"
    PRIVATE = "private"
chat_message_mod.ChatType = ChatType
sys.modules["nekro_agent.schemas.chat_message"] = chat_message_mod

services_pkg = types.ModuleType("nekro_agent.services")
sys.modules["nekro_agent.services"] = services_pkg
imagecard_mod = types.ModuleType("nekro_agent.services.imagecard")
def fonts_available(): return True
def prepare_body_text(value: str) -> str: return " ".join(str(value).split())
def render_inner_voice_card(body: str) -> bytes: return body.encode()
imagecard_mod.fonts_available = fonts_available
imagecard_mod.prepare_body_text = prepare_body_text
imagecard_mod.render_inner_voice_card = render_inner_voice_card
sys.modules["nekro_agent.services.imagecard"] = imagecard_mod
