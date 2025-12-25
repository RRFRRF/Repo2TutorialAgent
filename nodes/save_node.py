"""
保存输出节点

保存最终文档和报告
"""

import logging
from datetime import datetime
from pathlib import Path

from state import AgentState
from config_loader import Config


logger = logging.getLogger(__name__)


def save_output_node(state: AgentState, config: Config) -> AgentState:
    """
    保存输出节点
    
    保存最终文档和处理报告
    
    Args:
        state: 当前状态
        config: 配置对象
    
    Returns:
        更新后的状态
    """
    logger.info("保存输出...")
    
    repo_path = Path(state["repo_path"])
    output_dir = repo_path / config.output.output_dir
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # 保存最终文档
    doc_path = output_dir / config.output.filename
    doc_path_timestamped = output_dir / f"{timestamp}_{config.output.filename}"
    
    document = state.get("current_document", "")
    
    try:
        # 保存主文档
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(document)
        logger.info(f"文档已保存: {doc_path}")
        
        # 保存带时间戳的备份
        with open(doc_path_timestamped, "w", encoding="utf-8") as f:
            f.write(document)
        
        # 生成并保存报告
        report = _generate_report(state, config)
        report_path = output_dir / f"{timestamp}_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"报告已保存: {report_path}")
        
        # 保存 JSON 统计信息
        stats = _generate_stats_json(state, config, timestamp)
        stats_path = output_dir / f"{timestamp}_stats.json"
        import json
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        logger.info(f"统计信息已保存: {stats_path}")
        
        # 保存中间结果（如果启用）
        if config.output.save_intermediate:
            intermediate_dir = output_dir / "intermediate"
            intermediate_dir.mkdir(exist_ok=True)
            
            for i, doc_version in enumerate(state.get("document_versions", [])):
                version_path = intermediate_dir / f"version_{i + 1}.md"
                with open(version_path, "w", encoding="utf-8") as f:
                    f.write(doc_version)
            
            logger.info(f"中间结果已保存到: {intermediate_dir}")
        
        state["status"] = "completed"
        
    except Exception as e:
        logger.error(f"保存输出失败: {e}")
        state["status"] = "error"
        state["error"] = f"保存输出失败: {e}"
    
    return state


def _generate_report(state: AgentState, config: Config) -> str:
    """生成处理报告"""
    lines = [
        "# Repo2Doc Agent 处理报告",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**仓库路径**: {state['repo_path']}",
        "",
        "## 统计信息",
        "",
        f"- 迭代次数: {state.get('iteration_count', 0)}",
        f"- 最终置信度: {state.get('confidence_score', 0):.2f}",
        f"- 文档长度: {len(state.get('current_document', ''))} 字符",
        f"- 文档版本数: {len(state.get('document_versions', []))}",
        "",
        "## 探索历史",
        "",
    ]
    
    for record in state.get("exploration_history", []):
        lines.append(f"### 迭代 {record.iteration}")
        lines.append(f"- 动作: {record.action}")
        lines.append(f"- 发现: {record.findings}")
        
        if record.tool_calls:
            lines.append("- 工具调用:")
            for tc in record.tool_calls:
                status = "✓" if tc.success else "✗"
                lines.append(f"  - {status} {tc.tool_name}")
        lines.append("")
    
    if state.get("missing_parts"):
        lines.append("## 仍需关注的部分")
        lines.append("")
        for part in state["missing_parts"]:
            lines.append(f"- {part}")
        lines.append("")
    
    lines.append("## 配置")
    lines.append("")
    lines.append(f"- 模型: {config.llm.model}")
    lines.append(f"- 最大迭代次数: {config.agent.max_iterations}")
    lines.append(f"- 每次最大工具调用: {config.agent.max_tool_calls_per_iteration}")
    
    return "\n".join(lines)


def _generate_stats_json(state: AgentState, config: Config, timestamp: str) -> dict:
    """
    生成 JSON 格式的统计信息
    
    Args:
        state: 当前状态
        config: 配置对象
        timestamp: 时间戳
    
    Returns:
        统计信息字典
    """
    exploration_history = state.get("exploration_history", [])
    llm_usage = state.get("llm_usage", {})
    
    # 统计工具调用
    total_tool_calls = 0
    successful_tool_calls = 0
    tool_usage = {}
    
    for record in exploration_history:
        for tc in record.tool_calls:
            total_tool_calls += 1
            if tc.success:
                successful_tool_calls += 1
            tool_usage[tc.tool_name] = tool_usage.get(tc.tool_name, 0) + 1
    
    return {
        "meta": {
            "timestamp": timestamp,
            "generated_at": datetime.now().isoformat(),
            "repo_path": state["repo_path"],
            "tool": "repo2docAgent",
            "version": "0.1.0"
        },
        "execution": {
            "total_iterations": state.get("iteration_count", 0),
            "llm_calls": len(llm_usage.get("calls", [])),
            "is_complete": state.get("is_complete", False),
        },
        "llm_tokens": {
            "total_prompt_tokens": llm_usage.get("total_prompt_tokens", 0),
            "total_completion_tokens": llm_usage.get("total_completion_tokens", 0),
            "total_tokens": llm_usage.get("total_tokens", 0),
            "calls": llm_usage.get("calls", []),
        },
        "files": {
            "tool_calls": total_tool_calls,
            "successful_calls": successful_tool_calls,
            "by_tool": tool_usage,
        },
        "document": {
            "final_length": len(state.get("current_document", "")),
            "versions_count": len(state.get("document_versions", [])),
            "confidence_score": state.get("confidence_score", 0),
        },
        "config": {
            "model": config.llm.model,
            "temperature": config.llm.temperature,
            "max_iterations": config.agent.max_iterations,
        }
    }
