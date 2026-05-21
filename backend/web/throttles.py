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
