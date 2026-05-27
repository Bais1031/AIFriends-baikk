import os
import threading
import time
from datetime import datetime, timedelta
from typing import TypedDict, Annotated, Sequence

from django.utils.timezone import now, make_aware, localtime
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import ToolNode

from web.models.schedule import Schedule
from web.models.user import UserProfile

_CACHE_TTL = 300

SYSTEM_PROMPT = """你是日程助手，帮助用户管理日程。你可以：
1. 创建日程 — 从用户的话中提取标题、时间、地点
2. 查询日程 — 查看某天或某月的安排
3. 删除日程 — 根据用户要求删除

规则：
- 今天是 {today}，用户说"明天"就用明天的日期，说"后天"就用后天
- 如果用户没指定结束时间，end_time 设为 null
- 如果用户没指定地点，location 设为空字符串
- 每次创建日程后，告诉用户创建成功并简要说明内容
- 回复要简洁友好，像一个贴心的助理"""


_WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']

def get_system_prompt():
    current = now()
    weekday = _WEEKDAYS[current.weekday()]
    return SYSTEM_PROMPT.format(today=current.strftime(f"%Y年%m月%d日 {weekday}"))


class ScheduleGraph:
    _cached_app = None
    _cached_time = 0
    _lock = threading.Lock()

    @classmethod
    def create_app(cls):
        if cls._cached_app and (time.time() - cls._cached_time) < _CACHE_TTL:
            return cls._cached_app
        with cls._lock:
            if cls._cached_app and (time.time() - cls._cached_time) < _CACHE_TTL:
                return cls._cached_app
            cls._cached_app = cls._build_app()
            cls._cached_time = time.time()
            return cls._cached_app

    @classmethod
    def _build_app(cls):

        @tool
        def create_schedule(title: str, start_time: str, end_time: str = "", location: str = "", description: str = "", repeat_type: str = "none") -> str:
            """创建一个新日程。start_time 格式：YYYY-MM-DD HH:MM。end_time 同上，可为空。repeat_type 可选 none/daily/weekly/monthly。"""
            try:
                start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M") if end_time else None
            except ValueError:
                return "时间格式不正确，请使用 YYYY-MM-DD HH:MM 格式"

            # 获取当前用户（通过 thread_id 传递）
            user_id = cls._current_user_id
            if not user_id:
                return "无法识别用户身份"

            user_profile = UserProfile.objects.filter(user_id=user_id).first()
            if not user_profile:
                return "用户不存在"

            schedule = Schedule.objects.create(
                user=user_profile,
                title=title,
                description=description,
                start_time=make_aware(start_dt),
                end_time=make_aware(end_dt) if end_dt else None,
                location=location,
                repeat_type=repeat_type,
                source='agent',
            )
            return f"日程创建成功：{title}，时间 {start_time}"

        @tool
        def get_schedules(date: str = "", year: str = "", month: str = "") -> str:
            """查询日程。date 格式 YYYY-MM-DD 查某天，或 year+month 查某月。都不传则查今天。"""
            user_id = cls._current_user_id
            if not user_id:
                return "无法识别用户身份"

            user_profile = UserProfile.objects.filter(user_id=user_id).first()
            if not user_profile:
                return "用户不存在"

            qs = Schedule.objects.filter(user=user_profile, status='pending')

            if date:
                try:
                    dt = datetime.strptime(date, "%Y-%m-%d")
                    qs = qs.filter(start_time__date=dt.date())
                except ValueError:
                    return "日期格式不正确，请使用 YYYY-MM-DD"
            elif year and month:
                try:
                    qs = qs.filter(start_time__year=int(year), start_time__month=int(month))
                except (ValueError, TypeError):
                    return "年月格式不正确"
            else:
                qs = qs.filter(start_time__date=now().date())

            schedules = qs.order_by('start_time')[:20]
            if not schedules:
                return "没有找到日程"

            lines = []
            for s in schedules:
                time_str = localtime(s.start_time).strftime("%m-%d %H:%M")
                loc = f" @ {s.location}" if s.location else ""
                lines.append(f"- {time_str} {s.title}{loc}")
            return "\n".join(lines)

        @tool
        def delete_schedule(schedule_id: str) -> str:
            """根据 ID 删除一个日程。"""
            user_id = cls._current_user_id
            if not user_id:
                return "无法识别用户身份"

            try:
                sid = int(schedule_id)
            except (ValueError, TypeError):
                return "日程 ID 格式不正确"

            deleted = Schedule.objects.filter(
                id=sid, user__user_id=user_id
            ).update(status='cancelled')
            if deleted:
                return "日程已删除"
            return "未找到该日程"

        @tool
        def detect_conflicts(start_time: str, end_time: str = "") -> str:
            """检查指定时间段是否与已有日程冲突。start_time 格式：YYYY-MM-DD HH:MM。"""
            user_id = cls._current_user_id
            if not user_id:
                return "无法识别用户身份"

            try:
                start_dt = make_aware(datetime.strptime(start_time, "%Y-%m-%d %H:%M"))
            except ValueError:
                return "时间格式不正确"

            same_day = Schedule.objects.filter(
                user__user_id=user_id,
                status='pending',
                start_time__date=start_dt.date(),
            ).order_by('start_time')

            if not same_day.exists():
                return "该时间段没有冲突"

            lines = [f"当天已有 {same_day.count()} 个日程："]
            for s in same_day:
                t = localtime(s.start_time).strftime("%H:%M")
                lines.append(f"- {t} {s.title}")
            return "\n".join(lines)

        tools = [create_schedule, get_schedules, delete_schedule, detect_conflicts]

        llm = ChatOpenAI(
            model='deepseek-v3.2',
            openai_api_key=os.getenv('API_KEY'),
            openai_api_base=os.getenv('API_BASE'),
            streaming=True,
            request_timeout=30,
            model_kwargs={
                "stream_options": {"include_usage": True}
            }
        ).bind_tools(tools)

        class AgentState(TypedDict):
            messages: Annotated[Sequence[BaseMessage], add_messages]

        def model_call(state: AgentState) -> AgentState:
            res = llm.invoke(state['messages'])
            return {'messages': [res]}

        def should_continue(state: AgentState) -> str:
            last_message = state['messages'][-1]
            if last_message.tool_calls:
                return "tools"
            return "end"

        tool_node = ToolNode(tools)

        graph = StateGraph(AgentState)
        graph.add_node('agent', model_call)
        graph.add_node('tools', tool_node)

        graph.add_edge(START, 'agent')
        graph.add_conditional_edges(
            'agent',
            should_continue,
            {'tools': 'tools', 'end': END}
        )
        graph.add_edge('tools', 'agent')

        return graph.compile()

    # 当前请求的用户 ID，由 chat 视图在调用前设置
    _current_user_id = None
