"""
Repo2Doc Agent Web Demo 服务器

基于 Flask 的 Web 界面，用于展示 Agent 工作流的实时运行状态
"""

import json
import queue
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, render_template, request, jsonify

from agent_workflow import Repo2DocAgentWorkflow
from config_loader import Config, setup_logging
from state import AgentState


app = Flask(__name__)

# 存储任务状态的字典
tasks: dict[str, dict] = {}


class StreamingWorkflow:
    """
    支持实时状态推送的工作流包装器
    """
    
    def __init__(self, task_id: str, config_path: str = None):
        self.task_id = task_id
        self.config = Config.load(config_path)
        setup_logging(self.config.logging)
        self.message_queue = queue.Queue()
        self._running = False
    
    def emit(self, event_type: str, data: dict):
        """发送SSE事件到队列"""
        self.message_queue.put({
            "event": event_type,
            "data": data,
            "timestamp": time.time()
        })
    
    def run(self, repo_path: str, config_path: str = None):
        """运行工作流并推送状态"""
        from state import create_initial_state
        from langgraph.graph import StateGraph, END
        from nodes.init_node import init_node
        from nodes.doc_node import generate_doc_node
        from nodes.check_node import check_completeness_node
        from nodes.tool_node import tool_execution_node
        from nodes.save_node import save_output_node
        
        self._running = True
        self.emit("start", {"repo_path": repo_path})
        
        # 包装节点函数以添加状态推送
        def wrap_node(name: str, node_func):
            def wrapped(state: AgentState) -> AgentState:
                self.emit("node_start", {
                    "node": name,
                    "iteration": state.get("iteration_count", 0)
                })
                
                try:
                    result = node_func(state, self.config)
                    
                    # 发送节点完成事件
                    self.emit("node_complete", {
                        "node": name,
                        "iteration": result.get("iteration_count", 0),
                        "status": result.get("status", ""),
                        "confidence": result.get("confidence_score", 0),
                        "document_length": len(result.get("current_document", "")),
                        "is_complete": result.get("is_complete", False),
                        "missing_parts": result.get("missing_parts", []),
                    })
                    
                    # 发送探索历史更新
                    history = result.get("exploration_history", [])
                    if history:
                        latest = history[-1]
                        self.emit("exploration", {
                            "iteration": latest.iteration if hasattr(latest, 'iteration') else latest.get('iteration', 0),
                            "action": latest.action if hasattr(latest, 'action') else latest.get('action', ''),
                            "findings": latest.findings if hasattr(latest, 'findings') else latest.get('findings', ''),
                            "tool_calls": [
                                {
                                    "tool_name": tc.tool_name if hasattr(tc, 'tool_name') else tc.get('tool_name', ''),
                                    "success": tc.success if hasattr(tc, 'success') else tc.get('success', True),
                                }
                                for tc in (latest.tool_calls if hasattr(latest, 'tool_calls') else latest.get('tool_calls', []))
                            ]
                        })
                    
                    return result
                except Exception as e:
                    self.emit("error", {"node": name, "message": str(e)})
                    raise
            return wrapped
        
        try:
            # 构建工作流图
            workflow = StateGraph(AgentState)
            
            workflow.add_node("init", wrap_node("init", init_node))
            workflow.add_node("generate_doc", wrap_node("generate_doc", generate_doc_node))
            workflow.add_node("check_completeness", wrap_node("check_completeness", check_completeness_node))
            workflow.add_node("execute_tools", wrap_node("execute_tools", tool_execution_node))
            workflow.add_node("save_output", wrap_node("save_output", save_output_node))
            
            workflow.set_entry_point("init")
            
            # 添加边
            def check_error(state):
                return "error" if state.get("status") == "error" else "continue"
            
            def route_after_check(state):
                if state.get("status") == "error":
                    return "error"
                if state.get("is_complete", False):
                    return "complete"
                return "explore"
            
            workflow.add_conditional_edges("init", check_error, {"continue": "generate_doc", "error": END})
            workflow.add_conditional_edges("generate_doc", check_error, {"continue": "check_completeness", "error": END})
            workflow.add_conditional_edges("check_completeness", route_after_check, {"complete": "save_output", "explore": "execute_tools", "error": END})
            workflow.add_conditional_edges("execute_tools", check_error, {"continue": "generate_doc", "error": END})
            workflow.add_edge("save_output", END)
            
            graph = workflow.compile()
            
            # 创建初始状态
            initial_state = create_initial_state(
                repo_path,
                config_path,
                max_iterations=self.config.agent.max_iterations
            )
            
            # 运行工作流
            recursion_limit = self.config.agent.max_iterations * 10 + 20
            final_state = graph.invoke(initial_state, {"recursion_limit": recursion_limit})
            
            # 发送完成事件
            if final_state.get("status") == "completed":
                self.emit("complete", {
                    "iteration_count": final_state.get("iteration_count", 0),
                    "confidence_score": final_state.get("confidence_score", 0),
                    "document_length": len(final_state.get("current_document", "")),
                    "document_preview": final_state.get("current_document", "")[:2000],
                })
            else:
                self.emit("failed", {
                    "error": final_state.get("error", "Unknown error")
                })
                
        except Exception as e:
            self.emit("error", {"message": str(e)})
        finally:
            self._running = False
            self.emit("end", {})


@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


@app.route("/api/run", methods=["POST"])
def run_agent():
    """启动 Agent 任务"""
    data = request.get_json()
    repo_path = data.get("repo_path", "").strip()
    
    if not repo_path:
        return jsonify({"error": "请提供仓库路径"}), 400
    
    # 验证路径
    path = Path(repo_path)
    if not path.exists():
        return jsonify({"error": f"路径不存在: {repo_path}"}), 400
    if not path.is_dir():
        return jsonify({"error": f"路径不是目录: {repo_path}"}), 400
    
    # 创建任务
    task_id = str(uuid.uuid4())
    config_path = str(Path(__file__).parent / "config.yaml")
    
    workflow = StreamingWorkflow(task_id, config_path)
    tasks[task_id] = {
        "workflow": workflow,
        "repo_path": repo_path,
        "status": "running",
        "created_at": time.time()
    }
    
    # 在后台线程运行
    def run_task():
        try:
            workflow.run(repo_path, config_path)
            tasks[task_id]["status"] = "completed"
        except Exception as e:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = str(e)
    
    thread = threading.Thread(target=run_task, daemon=True)
    thread.start()
    
    return jsonify({"task_id": task_id})


@app.route("/api/stream/<task_id>")
def stream(task_id: str):
    """SSE 事件流"""
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404
    
    workflow = tasks[task_id]["workflow"]
    
    def generate():
        while True:
            try:
                message = workflow.message_queue.get(timeout=30)
                yield f"event: {message['event']}\ndata: {json.dumps(message['data'], ensure_ascii=False)}\n\n"
                
                if message["event"] == "end":
                    break
            except queue.Empty:
                yield f"event: heartbeat\ndata: {{}}\n\n"
    
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    print("\n🚀 Repo2Doc Agent Demo 服务器启动中...")
    print("📍 访问 http://localhost:5000 开始使用\n")
    app.run(debug=True, port=5000, threaded=True)
