/**
 * Repo2Doc Agent Demo - 前端交互脚本
 */

// DOM 元素
const repoPathInput = document.getElementById('repo-path');
const runBtn = document.getElementById('run-btn');
const logContainer = document.getElementById('log-container');
const docPreview = document.getElementById('doc-preview');
const clearLogBtn = document.getElementById('clear-log');
const missingSection = document.getElementById('missing-section');
const missingList = document.getElementById('missing-list');

// 统计元素
const statIteration = document.getElementById('stat-iteration');
const statConfidence = document.getElementById('stat-confidence');
const statDocLength = document.getElementById('stat-doc-length');
const statStatus = document.getElementById('stat-status');

// 工作流节点元素
const workflowNodes = document.querySelectorAll('.workflow-node');

// 状态
let eventSource = null;
let isRunning = false;

/**
 * 格式化时间戳
 */
function formatTime(date) {
    return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

/**
 * 添加日志条目
 */
function addLog(type, message) {
    // 移除占位符
    const placeholder = logContainer.querySelector('.log-placeholder');
    if (placeholder) {
        placeholder.remove();
    }

    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.innerHTML = `
        <span class="log-time">${formatTime(new Date())}</span>
        <span class="log-type ${type}">[${type.toUpperCase()}]</span>
        <span class="log-message">${escapeHtml(message)}</span>
    `;
    logContainer.appendChild(entry);
    logContainer.scrollTop = logContainer.scrollHeight;
}

/**
 * HTML 转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 更新工作流节点状态
 */
function updateNode(nodeName, status) {
    workflowNodes.forEach(node => {
        if (node.dataset.node === nodeName) {
            node.classList.remove('active', 'completed', 'error');
            if (status) {
                node.classList.add(status);
            }
            const statusEl = node.querySelector('.node-status');
            if (statusEl) {
                if (status === 'active') {
                    statusEl.textContent = '运行中...';
                } else if (status === 'completed') {
                    statusEl.textContent = '完成 ✓';
                } else if (status === 'error') {
                    statusEl.textContent = '错误';
                } else {
                    statusEl.textContent = '';
                }
            }
        }
    });
}

/**
 * 重置所有节点状态
 */
function resetNodes() {
    workflowNodes.forEach(node => {
        node.classList.remove('active', 'completed', 'error');
        const statusEl = node.querySelector('.node-status');
        if (statusEl) {
            statusEl.textContent = '';
        }
    });
}

/**
 * 更新统计信息
 */
function updateStats(data) {
    if (data.iteration !== undefined) {
        statIteration.textContent = data.iteration;
    }
    if (data.confidence !== undefined) {
        statConfidence.textContent = `${(data.confidence * 100).toFixed(1)}%`;
    }
    if (data.document_length !== undefined) {
        statDocLength.textContent = data.document_length.toLocaleString();
    }
}

/**
 * 设置运行状态
 */
function setRunningState(running) {
    isRunning = running;
    runBtn.disabled = running;
    repoPathInput.disabled = running;

    if (running) {
        runBtn.classList.add('running');
        runBtn.querySelector('.btn-text').textContent = '运行中...';
        statStatus.textContent = '运行中';
        statStatus.className = 'stat-value status-badge running';
    } else {
        runBtn.classList.remove('running');
        runBtn.querySelector('.btn-text').textContent = '运行 Agent';
    }
}

/**
 * 设置完成状态
 */
function setCompletedState(success) {
    setRunningState(false);
    if (success) {
        statStatus.textContent = '已完成';
        statStatus.className = 'stat-value status-badge completed';
    } else {
        statStatus.textContent = '失败';
        statStatus.className = 'stat-value status-badge error';
    }
}

/**
 * 处理 SSE 事件
 */
function handleSSEEvent(event, data) {
    switch (event) {
        case 'start':
            addLog('info', `开始分析仓库: ${data.repo_path}`);
            break;

        case 'node_start':
            updateNode(data.node, 'active');
            addLog('info', `节点 [${data.node}] 开始执行 (迭代 ${data.iteration})`);
            break;

        case 'node_complete':
            updateNode(data.node, 'completed');
            addLog('success', `节点 [${data.node}] 执行完成`);
            updateStats({
                iteration: data.iteration,
                confidence: data.confidence,
                document_length: data.document_length
            });

            // 更新缺失部分提示
            if (data.missing_parts && data.missing_parts.length > 0) {
                missingSection.style.display = 'block';
                missingList.innerHTML = data.missing_parts
                    .map(part => `<li>${escapeHtml(part)}</li>`)
                    .join('');
            }
            break;

        case 'exploration':
            if (data.tool_calls && data.tool_calls.length > 0) {
                const toolNames = data.tool_calls.map(tc => tc.tool_name).join(', ');
                addLog('info', `工具调用: ${toolNames}`);
            }
            if (data.findings) {
                addLog('info', `发现: ${data.findings.substring(0, 100)}...`);
            }
            break;

        case 'complete':
            addLog('success', `✅ 分析完成! 迭代 ${data.iteration_count} 次, 置信度 ${(data.confidence_score * 100).toFixed(1)}%`);
            updateStats({
                iteration: data.iteration_count,
                confidence: data.confidence_score,
                document_length: data.document_length
            });

            // 显示文档预览
            if (data.document_preview) {
                docPreview.innerHTML = '';
                docPreview.textContent = data.document_preview;
                if (data.document_length > 2000) {
                    docPreview.textContent += '\n\n... (文档已截断，完整版本请查看输出文件)';
                }
            }
            setCompletedState(true);
            missingSection.style.display = 'none';
            break;

        case 'failed':
            addLog('error', `❌ 分析失败: ${data.error}`);
            setCompletedState(false);
            break;

        case 'error':
            addLog('error', `错误: ${data.message || data.node}`);
            if (data.node) {
                updateNode(data.node, 'error');
            }
            break;

        case 'end':
            addLog('info', '任务结束');
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            break;

        case 'heartbeat':
            // 心跳，忽略
            break;

        default:
            console.log('未知事件:', event, data);
    }
}

/**
 * 启动 Agent 任务
 */
async function runAgent() {
    const repoPath = repoPathInput.value.trim();
    if (!repoPath) {
        alert('请输入仓库路径');
        return;
    }

    // 重置 UI
    resetNodes();
    logContainer.innerHTML = '<div class="log-placeholder">等待运行...</div>';
    docPreview.innerHTML = '<div class="doc-placeholder">文档将在此处显示...</div>';
    missingSection.style.display = 'none';
    statIteration.textContent = '0';
    statConfidence.textContent = '0%';
    statDocLength.textContent = '0';

    setRunningState(true);
    addLog('info', '正在启动 Agent...');

    try {
        // 发送运行请求
        const response = await fetch('/api/run', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ repo_path: repoPath })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || '启动失败');
        }

        const taskId = result.task_id;
        addLog('success', `任务已创建: ${taskId}`);

        // 连接 SSE 事件流
        eventSource = new EventSource(`/api/stream/${taskId}`);

        eventSource.onopen = () => {
            addLog('info', '已连接到事件流');
        };

        eventSource.onerror = (e) => {
            console.error('SSE 错误:', e);
            if (eventSource.readyState === EventSource.CLOSED) {
                addLog('warning', '事件流已关闭');
                setRunningState(false);
            }
        };

        // 监听各种事件
        const eventTypes = ['start', 'node_start', 'node_complete', 'exploration',
            'complete', 'failed', 'error', 'end', 'heartbeat'];

        eventTypes.forEach(eventType => {
            eventSource.addEventListener(eventType, (e) => {
                try {
                    const data = JSON.parse(e.data);
                    handleSSEEvent(eventType, data);
                } catch (err) {
                    console.error('解析事件数据失败:', err);
                }
            });
        });

    } catch (error) {
        addLog('error', `启动失败: ${error.message}`);
        setCompletedState(false);
    }
}

// 事件绑定
runBtn.addEventListener('click', runAgent);

repoPathInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !isRunning) {
        runAgent();
    }
});

clearLogBtn.addEventListener('click', () => {
    logContainer.innerHTML = '<div class="log-placeholder">等待运行...</div>';
});

// 页面关闭时清理
window.addEventListener('beforeunload', () => {
    if (eventSource) {
        eventSource.close();
    }
});
