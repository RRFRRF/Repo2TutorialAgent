"""
Mermaid 语法修复工具

用于自动修复 LLM 生成的 Mermaid 图表中的常见语法错误
"""

import re

def fix_mermaid_syntax(markdown_content: str) -> str:
    """
    修复 Markdown 内容中的 Mermaid 语法错误
    
    Args:
        markdown_content: 原始 Markdown 内容
        
    Returns:
        修复后的内容
    """
    # 匹配 mermaid 代码块
    pattern = r"```mermaid\n(.*?)```"
    
    def replace_block(match):
        content = match.group(1)
        fixed_content = _fix_mermaid_block(content)
        return f"```mermaid\n{fixed_content}```"
    
    return re.sub(pattern, replace_block, markdown_content, flags=re.DOTALL)


def _fix_mermaid_block(content: str) -> str:
    """修复单个 Mermaid 代码块"""
    lines = content.split('\n')
    fixed_lines = []
    
    # 节点定义的正则：ID[Text] 或 ID(Text) 等
    # 捕获组：
    # 1: ID
    # 2: 开口符号 ([({
    # 3: 内容
    # 4: 闭合符号 )]})
    node_pattern = re.compile(r'([A-Za-z0-9_]+)\s*(\[|\(|\{\{|\(\[|\[\()(.+?)(\]|\)|\}\}|\)\]|\)\])')
    
    for line in lines:
        line = line.rstrip()
        if not line:
            fixed_lines.append(line)
            continue
            
        # 尝试修复节点定义
        # 查找行中所有的节点定义
        def fix_node(match):
            node_id = match.group(1)
            open_sym = match.group(2)
            text = match.group(3)
            close_sym = match.group(4)
            
            # 如果已经是双引号包裹，尝试通过，但要检查内部是否转义
            if text.startswith('"') and text.endswith('"'):
                return match.group(0)
            
            # 转义内部的双引号
            text = text.replace('"', "'")
            
            # 强制使用双引号包裹
            # 注意：不同形状的节点有不同的语法，但文本部分都可以用双引号
            # 例如 A[Text] -> A["Text"]
            # A(Text) -> A("Text")
            return f'{node_id}{open_sym}"{text}"{close_sym}'
            
        # 替换节点定义
        # 注意：这个简单的正则可能无法处理嵌套或极其复杂的情况，但能处理大部分常见错误
        try:
            # 排除已经是引号包裹的情况 (简单的排除)
            if '["' not in line and '("' not in line:
                line = node_pattern.sub(fix_node, line)
        except Exception:
            pass # 如果修复失败，保留原样
            
        # 修复箭头上的特殊字符
        # A -->|Text| B  =>  A -->|"Text"| B
        arrow_pattern = re.compile(r'(\|)([^"]+?)(\|)')
        def fix_arrow(match):
            return f'|"{match.group(2)}"|'
            
        if '-->|' in line or '-.->|' in line:
            try:
                line = arrow_pattern.sub(fix_arrow, line)
            except Exception:
                pass
                
        fixed_lines.append(line)
        
    return '\n'.join(fixed_lines)
