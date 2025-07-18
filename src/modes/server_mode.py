# -*- coding: utf-8 -*-
"""
Server模式
支持多集群管理，使用轻量化数据库存储集群配置
"""

import json
import sqlite3
from typing import Dict, List, Optional

import yaml
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel
from kubernetes import client
from kubernetes.dynamic import DynamicClient

from src.core.config import Settings
from src.core.cluster_monitor import ClusterMonitor
from .base_mode import BaseMode
from .k8s.cluster_management_api import create_server_cluster_router
from .k8s.cluster_overview_api import create_server_overview_router
from .k8s.resource_api import create_server_resource_router
from .istio.gateway_api import create_server_gateway_router


# 模型类已移至各自的API文件中


class ServerMode(BaseMode):
    """Server模式实现"""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.app = None
        self.db_path = "cloudpilot.db"
        self.cluster_clients: Dict[str, DynamicClient] = {}
        self.cluster_monitors: Dict[str, ClusterMonitor] = {}
        self._init_database()

    def _init_database(self):
        """初始化数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 创建集群配置表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    api_server TEXT NOT NULL,
                    token TEXT,
                    kubeconfig TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.commit()
            conn.close()
            self.logger.info("数据库初始化成功")

        except Exception as e:
            self.logger.error("数据库初始化失败: %s", e)
            raise

    def _save_cluster_config(self, cluster_config):
        """保存集群配置到数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO clusters 
                (name, api_server, token, kubeconfig, description, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    cluster_config.name,
                    cluster_config.api_server,
                    cluster_config.token,
                    cluster_config.kubeconfig,
                    cluster_config.description,
                ),
            )

            conn.commit()
            conn.close()
            self.logger.info("集群配置 %s 保存成功", cluster_config.name)

        except Exception as e:
            self.logger.error("保存集群配置失败: %s", e)
            raise

    def _get_cluster_configs(self) -> List[Dict]:
        """获取所有集群配置"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM clusters ORDER BY created_at DESC")
            rows = cursor.fetchall()

            columns = [description[0] for description in cursor.description]
            clusters = [dict(zip(columns, row)) for row in rows]

            conn.close()
            return clusters

        except Exception as e:
            self.logger.error("获取集群配置失败: %s", e)
            return []

    def _get_cluster_config(self, cluster_name: str) -> Optional[Dict]:
        """获取指定集群配置"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM clusters WHERE name = ?", (cluster_name,))
            row = cursor.fetchone()

            if row:
                columns = [description[0] for description in cursor.description]
                cluster = dict(zip(columns, row))
                conn.close()
                return cluster

            conn.close()
            return None

        except Exception as e:
            self.logger.error("获取集群配置失败: %s", e)
            return None

    async def _create_k8s_client(self, cluster_name: str) -> Optional[DynamicClient]:
        """为指定集群创建Kubernetes客户端"""
        cluster_config = self._get_cluster_config(cluster_name)
        if not cluster_config:
            return None

        try:
            # 创建配置对象
            configuration = client.Configuration()

            if cluster_config["kubeconfig"]:
                # 使用kubeconfig
                # TODO: 完整解析kubeconfig，目前简化处理
                configuration.host = cluster_config["api_server"]
                if cluster_config["token"]:
                    configuration.api_key = {
                        "authorization": f"Bearer {cluster_config['token']}"
                    }
            else:
                # 使用API Server和Token
                configuration.host = cluster_config["api_server"]
                if cluster_config["token"]:
                    configuration.api_key = {
                        "authorization": f"Bearer {cluster_config['token']}"
                    }

            # 跳过SSL验证（生产环境需要配置证书）
            configuration.verify_ssl = False

            # 创建API客户端
            api_client = client.ApiClient(configuration)
            dynamic_client = DynamicClient(api_client)

            self.logger.info("集群 %s 的Kubernetes客户端创建成功", cluster_name)
            return dynamic_client

        except Exception as e:
            self.logger.error("创建集群 %s 的Kubernetes客户端失败: %s", cluster_name, e)
            return None

    async def _get_cluster_monitor(self, cluster_name: str) -> Optional[ClusterMonitor]:
        """获取或创建指定集群的监控器"""
        # 如果监控器已存在，直接返回
        if cluster_name in self.cluster_monitors:
            return self.cluster_monitors[cluster_name]

        # 获取或创建客户端
        if cluster_name not in self.cluster_clients:
            client_instance = await self._create_k8s_client(cluster_name)
            if not client_instance:
                return None
            self.cluster_clients[cluster_name] = client_instance

        # 创建监控器
        dynamic_client = self.cluster_clients[cluster_name]
        monitor = ClusterMonitor(dynamic_client, cache_ttl=30)
        self.cluster_monitors[cluster_name] = monitor

        self.logger.info("集群 %s 的监控器创建成功", cluster_name)
        return monitor

    def _create_app(self) -> FastAPI:
        """创建FastAPI应用"""
        app = FastAPI(
            title=self.settings.app_name,
            version=self.settings.version,
            description="AIOps CloudPilot - Server模式",
        )

        # 基础路由
        @app.get("/")
        async def root():
            return {
                "code": 200,
                "data": {
                    "message": "AIOps CloudPilot - Server模式",
                    "version": self.settings.version,
                    "mode": "server",
                },
            }

        @app.get("/docs", include_in_schema=False)
        async def custom_swagger_ui_html():
            return get_swagger_ui_html(
                openapi_url=app.openapi_url, title="CloudPilot APIs"
            )

        @app.get("/health")
        async def health():
            """健康检查"""
            return {"code": 200, "data": {"status": "healthy", "mode": "server"}}

        # 注册K8s相关路由
        app.include_router(create_server_cluster_router(self))
        app.include_router(create_server_overview_router(self))
        app.include_router(create_server_resource_router(self))

        # 注册Istio相关路由
        app.include_router(create_server_gateway_router(self))

        return app

    async def start(self, host: str = "0.0.0.0", port: int = 8000):
        """启动Server模式"""
        self.logger.info("正在启动Server模式...")

        # 创建FastAPI应用
        self.app = self._create_app()

        # 启动服务
        config = uvicorn.Config(
            self.app, host=host, port=port, log_level=self.settings.log_level.lower()
        )
        server = uvicorn.Server(config)

        self.logger.info("Server模式启动成功，监听 %s:%d", host, port)
        await server.serve()

    async def stop(self):
        """停止服务"""
        self.logger.info("正在停止Server模式...")
        # 关闭所有客户端连接
        for client_instance in self.cluster_clients.values():
            try:
                await client_instance.client.close()
            except Exception as e:
                self.logger.error("关闭客户端连接失败: %s", e)
        self.cluster_clients.clear()
        self.cluster_monitors.clear()
