# 角色音色选择功能

## Context

前端已完成 VoiceSelector.vue，用户可在创建/更新角色时选择音色，`speaker` 字段随 FormData 提交。后端需要：Character 模型加 `speaker` 字段、视图处理该字段、TTS 从硬编码改为读取角色音色。

**实测结论**：阿里云 CosyVoice-v3-flash 支持 11 个音色（含男声/女声），全部可通过现有 WebSocket duplex 流式协议工作，边生成边返回音频片段，无需改动 TTS 架构。

## 可用音色（已实机验证）

| 音色 ID | 名称 | 性别 | 风格 |
|---|---|---|---|
| `longanyang` | 龙卷杨 | 男 | 默认，沉稳 |
| `longfei_v3` | 龙飞 | 男 | 年轻活力 |
| `longshuo_v3` | 龙硕 | 男 | 沉稳 |
| `longshu_v3` | 龙叔 | 男 | 中年 |
| `longlaotie_v3` | 龙老铁 | 男 | 东北味 |
| `longyue_v3` | 龙悦 | 女 | 温柔 |
| `longyuan_v3` | 龙媛 | 女 | 知性 |
| `longmiao_v3` | 龙淼 | 女 | 甜美 |
| `longxiaochun_v3` | 龙小春 | 女 | 活泼 |
| `longxiaoxia_v3` | 龙小夏 | 女 | 清新 |
| `longxiaoyun_v3` | 龙小云 | 女 | 可爱 |

> 注意：cosyvoice-v3-flash 的音色除 `longanyang` 外都带 `_v3` 后缀；cosyvoice-v2 的音色带 `_v2` 后缀（如 `longxiaochun_v2`），两者不互通。

## 改动文件清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `backend/web/models/character.py` | 修改 | 添加 `speaker` 字段 |
| `backend/web/views/create/character/create.py` | 修改 | 接收并保存 `speaker` |
| `backend/web/views/create/character/update.py` | 修改 | 接收并更新 `speaker` |
| `backend/web/views/create/character/get_single.py` | 修改 | 返回 `speaker` 字段 |
| `backend/web/views/friend/message/chat/chat.py` | 修改 | TTS voice 从 `friend.character.speaker` 读取 |
| `backend/web/views/friend/message/chat/multimodal.py` | 修改 | 同上 |
| `frontend/src/views/create/character/components/VoiceSelector.vue` | 修改 | 更新为阿里云实际音色选项 |

## Step 1: Character 模型添加 speaker 字段

**文件**: `backend/web/models/character.py`

```python
speaker = models.CharField(max_length=50, default="longanyang")
```

- 存储阿里云音色 ID（如 `longyue_v3`），非自然语言描述
- 默认值 `longanyang`（当前硬编码值），保证向后兼容
- `max_length=50` 足够覆盖所有音色 ID

运行迁移：
```bash
python manage.py makemigrations
python manage.py migrate
```

## Step 2: 视图处理 speaker 字段

### CreateCharacterView (`create.py`)

```python
speaker = request.data.get('speaker', 'longanyang')
Character.objects.create(..., speaker=speaker)
```

### UpdateCharacterView (`update.py`)

```python
speaker = request.data.get('speaker')
if speaker:
    character.speaker = speaker
```

### GetSingleCharacterView (`get_single.py`)

返回值添加：
```python
'speaker': character.speaker,
```

## Step 3: 更新前端 VoiceSelector.vue

替换为阿里云实际音色 ID：

```vue
<select v-model="mySpeaker" class="select w-60">
  <optgroup label="男声">
    <option value="longanyang">龙卷杨（沉稳）</option>
    <option value="longfei_v3">龙飞（活力）</option>
    <option value="longshuo_v3">龙硕（沉稳）</option>
    <option value="longshu_v3">龙叔（中年）</option>
    <option value="longlaotie_v3">龙老铁（东北）</option>
  </optgroup>
  <optgroup label="女声">
    <option value="longyue_v3">龙悦（温柔）</option>
    <option value="longyuan_v3">龙媛（知性）</option>
    <option value="longmiao_v3">龙淼（甜美）</option>
    <option value="longxiaochun_v3">龙小春（活泼）</option>
    <option value="longxiaoxia_v3">龙小夏（清新）</option>
    <option value="longxiaoyun_v3">龙小云（可爱）</option>
  </optgroup>
</select>
```

默认值改为 `longanyang`（与后端一致）。

## Step 4: TTS 视图读取角色音色

### chat.py 修改

`run_tts_tasks` 签名增加 `speaker` 参数，替换硬编码：

```python
# 改动前
"voice": "longanyang",

# 改动后
"voice": speaker,
```

`run_tts_tasks(self, app, inputs, mq)` → `run_tts_tasks(self, app, inputs, mq, speaker)`

调用处（`work` 方法）传入 `friend.character.speaker`：
```python
def work(self, app, inputs, mq, speaker):
    try:
        asyncio.run(self.run_tts_tasks(app, inputs, mq, speaker))
    finally:
        mq.put_nowait(None)
```

`event_stream` 中获取 `friend` 对象传给 `work`：
```python
thread = threading.Thread(target=self.work, args=(app, inputs, mq, friend.character.speaker))
```

### multimodal.py 同理修改

## 验证

1. 运行迁移，确认 `speaker` 字段添加成功
2. 创建角色时选择音色（如 `longyue_v3`），确认 API 返回成功
3. 更新已有角色音色，确认 `get_single` 返回正确 `speaker`
4. 发送聊天消息，确认：
   - 文本和音频正常流式返回
   - 音色与角色设置一致
5. 测试已有角色（无 speaker 值），确认默认 `longanyang` 生效
