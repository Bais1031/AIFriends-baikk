import os
from typing import TypedDict, Annotated, Sequence

from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import ToolNode

from web.models.friend import Friend
from web.utils.memory_retrieval import retrieve_relevant_memories


class MemoryGraph:
    @staticmethod
    def create_app(friend: Friend):
        @tool
        def query_memories(query: str) -> str:
            """搜索已有的长期记忆。输入为搜索查询，返回与查询语义相关的已有记忆列表。
            在提取新记忆前，务必先调用此工具检查是否已有相似记忆，以避免重复提取。
            也能发现矛盾：如果用户改变了偏好，已有记忆可能需要更新而非重复添加。"""
            memories = retrieve_relevant_memories(friend, query, top_k=5)
            if not memories:
                return "未找到相关记忆。"
            lines = []
            for m in memories:
                lines.append(f"- [{m.category}] {m.content} (重要性:{m.importance:.1f}, 权重:{m.weight:.2f})")
            return "找到以下相关记忆：\n" + "\n".join(lines)

        tools = [query_memories]

        llm = ChatOpenAI(
            model='deepseek-v3.2',
            openai_api_key=os.getenv('API_KEY'),
            openai_api_base=os.getenv('API_BASE'),
            request_timeout=30,
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
            {
                'tools': 'tools',
                'end': END,
            }
        )
        graph.add_edge('tools', 'agent')

        return graph.compile()
