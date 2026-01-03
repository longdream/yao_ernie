"""
ACE反思链可视化工具
生成HTML报告展示完整的思考、分析、优化过程
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class ReflectionChainViewer:
    """
    反思链可视化工具
    
    将JSON格式的反思链转换为可视化的HTML报告
    """
    
    @staticmethod
    def generate_html_report(chain_file: str, output_file: Optional[str] = None) -> str:
        """
        生成HTML报告
        
        Args:
            chain_file: 反思链JSON文件路径
            output_file: 输出HTML文件路径（可选，默认为同目录下的.html文件）
            
        Returns:
            生成的HTML文件路径
        """
        # 读取反思链数据
        with open(chain_file, 'r', encoding='utf-8') as f:
            chain_data = json.load(f)
        
        # 确定输出文件路径
        if output_file is None:
            chain_path = Path(chain_file)
            output_file = str(chain_path.parent / f"{chain_path.stem}_report.html")
        
        # 生成HTML内容
        html_content = ReflectionChainViewer._build_html(chain_data)
        
        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_file
    
    @staticmethod
    def _build_html(chain_data: Dict[str, Any]) -> str:
        """构建HTML内容"""
        chain_id = chain_data.get("chain_id", "unknown")
        task_desc = chain_data.get("task_description", "")
        created_at = chain_data.get("created_at", "")
        entries = chain_data.get("entries", [])
        
        # HTML模板
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ACE反思链 - {chain_id}</title>
    <style>
        {ReflectionChainViewer._get_css()}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🧠 ACE反思链报告</h1>
            <div class="meta">
                <div><strong>链ID:</strong> {chain_id}</div>
                <div><strong>创建时间:</strong> {created_at}</div>
                <div><strong>任务描述:</strong> {task_desc}</div>
                <div><strong>条目数:</strong> {len(entries)}</div>
            </div>
        </header>
        
        <div class="timeline">
            {ReflectionChainViewer._build_timeline(entries)}
        </div>
        
        <footer>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Powered by PlanScope ACE</p>
        </footer>
    </div>
</body>
</html>"""
        return html
    
    @staticmethod
    def _get_css() -> str:
        """获取CSS样式"""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
        }
        
        header h1 {
            font-size: 32px;
            margin-bottom: 20px;
        }
        
        .meta {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            font-size: 14px;
        }
        
        .meta div {
            background: rgba(255,255,255,0.1);
            padding: 10px;
            border-radius: 6px;
        }
        
        .timeline {
            padding: 40px;
        }
        
        .entry {
            position: relative;
            padding-left: 40px;
            margin-bottom: 40px;
            border-left: 3px solid #e0e0e0;
        }
        
        .entry::before {
            content: '';
            position: absolute;
            left: -8px;
            top: 0;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: #667eea;
            border: 3px solid white;
            box-shadow: 0 0 0 3px #667eea;
        }
        
        .entry-header {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }
        
        .stage-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .stage-plan_generation { background: #e3f2fd; color: #1976d2; }
        .stage-plan_generation_result { background: #e8f5e9; color: #388e3c; }
        .stage-tool_execution { background: #fff3e0; color: #f57c00; }
        .stage-tool_execution_result { background: #fce4ec; color: #c2185b; }
        .stage-quality_analysis { background: #f3e5f5; color: #7b1fa2; }
        .stage-quality_analysis_result { background: #e0f2f1; color: #00796b; }
        .stage-prompt_optimization { background: #fff9c4; color: #f57f17; }
        
        .timestamp {
            color: #666;
            font-size: 13px;
        }
        
        .entry-content {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
        }
        
        .section {
            margin-bottom: 20px;
        }
        
        .section:last-child {
            margin-bottom: 0;
        }
        
        .section-title {
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .section-content {
            background: white;
            padding: 15px;
            border-radius: 6px;
            border-left: 3px solid #667eea;
        }
        
        .code-block {
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 6px;
            overflow-x: auto;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.5;
        }
        
        .key-value {
            display: grid;
            grid-template-columns: 150px 1fr;
            gap: 10px;
            margin-bottom: 8px;
        }
        
        .key {
            font-weight: 600;
            color: #555;
        }
        
        .value {
            color: #333;
        }
        
        .list {
            list-style: none;
            padding-left: 0;
        }
        
        .list li {
            padding: 8px 12px;
            background: white;
            margin-bottom: 8px;
            border-radius: 4px;
            border-left: 3px solid #667eea;
        }
        
        .list li::before {
            content: '▸ ';
            color: #667eea;
            font-weight: bold;
        }
        
        .diff-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        
        .diff-before, .diff-after {
            background: white;
            padding: 15px;
            border-radius: 6px;
        }
        
        .diff-before {
            border-left: 3px solid #f44336;
        }
        
        .diff-after {
            border-left: 3px solid #4caf50;
        }
        
        .diff-title {
            font-weight: 600;
            margin-bottom: 10px;
            font-size: 13px;
        }
        
        .diff-before .diff-title {
            color: #f44336;
        }
        
        .diff-after .diff-title {
            color: #4caf50;
        }
        
        footer {
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 13px;
        }
        
        footer p {
            margin: 5px 0;
        }
        
        .analysis-box {
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 6px;
            padding: 15px;
            margin-top: 10px;
        }
        
        .analysis-box::before {
            content: '💡 ';
            font-size: 18px;
        }
        """
    
    @staticmethod
    def _build_timeline(entries: list) -> str:
        """构建时间线HTML"""
        html_parts = []
        
        for entry in entries:
            entry_id = entry.get("entry_id", "")
            timestamp = entry.get("timestamp", "")
            stage = entry.get("stage", "unknown")
            input_data = entry.get("input_data", {})
            output_data = entry.get("output_data", {})
            model_info = entry.get("model_info", {})
            analysis = entry.get("analysis", "")
            
            # 构建条目HTML
            entry_html = f"""
            <div class="entry">
                <div class="entry-header">
                    <span class="stage-badge stage-{stage}">{stage.replace('_', ' ')}</span>
                    <span class="timestamp">⏱️ {timestamp}</span>
                </div>
                <div class="entry-content">
                    {ReflectionChainViewer._build_entry_content(stage, input_data, output_data, model_info, analysis)}
                </div>
            </div>
            """
            html_parts.append(entry_html)
        
        return '\n'.join(html_parts)
    
    @staticmethod
    def _build_entry_content(stage: str, input_data: dict, output_data: dict, model_info: dict, analysis: str) -> str:
        """构建条目内容HTML"""
        parts = []
        
        # 输入数据
        if input_data:
            parts.append('<div class="section">')
            parts.append('<div class="section-title">📥 输入</div>')
            parts.append('<div class="section-content">')
            parts.append(ReflectionChainViewer._format_dict(input_data))
            parts.append('</div></div>')
        
        # 输出数据
        if output_data:
            parts.append('<div class="section">')
            parts.append('<div class="section-title">📤 输出</div>')
            parts.append('<div class="section-content">')
            parts.append(ReflectionChainViewer._format_dict(output_data))
            parts.append('</div></div>')
        
        # 模型信息
        if model_info:
            parts.append('<div class="section">')
            parts.append('<div class="section-title">🤖 模型信息</div>')
            parts.append('<div class="section-content">')
            parts.append(ReflectionChainViewer._format_dict(model_info))
            parts.append('</div></div>')
        
        # 分析结果
        if analysis:
            parts.append(f'<div class="analysis-box">{analysis}</div>')
        
        # 特殊处理：Prompt优化对比
        if stage == "prompt_optimization" and "original_prompt" in input_data and "optimized_prompt" in output_data:
            parts.append('<div class="section">')
            parts.append('<div class="section-title">🔄 Prompt优化对比</div>')
            parts.append('<div class="diff-container">')
            parts.append('<div class="diff-before">')
            parts.append('<div class="diff-title">❌ 优化前</div>')
            parts.append(f'<div class="code-block">{ReflectionChainViewer._escape_html(input_data.get("original_prompt", ""))}</div>')
            parts.append('</div>')
            parts.append('<div class="diff-after">')
            parts.append('<div class="diff-title">✅ 优化后</div>')
            parts.append(f'<div class="code-block">{ReflectionChainViewer._escape_html(output_data.get("optimized_prompt", ""))}</div>')
            parts.append('</div>')
            parts.append('</div></div>')
        
        return '\n'.join(parts)
    
    @staticmethod
    def _format_dict(data: dict) -> str:
        """格式化字典为HTML"""
        parts = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                value_str = f'<pre class="code-block">{json.dumps(value, ensure_ascii=False, indent=2)}</pre>'
            else:
                value_str = f'<span class="value">{ReflectionChainViewer._escape_html(str(value))}</span>'
            
            parts.append(f'<div class="key-value"><span class="key">{key}:</span>{value_str}</div>')
        
        return '\n'.join(parts)
    
    @staticmethod
    def _escape_html(text: str) -> str:
        """转义HTML特殊字符"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))


def generate_html_report(chain_file: str, output_file: Optional[str] = None) -> str:
    """
    便捷函数：生成HTML报告
    
    Args:
        chain_file: 反思链JSON文件路径
        output_file: 输出HTML文件路径（可选）
        
    Returns:
        生成的HTML文件路径
    """
    return ReflectionChainViewer.generate_html_report(chain_file, output_file)

