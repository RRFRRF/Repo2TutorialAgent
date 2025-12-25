"""
文档生成节点

使用 LLM 生成或更新需求文档
"""

import logging
from typing import Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from state import AgentState
from config_loader import Config
from prompts.agent_prompts import (
    SYSTEM_PROMPT,
    INITIAL_DOC_PROMPT,
    UPDATE_DOC_PROMPT,
)


logger = logging.getLogger(__name__)


def generate_doc_node(state: AgentState, config: Config) -> AgentState:
    """
    文档生成节点
    
    根据当前信息生成或更新需求文档：
    - 首次调用：基于高层信息生成初版文档
    - 后续调用：基于新工具结果更新文档
    
    Args:
        state: 当前状态
        config: 配置对象
    
    Returns:
        更新后的状态
    """
    logger.info(f"开始生成/更新文档（迭代 {state['iteration_count'] + 1}）...")
    
    # 创建 LLM 客户端
    llm = _create_llm(config)
    
    # 初始化或获取 LLM 使用量统计
    llm_usage = state.get("llm_usage", {
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "calls": []
    })
    
    # 根据是否是首次生成选择不同的策略
    if state["iteration_count"] == 0:
        # 首次生成
        new_document, usage = _generate_initial_doc(
            llm, 
            state["high_level_info"],
            config
        )
        call_type = "initial_doc"
    else:
        # 增量更新
        new_document, usage = _update_document(
            llm,
            state["current_document"],
            state["current_tool_results"],
            state["missing_parts"],
            config
        )
        call_type = "update_doc"
    
    # 记录 token 使用量
    if usage:
        llm_usage["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
        llm_usage["total_completion_tokens"] += usage.get("completion_tokens", 0)
        llm_usage["total_tokens"] += usage.get("total_tokens", 0)
        llm_usage["calls"].append({
            "iteration": state["iteration_count"] + 1,
            "type": call_type,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0)
        })
    
    # 更新状态
    state["current_document"] = new_document
    state["document_versions"].append(new_document)
    state["iteration_count"] += 1
    state["current_tool_results"] = ""  # 清空工具结果
    state["llm_usage"] = llm_usage
    state["status"] = "doc_generated"
    
    logger.info(f"文档生成完成，长度: {len(new_document)} 字符")
    logger.info(f"本次 LLM token: prompt={usage.get('prompt_tokens', 0)}, completion={usage.get('completion_tokens', 0)}")
    
    return state


def _create_llm(config: Config) -> ChatOpenAI:
    """创建 LLM 客户端"""
    kwargs = {
        "model": config.llm.model,
        "temperature": config.llm.temperature,
    }
    
    if config.llm.api_key:
        kwargs["api_key"] = config.llm.api_key
    
    if config.llm.base_url:
        kwargs["base_url"] = config.llm.base_url
    
    return ChatOpenAI(**kwargs)


def _extract_usage(response) -> dict:
    """从响应中提取 token 使用量"""
    usage = {}
    if hasattr(response, 'response_metadata') and response.response_metadata:
        token_usage = response.response_metadata.get('token_usage', {})
        usage = {
            "prompt_tokens": token_usage.get('prompt_tokens', 0),
            "completion_tokens": token_usage.get('completion_tokens', 0),
            "total_tokens": token_usage.get('total_tokens', 0)
        }
    return usage


def _generate_initial_doc(
    llm: ChatOpenAI, 
    high_level_info: str,
    config: Config
) -> Tuple[str, dict]:
    """生成初版文档"""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=INITIAL_DOC_PROMPT.format(
            high_level_info=high_level_info
        ))
    ]
    
    response = llm.invoke(messages)
    usage = _extract_usage(response)
    
    return response.content, usage


def _update_document(
    llm: ChatOpenAI,
    current_document: str,
    tool_results: str,
    missing_parts: list[str],
    config: Config
) -> Tuple[str, dict]:
    """更新文档"""
    missing_str = "\n".join(f"- {part}" for part in missing_parts) if missing_parts else "无"
    
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=UPDATE_DOC_PROMPT.format(
            current_document=current_document,
            tool_results=tool_results,
            missing_parts=missing_str
        ))
    ]
    
    response = llm.invoke(messages)
    usage = _extract_usage(response)
    
    return response.content, usage
