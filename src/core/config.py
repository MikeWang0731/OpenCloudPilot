# -*- coding: utf-8 -*-
"""
配置管理模块
支持从环境变量、配置文件等多种方式加载配置
"""

import os
import yaml
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatabaseConfig:
    """数据库配置"""

    url: str = "sqlite:///./cloudpilot.db"
    echo: bool = False


@dataclass
class K8sConfig:
    """Kubernetes配置"""

    in_cluster: bool = True  # 是否在集群内运行
    kubeconfig_path: Optional[str] = None
    api_server: Optional[str] = None
    token: Optional[str] = None


@dataclass
class LLMConfig:
    """大模型配置"""

    provider: str = "openai"  # openai, ollama
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "gpt-3.5-turbo"


@dataclass
class Settings:
    """全局配置类"""

    # 基础配置
    app_name: str = "AIOps CloudPilot"
    version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # 子配置
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    k8s: K8sConfig = field(default_factory=K8sConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    def __init__(self, config_file: Optional[str] = None):
        """初始化配置"""
        # 设置默认值
        self.database = DatabaseConfig()
        self.k8s = K8sConfig()
        self.llm = LLMConfig()

        # 从环境变量加载
        self._load_from_env()

        # 从配置文件加载
        if config_file:
            self._load_from_file(config_file)

    def _load_from_env(self):
        """从环境变量加载配置"""
        # 基础配置
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # 数据库配置
        if db_url := os.getenv("DATABASE_URL"):
            self.database.url = db_url

        # K8s配置
        self.k8s.in_cluster = os.getenv("K8S_IN_CLUSTER", "true").lower() == "true"
        if kubeconfig := os.getenv("KUBECONFIG"):
            self.k8s.kubeconfig_path = kubeconfig
        if api_server := os.getenv("K8S_API_SERVER"):
            self.k8s.api_server = api_server
        if token := os.getenv("K8S_TOKEN"):
            self.k8s.token = token

        # LLM配置
        if provider := os.getenv("LLM_PROVIDER"):
            self.llm.provider = provider
        if api_key := os.getenv("LLM_API_KEY"):
            self.llm.api_key = api_key
        if base_url := os.getenv("LLM_BASE_URL"):
            self.llm.base_url = base_url
        if model := os.getenv("LLM_MODEL"):
            self.llm.model = model

    def _load_from_file(self, config_file: str):
        """从配置文件加载配置"""
        config_path = Path(config_file)
        if not config_path.exists():
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            # 更新配置
            self._update_from_dict(config_data)
        except Exception as e:
            print(f"加载配置文件失败: {e}")

    def _update_from_dict(self, config_data: Dict[str, Any]):
        """从字典更新配置"""
        if not config_data:
            return

        # 基础配置
        for key in ["app_name", "version", "debug", "log_level"]:
            if key in config_data:
                setattr(self, key, config_data[key])

        # 数据库配置
        if "database" in config_data:
            db_config = config_data["database"]
            for key in ["url", "echo"]:
                if key in db_config:
                    setattr(self.database, key, db_config[key])

        # K8s配置
        if "k8s" in config_data:
            k8s_config = config_data["k8s"]
            for key in ["in_cluster", "kubeconfig_path", "api_server", "token"]:
                if key in k8s_config:
                    setattr(self.k8s, key, k8s_config[key])

        # LLM配置
        if "llm" in config_data:
            llm_config = config_data["llm"]
            for key in ["provider", "api_key", "base_url", "model"]:
                if key in llm_config:
                    setattr(self.llm, key, llm_config[key])
