# NekroAgent Inner Voice Plugin / 心声插件

作者：Akiyo  
仓库：https://github.com/Akiyo-dayo/nekro-plugin-inner-voice  
上游致谢：[NekroAgent](https://github.com/KroMiose/nekro-agent) / [NekroAgent_ByAkiyo](https://github.com/Akiyo-dayo/NekroAgent_ByAkiyo)

心声插件让 NekroAgent 在偶尔完成一次真实回复后，以图片卡片形式发送一句「内心活动」。当前版本是 **同次 LLM / 主回复后发送** 架构，避免旧版为了心声额外请求模型的问题。

## 重要说明

当前功能 **需要 NekroAgent 核心集成补丁**。只复制插件文件不会完整工作，因为主 Agent 需要在解析回复前剥离隐藏 marker，并在主回复发送完成后调用插件发送心声。

基线版本：`Akiyo-dayo/NekroAgent_ByAkiyo` main commit `2587b6bb440d88ebc35551e5e679520d06bc12e0`。

核心工作流：

1. 只有主 Agent 被真实唤醒并决定回复时，心声注入提示才会参与。
2. 同一次 LLM 响应可携带隐藏 marker：
   `# <NA_INNER_VOICE>{"text":"一句第一人称心声"}</NA_INNER_VOICE>`
3. 核心补丁在主回复解析/发送前剥离 marker，避免泄漏到普通回复或沙盒代码。
4. 主回复正常完成后，插件按概率、会话冷却和聊天类型判断是否发送心声图片。
5. 未唤醒主 Agent 时不触发。不额外发起模型请求。
6. 如果模型没有输出 marker，插件会静默跳过。

## 仓库结构

```text
plugins/builtin/inner_voice.py                         # 插件源码
patches/nekro-agent-inner-voice-core-integration.patch # 对 NekroAgent_ByAkiyo 的最小核心补丁
tests/                                                # 独立测试，使用 stub 上游依赖
README.md
CHANGELOG.md
LICENSE
.gitignore
```

## 配置项

插件配置类为 `InnerVoiceConfig`：

- `ENABLE_INNER_VOICE`：是否启用心声。关闭时不触发，也不会产生模型调用。
- `TRIGGER_PROBABILITY`：单次主 Agent 回复后的触发概率，范围 0~1。
- `MIN_INTERVAL_SECONDS`：同一会话最小发送间隔，避免刷屏。
- `ENABLE_IN_PRIVATE_CHAT`：是否允许私聊触发。默认关闭。
- `MODEL_GROUP`：保留配置项。当前同次 LLM 架构不额外请求模型，通常无需设置。
- `CONTEXT_MESSAGE_COUNT`：保留配置项。当前同次 LLM 架构不额外读取上下文生成心声。

## 安装

> 操作前建议先提交或备份你的 NekroAgent 工作区。

1. 获取本仓库：

```bash
git clone https://github.com/Akiyo-dayo/nekro-plugin-inner-voice.git
cd nekro-plugin-inner-voice
```

2. 复制插件文件到 NekroAgent：

```bash
cp plugins/builtin/inner_voice.py /path/to/NekroAgent/plugins/builtin/inner_voice.py
```

3. 在 NekroAgent 工作区应用核心补丁：

```bash
cd /path/to/NekroAgent
git apply --check /path/to/nekro-plugin-inner-voice/patches/nekro-agent-inner-voice-core-integration.patch
git apply /path/to/nekro-plugin-inner-voice/patches/nekro-agent-inner-voice-core-integration.patch
```

4. 重启 NekroAgent。

5. 在插件配置里启用 `ENABLE_INNER_VOICE`，并按需要调整概率和冷却时间。

## 更新

```bash
cd /path/to/nekro-plugin-inner-voice
git pull --ff-only
cp plugins/builtin/inner_voice.py /path/to/NekroAgent/plugins/builtin/inner_voice.py
cd /path/to/NekroAgent
git apply --check /path/to/nekro-plugin-inner-voice/patches/nekro-agent-inner-voice-core-integration.patch || true
```

如果补丁已经应用，`git apply --check` 可能失败。请用 `git diff` 或 `git status` 确认当前核心集成代码是否仍存在。更新本版本不需要数据库迁移，只需要重启 agent。

## 回滚

1. 关闭插件配置 `ENABLE_INNER_VOICE`。
2. 删除或恢复 `plugins/builtin/inner_voice.py`。
3. 若核心补丁由本仓库 patch 应用，可在 NekroAgent 工作区执行：

```bash
git apply -R /path/to/nekro-plugin-inner-voice/patches/nekro-agent-inner-voice-core-integration.patch
```

4. 重启 NekroAgent。

## 兼容性与限制

- 已知兼容基线：`Akiyo-dayo/NekroAgent_ByAkiyo` commit `2587b6bb440d88ebc35551e5e679520d06bc12e0`。
- 上游核心文件变化后，patch 可能需要手动调整。
- 模型不输出 marker 时会静默跳过。
- marker JSON 不合法时会剥离但不发送心声。
- 渲染图片需要运行环境存在可用中文字体，否则会跳过发送。
- 心声依赖主 Agent 真实回复。未唤醒、不回复、或中途异常时不会发送。

## 测试

本仓库测试使用 stub 模拟 NekroAgent 依赖，可独立运行：

```bash
python -m py_compile plugins/builtin/inner_voice.py
uvx --with pytest-asyncio pytest -q
```

覆盖内容：marker 提取、坏 marker 剥离、概率与冷却判定、主回复后发送顺序。

## License

本仓库原创插件代码使用 MIT License。

`patches/` 下的核心集成补丁包含 NekroAgent / NekroAgent_ByAkiyo 上下文行，不由本仓库重新授权；这些部分需遵循上游 NekroAgent 许可。请保留 NekroAgent 的来源标识与许可要求。
