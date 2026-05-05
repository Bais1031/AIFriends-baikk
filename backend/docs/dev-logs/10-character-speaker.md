# 角色音色选择功能

## Context

前端已完成 VoiceSelector.vue，用户可在创建/更新角色时选择音色，`speaker` 字段随 FormData 提交。后端已实现：Character 模型加 `speaker` 字段、视图处理该字段、TTS 从硬编码改为读取角色音色。

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
| `frontend/src/views/create/character/CreateCharacter.vue` | 修改 | 集成 VoiceSelector 组件，提交 speaker |
| `frontend/src/views/create/character/UpdateCharacter.vue` | 修改 | 集成 VoiceSelector 组件，提交 speaker |

## Step 1: Character 模型添加 speaker 字段 ✅

**文件**: `backend/web/models/character.py`

```python
class Character(models.Model):
    author = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    photo = models.ImageField(upload_to=photo_upload_to)
    profile = models.TextField(max_length=100000)
    background_image = models.ImageField(upload_to=background_image_upload_to)
    speaker = models.CharField(max_length=50, default="longanyang")  # 新增
    create_time = models.DateTimeField(default=now)
    update_time = models.DateTimeField(default=now)
```

- 存储阿里云音色 ID（如 `longyue_v3`），非自然语言描述
- 默认值 `longanyang`（当前硬编码值），保证向后兼容
- `max_length=50` 足够覆盖所有音色 ID

迁移文件已生成并执行：
```
web/migrations/0014_character_speaker_alter_memoryitem_embedding.py
```

## Step 2: 视图处理 speaker 字段 ✅

### CreateCharacterView (`create.py`)

```python
speaker = request.data.get('speaker', 'longanyang')

Character.objects.create(
    author=user_profile,
    name=name,
    profile=profile,
    photo=photo,
    background_image=background_image,
    speaker=speaker,
)
```

### UpdateCharacterView (`update.py`)

```python
character.name = name
character.profile = profile
speaker = request.data.get('speaker')
if speaker:
    character.speaker = speaker
character.update_time = now()
```

### GetSingleCharacterView (`get_single.py`)

返回值添加：
```python
'character': {
    'id': character.id,
    'name': character.name,
    'profile': character.profile,
    'photo': character.photo.url,
    'background_image': character.background_image.url,
    'speaker': character.speaker,  # 新增
}
```

## Step 3: 更新前端 VoiceSelector.vue ✅

替换为阿里云实际音色 ID：

```vue
<select v-model="mySpeaker" class="select w-60">
  <option disabled value="">请选择音色</option>
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

默认值 `longanyang`（与后端一致）。

### CreateCharacter.vue 集成

```vue
<div class="flex gap-6 items-start">
  <BackgroundImage ref="background-image-ref" />
  <VoiceSelector ref="voice-ref" />
</div>
```

```javascript
const speaker = voiceRef.value.mySpeaker
formData.append('speaker', speaker)
```

### UpdateCharacter.vue 集成

```vue
<div class="flex gap-6 items-start">
  <BackgroundImage ref="background-image-ref" :backgroundImage="character.background_image" />
  <VoiceSelector ref="voice-ref" :speaker="character.speaker" />
</div>
```

```javascript
const speaker = voiceRef.value.mySpeaker
formData.append('speaker', speaker)
```

## Step 4: TTS 视图读取角色音色 ✅

### chat.py 修改

`run_tts_tasks` 签名增加 `speaker` 参数，替换硬编码：

```python
# 改动前
async def run_tts_tasks(self, app, inputs, mq):
    ...
    "voice": "longanyang",

# 改动后
async def run_tts_tasks(self, app, inputs, mq, speaker):
    ...
    "voice": speaker,
```

`work` 方法透传 `speaker`：

```python
# 改动前
def work(self, app, inputs, mq):
    try:
        asyncio.run(self.run_tts_tasks(app, inputs, mq))
    finally:
        mq.put_nowait(None)

# 改动后
def work(self, app, inputs, mq, speaker):
    try:
        asyncio.run(self.run_tts_tasks(app, inputs, mq, speaker))
    finally:
        mq.put_nowait(None)
```

`event_stream` 中从 `friend` 对象传入音色：

```python
# 改动前
thread = threading.Thread(target=self.work, args=(app, inputs, mq))

# 改动后
thread = threading.Thread(target=self.work, args=(app, inputs, mq, friend.character.speaker))
```

### multimodal.py 修改

与 chat.py 完全相同的修改模式：

- `run_tts_tasks(self, app, inputs, mq)` → `run_tts_tasks(self, app, inputs, mq, speaker)`
- `"voice": "longanyang"` → `"voice": speaker`
- `work(self, app, inputs, mq)` → `work(self, app, inputs, mq, speaker)`
- `args=(app, inputs, mq)` → `args=(app, inputs, mq, friend.character.speaker)`

## 验证清单

1. ✅ 运行迁移，确认 `speaker` 字段添加成功
2. ⬜ 创建角色时选择音色（如 `longyue_v3`），确认 API 返回成功
3. ⬜ 更新已有角色音色，确认 `get_single` 返回正确 `speaker`
4. ⬜ 发送聊天消息，确认：
   - 文本和音频正常流式返回
   - 音色与角色设置一致
5. ⬜ 测试已有角色（无 speaker 值），确认默认 `longanyang` 生效
