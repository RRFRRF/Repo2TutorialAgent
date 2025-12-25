"""
LangGraph Agent 工作流定义

定义 Repo2Doc Agent 的完整工作流
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from state import AgentState, create_initial_state
from config_loader import Config, setup_logging
from nodes.init_node import init_node
from nodes.doc_node import generate_doc_node
from nodes.check_node import check_completeness_node
from nodes.tool_node import tool_execution_node
from nodes.save_node import save_output_node


logger = logging.getLogger(__name__)


class Repo2DocAgentWorkflow:
    """
    Repo2Doc Agent LangGraph 工作流
    
    工作流程：
    1. init_node: 初始化，收集高层信息
    2. doc_node: 生成/更新文档
    3. check_node: 检查完整性
    4. tool_node: 执行工具调用（如果需要继续探索）
    5. 循环回到 doc_node 直到完整
    """
    
    def __init__(self, config: Config):
        """
        初始化工作流
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """
        构建 LangGraph 工作流图
        
        Returns:
            编译后的工作流图
        """
        # 创建状态图
        workflow = StateGraph(AgentState)
        
        # 添加节点
        workflow.add_node("init", self._wrap_node(init_node))
        workflow.add_node("generate_doc", self._wrap_node(generate_doc_node))
        workflow.add_node("check_completeness", self._wrap_node(check_completeness_node))
        workflow.add_node("execute_tools", self._wrap_node(tool_execution_node))
        workflow.add_node("save_output", self._wrap_node(save_output_node))
        
        # 设置入口点
        workflow.set_entry_point("init")
        
        # 添加边
        # init -> generate_doc
        workflow.add_conditional_edges(
            "init",
            self._check_error,
            {
                "continue": "generate_doc",
                "error": END,
            }
        )
        
        # generate_doc -> check_completeness
        workflow.add_conditional_edges(
            "generate_doc",
            self._check_error,
            {
                "continue": "check_completeness",
                "error": END,
            }
        )
        
        # check_completeness -> save_output (if complete) or execute_tools (if not)
        workflow.add_conditional_edges(
            "check_completeness",
            self._route_after_check,
            {
                "complete": "save_output",
                "explore": "execute_tools",
                "error": END,
            }
        )
        
        # execute_tools -> generate_doc (循环)
        workflow.add_conditional_edges(
            "execute_tools",
            self._check_error,
            {
                "continue": "generate_doc",
                "error": END,
            }
        )
        
        # save_output -> END
        workflow.add_edge("save_output", END)
        
        # 编译图
        return workflow.compile()
    
    def _wrap_node(self, node_func):
        """
        包装节点函数，注入配置
        
        Args:
            node_func: 节点函数
        
        Returns:
            包装后的函数
        """
        def wrapped(state: AgentState) -> AgentState:
            return node_func(state, self.config)
        return wrapped
    
    def _check_error(self, state: AgentState) -> Literal["continue", "error"]:
        """
        检查是否有错误
        
        Args:
            state: 当前状态
        
        Returns:
            路由决策
        """
        if state.get("status") == "error":
            logger.error(f"工作流错误: {state.get('error')}")
            return "error"
        return "continue"
    
    def _route_after_check(self, state: AgentState) -> Literal["complete", "explore", "error"]:
        """
        完整性检查后的路由决策
        
        Args:
            state: 当前状态
        
        Returns:
            路由决策
        """
        if state.get("status") == "error":
            return "error"
        
        if state.get("is_complete", False):
            return "complete"
        
        return "explore"
    
    def run(self, repo_path: str, config_path: str = None) -> AgentState:
        """
        运行工作流
        
        Args:
            repo_path: 仓库路径
            config_path: 配置文件路径（可选）
        
        Returns:
            最终状态
        """
        logger.info(f"开始处理仓库: {repo_path}")
        
        # 创建初始状态
        initial_state = create_initial_state(
            repo_path, 
            config_path,
            max_iterations=self.config.agent.max_iterations
        )
        
        # 运行工作流，设置递归限制以支持多次迭代
        # 每次迭代约2-4个节点，max_iterations为10时需要约40-80次递归
        recursion_limit = self.config.agent.max_iterations * 10 + 20
        final_state = self.graph.invoke(
            initial_state,
            {"recursion_limit": recursion_limit}
        )
        
        # 输出结果
        if final_state.get("status") == "completed":
            logger.info("✅ 工作流完成")
            logger.info(f"   迭代次数: {final_state.get('iteration_count', 0)}")
            logger.info(f"   文档长度: {len(final_state.get('current_document', ''))} 字符")
            logger.info(f"   置信度: {final_state.get('confidence_score', 0):.2f}")
        else:
            logger.error(f"❌ 工作流失败: {final_state.get('error')}")
        
        return final_state


def create_workflow(config_path: str = None) -> Repo2DocAgentWorkflow:
    """
    创建工作流实例
    
    Args:
        config_path: 配置文件路径（可选）
    
    Returns:
        工作流实例
    """
    # 加载配置
    config = Config.load(config_path)
    
    # 设置日志
    setup_logging(config.logging)
    
    # 创建工作流
    return Repo2DocAgentWorkflow(config)


def run_workflow(repo_path: str, config_path: str = None) -> AgentState:
    """
    便捷函数：创建并运行工作流
    
    Args:
        repo_path: 仓库路径
        config_path: 配置文件路径（可选）
    
    Returns:
        最终状态
    """
    workflow = create_workflow(config_path)
    return workflow.run(repo_path, config_path)
