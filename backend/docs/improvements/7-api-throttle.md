# 7 接口限流

## 问题

所有接口零限流保护。攻击者可无限调用 LLM 聊天接口，快速消耗 API 额度；登录/注册接口无防暴力破解机制。

具体风险：

- **LLM 接口**：每次聊天消耗 deepseek API + TTS + embedding，成本高，无限流可被刷爆额度
- **ASR 接口**：语音识别有 API 成本，需限制调用频率
- **登录/注册**：无限制的暴力尝试可破解弱密码

## 方案：DRF 内置 Throttle + 分级限流

```
请求进入
  │
  ├─ 未认证用户 ─── AnonRateThrottle: 10/min
  │
  ├─ 已认证用户 ─── UserRateThrottle: 60/min（全局默认，覆盖 CRUD）
  │
  └─ 高成本接口 ─── 自定义 Throttle 覆盖全局：
        ├─ 聊天 (LLM+TTS) ─── ChatThrottle: 20/min
        ├─ 语音识别 (ASR)   ─── ASRThrottle: 30/min
        └─ 登录/注册        ─── AuthThrottle: 5/min（按 IP）
```

分级思路：全局给兜底，高成本接口单独从严。视图的 `throttle_classes` 会覆盖全局 `DEFAULT_THROTTLE_CLASSES`。

## 实现

### 1. settings.py — 全局 Throttle 配置

```python
REST_FRAMEWORK = {
    ...,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10/min',
        'user': '60/min',
    },
}
```

### 2. throttles.py — 自定义限流类

```python
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class ChatThrottle(UserRateThrottle):
    """聊天接口限流：LLM+TTS 成本高，限制更严"""
    rate = '20/min'


class ASRThrottle(UserRateThrottle):
    """语音识别限流：ASR 成本低于 LLM，但仍需限制"""
    rate = '30/min'


class AuthThrottle(AnonRateThrottle):
    """认证接口限流：防暴力破解，按 IP 限制"""
    rate = '5/min'
```

### 3. 视图挂载

| 视图 | 文件 | throttle_classes | 限流速率 |
|------|------|-----------------|---------|
| MessageChatView | `chat.py` | `[ChatThrottle]` | 20/min/用户 |
| MultiModalChatView | `multimodal.py` | `[ChatThrottle]` | 20/min/用户 |
| ASRView | `asr.py` | `[ASRThrottle]` | 30/min/用户 |
| LoginView | `login.py` | `[AuthThrottle]` | 5/min/IP |
| RegisterView | `register.py` | `[AuthThrottle]` | 5/min/IP |
| 其他 CRUD 视图 | — | 走全局默认 | 60/min/用户 |

### 工作原理

- DRF Throttle 基于缓存后端计数，项目已配置 Redis，天然支持
- `UserRateThrottle` 按 `user.id` 分桶，`AnonRateThrottle` 按 `IP` 分桶
- 窗口为滑动窗口（按分钟），每次请求递增计数
- 超限返回 HTTP 429 `{"detail": "Request was throttled. Expected available in X seconds."}`

## 改动范围

| 文件 | 改动 |
|------|------|
| `backend/web/throttles.py` | 新建，3 个限流类 |
| `backend/backend/settings.py` | REST_FRAMEWORK 增加 DEFAULT_THROTTLE 配置 |
| `chat.py` | 添加 `throttle_classes = [ChatThrottle]` |
| `multimodal.py` | 添加 `throttle_classes = [ChatThrottle]` |
| `asr.py` | 添加 `throttle_classes = [ASRThrottle]` |
| `login.py` | 添加 `throttle_classes = [AuthThrottle]` |
| `register.py` | 添加 `throttle_classes = [AuthThrottle]` |
