"""
Repo2Doc Agent 配置加载器

加载和管理配置
"""

import os
import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv


# 加载环境变量
load_dotenv()


class AgentConfig(BaseModel):
    """Agent 配置"""
    max_iterations: int = Field(default=5, description="最大探索迭代次数")
    max_tool_calls_per_iteration: int = Field(default=10, description="每次迭代最大工具调用数")
    confidence_threshold: float = Field(default=0.75, description="完成置信度阈值")


class FileFilterConfig(BaseModel):
    """文件筛选配置"""
    include_extensions: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    max_file_size: int = Field(default=102400, description="最大文件大小（字节）")


class LLMConfig(BaseModel):
    """LLM 配置"""
    model: str = Field(default="qwen3-max")
    temperature: float = Field(default=0.3)
    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    
    def __init__(self, **data):
        super().__init__(**data)
        # 从环境变量获取 API 密钥（如果未设置）
        if self.api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY")
        if self.base_url is None:
            self.base_url = os.getenv("OPENAI_BASE_URL")


class OutputConfig(BaseModel):
    """输出配置"""
    output_dir: str = Field(default="./repo2doc-output")
    filename: str = Field(default="requirements.md")
    save_intermediate: bool = Field(default=True)


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = Field(default="INFO")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class Config(BaseModel):
    """主配置类"""
    agent: AgentConfig = Field(default_factory=AgentConfig)
    file_filter: FileFilterConfig = Field(default_factory=FileFilterConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """
        加载配置
        
        Args:
            config_path: 配置文件路径（可选）
        
        Returns:
            配置对象
        """
        config_data = {}
        
        if config_path:
            path = Path(config_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}
        
        return cls(**config_data)


def setup_logging(config: LoggingConfig) -> None:
    """
    设置日志
    
    Args:
        config: 日志配置
    """
    logging.basicConfig(
        level=getattr(logging, config.level.upper(), logging.INFO),
        format=config.format,
    )
