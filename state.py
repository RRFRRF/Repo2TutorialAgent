"""
Repo2Doc Agent 状态管理模块

定义 LangGraph Agent 工作流的状态数据结构
"""

from typing import TypedDict, Optional, Annotated
from dataclasses import dataclass, field
from operator import add


@dataclass
class ToolCall:
    """工具调用记录"""
    tool_name: str           # 工具名称
    arguments: dict          # 调用参数
    result: str = ""         # 执行结果
    success: bool = True     # 是否成功


@dataclass
class ExplorationRecord:
    """探索记录"""
    iteration: int           # 迭代次数
    action: str              # 执行的动作描述
    findings: str            # 发现的内容
    tool_calls: list[ToolCall] = field(default_factory=list)


class AgentState(TypedDict):
    """
    Repo2Doc Agent 工作流状态
    
    这是 LangGraph Agent 工作流的核心状态对象，
    在各个节点之间传递和更新。
    """
    # 输入参数
    repo_path: str                              # 仓库路径
    config_path: Optional[str]                  # 配置文件路径
    
    # 初始化阶段收集的信息
    readme_content: str                         # README 内容
    directory_tree: str                         # 目录结构树
    project_files: list[str]                    # 项目配置文件列表
    high_level_info: str                        # 高层信息汇总
    
    # Agent 探索阶段
    messages: Annotated[list, add]              # 消息历史（用于 Agent）
    exploration_history: list[ExplorationRecord]  # 探索历史记录
    current_tool_results: str                   # 当前工具调用结果
    
    # 文档生成阶段
    current_document: str                       # 当前生成的文档
    document_versions: list[str]                # 文档版本历史
    
    # 完整性检查
    is_complete: bool                           # 文档是否完整
    missing_parts: list[str]                    # 缺失的部分
    confidence_score: float                     # 置信度分数 (0-1)
    
    # 循环控制
    iteration_count: int                        # 当前迭代次数
    max_iterations: int                         # 最大迭代次数
    
    # 状态信息
    status: str                                 # 当前状态
    error: Optional[str]                        # 错误信息
    
    # LLM 使用量统计（真实值）
    llm_usage: dict                             # LLM token 使用量


def create_initial_state(
    repo_path: str, 
    config_path: Optional[str] = None,
    max_iterations: int = 10
) -> AgentState:
    """
    创建初始状态
    
    Args:
        repo_path: 仓库路径
        config_path: 配置文件路径（可选）
        max_iterations: 最大迭代次数
    
    Returns:
        初始化的状态对象
    """
    return AgentState(
        repo_path=repo_path,
        config_path=config_path,
        readme_content="",
        directory_tree="",
        project_files=[],
        high_level_info="",
        messages=[],
        exploration_history=[],
        current_tool_results="",
        current_document="",
        document_versions=[],
        is_complete=False,
        missing_parts=[],
        confidence_score=0.0,
        iteration_count=0,
        max_iterations=max_iterations,
        status="initialized",
        error=None,
        llm_usage={
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "calls": []
        },
    )
