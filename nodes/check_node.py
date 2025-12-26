"""
完整性检查节点

评估文档完整性，决定是否需要继续探索
"""

import logging
import json
import re
from typing import Tuple

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from state import AgentState
from config_loader import Config
from prompts.agent_prompts import CHECK_COMPLETENESS_PROMPT


logger = logging.getLogger(__name__)


def check_completeness_node(state: AgentState, config: Config) -> AgentState:
    """
    完整性检查节点
    
    评估当前文档的完整性：
    1. 使用 LLM 分析文档质量
    2. 识别缺失或不确定的部分
    3. 决定是否继续探索
    
    Args:
        state: 当前状态
        config: 配置对象
    
    Returns:
        更新后的状态
    """
    logger.info("检查文档完整性...")
    
    # 检查是否达到最大迭代次数
    if state["iteration_count"] >= state["max_iterations"]:
        logger.info(f"已达到最大迭代次数 {state['max_iterations']}，停止探索")
        state["is_complete"] = True
        state["status"] = "completed"
        return state
    
    # 创建 LLM 客户端
    llm = _create_llm(config)
    
    # 初始化或获取 LLM 使用量统计
    llm_usage = state.get("llm_usage", {
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "calls": []
    })
    
    # 评估完整性
    is_complete, confidence, missing_parts, suggested_tools, usage = _evaluate_completeness(
        llm,
        state["current_document"],
        state["high_level_info"],
        state["iteration_count"],
        config
    )
    
    # 记录 token 使用量
    if usage:
        llm_usage["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
        llm_usage["total_completion_tokens"] += usage.get("completion_tokens", 0)
        llm_usage["total_tokens"] += usage.get("total_tokens", 0)
        llm_usage["calls"].append({
            "iteration": state["iteration_count"],
            "type": "check_completeness",
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0)
        })
    
    # 使用配置的置信度阈值判断是否完成
    confidence_threshold = config.agent.confidence_threshold
    
    # 如果置信度达到阈值，则判定完成
    should_complete = is_complete or (
        confidence >= confidence_threshold
    )
    
    # 更新状态
    state["is_complete"] = should_complete
    state["confidence_score"] = confidence
    state["missing_parts"] = missing_parts
    state["llm_usage"] = llm_usage
    
    if should_complete:
        state["status"] = "completed"
        logger.info(f"文档已完整，置信度: {confidence:.2f}")
    else:
        state["status"] = "needs_exploration"
        # 存储建议的工具调用供后续使用
        state["current_tool_results"] = json.dumps(suggested_tools, ensure_ascii=False)
        logger.info(f"文档不完整，需要继续探索。缺失: {missing_parts}")
    
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


def _evaluate_completeness(
    llm: ChatOpenAI,
    document: str,
    high_level_info: str,
    iteration: int,
    config: Config
) -> Tuple[bool, float, list[str], list[dict], dict]:
    """
    评估文档完整性
    
    Returns:
        (is_complete, confidence_score, missing_parts, suggested_tools, usage)
    """
    messages = [
        SystemMessage(content="你是一个需求文档质量评估专家。请严格按照 JSON 格式返回评估结果。"),
        HumanMessage(content=CHECK_COMPLETENESS_PROMPT.format(
            document=document,
            high_level_info=high_level_info,
            iteration=iteration,
            max_iterations=config.agent.max_iterations
        ))
    ]
    
    response = llm.invoke(messages)
    usage = _extract_usage(response)
    
    # 解析响应
    try:
        # 尝试从响应中提取 JSON
        content = response.content
        
        # 查找 JSON 块
        json_match = re.search(r'\{[\s\S]*\}', content)
        
        if json_match:
            result = json.loads(json_match.group())
        else:
            # 如果没有找到 JSON，使用默认值
            logger.warning("无法解析 LLM 响应中的 JSON，使用默认值")
            result = {
                "is_complete": iteration >= 3,  # 至少完成 3 次迭代
                "confidence_score": 0.7,
                "missing_parts": [],
                "suggested_tools": []
            }
        
        return (
            result.get("is_complete", False),
            result.get("confidence_score", 0.5),
            result.get("missing_parts", []),
            result.get("suggested_tools", []),
            usage
        )
    
    except json.JSONDecodeError as e:
        logger.error(f"解析评估结果失败: {e}")
        # 返回保守估计
        return (False, 0.5, ["无法评估"], [], usage)
