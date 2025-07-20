# -*- coding: utf-8 -*-
"""
即时App模式
直接使用集群内权限，适合作为Pod部署在K8s集群中
"""

from fastapi import FastAPI, Query
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel
from typing import Optional
import uvicorn
from kubernetes import client, config
from kubernetes.dynamic import DynamicClient

from src.core.config import Settings
from src.core.cluster_monitor import ClusterMonitor
from .base_mode import BaseMode
from .k8s.cluster_management_api import create_instant_cluster_router
from .k8s.cluster_overview_api import create_instant_overview_router
from .k8s.resources.pod_api import create_instant_pod_router
from .k8s.resources.deployment_api import create_instant_deployment_router
from .k8s.resources.service_api import create_instant_service_router
from .k8s.resources.node_api import create_instant_node_router
from .k8s.resources.logs_api import create_instant_logs_router
from .k8s.resources.events_api import create_instant_events_router
from .istio.gateway_api import create_instant_gateway_router


# 模型类已移至各自的API文件中


class InstantAppMode(BaseMode):
    """即时App模式实现"""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.app = None
        self.k8s_client = None
        self.dynamic_client = None
        self.cluster_monitor = None

    async def _init_k8s_client(self):
        """初始化Kubernetes客户端"""
        try:
            # 使用集群内配置
            config.load_incluster_config()
            self.logger.info("成功加载集群内Kubernetes配置")

            # 创建API客户端
            api_client = client.ApiClient()
            self.k8s_client = api_client

            # 创建动态客户端
            self.dynamic_client = DynamicClient(api_client)
            self.logger.info("Kubernetes动态客户端初始化成功")

        except Exception as e:
            self.logger.error("初始化Kubernetes客户端失败: %s", e)
            # 尝试使用本地kubeconfig（开发环境）
            try:
                config.load_kube_config()
                api_client = client.ApiClient()
                self.k8s_client = api_client
                self.dynamic_client = DynamicClient(api_client)
                self.logger.info("使用本地kubeconfig初始化成功")
            except Exception as e2:
                self.logger.error("使用本地kubeconfig也失败: %s", e2)
                raise

    def _create_app(self) -> FastAPI:
        """创建FastAPI应用"""
        app = FastAPI(
            title=self.settings.app_name,
            version=self.settings.version,
            description="AIOps CloudPilot - 即时App模式",
        )

        # 基础路由
        @app.get("/")
        async def root():
            return {
                "code": 200,
                "data": {
                    "message": "AIOps CloudPilot - 即时App模式",
                    "version": self.settings.version,
                    "mode": "instant",
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
            return {"code": 200, "data": {"status": "healthy", "mode": "instant"}}

        # 注册K8s相关路由
        app.include_router(create_instant_cluster_router(self))
        app.include_router(create_instant_overview_router(self))

        # 注册K8s资源管理路由
        app.include_router(create_instant_pod_router(self))
        app.include_router(create_instant_deployment_router(self))
        app.include_router(create_instant_service_router(self))
        app.include_router(create_instant_node_router(self))
        app.include_router(create_instant_logs_router(self))
        app.include_router(create_instant_events_router(self))

        # 注册Istio相关路由
        app.include_router(create_instant_gateway_router(self))

        return app

    async def start(self, host: str = "0.0.0.0", port: int = 8000):
        """启动即时App模式"""
        self.logger.info("正在启动即时App模式...")

        # 初始化Kubernetes客户端
        await self._init_k8s_client()

        # 初始化集群监控器
        self.cluster_monitor = ClusterMonitor(self.dynamic_client, cache_ttl=30)

        # 创建FastAPI应用
        self.app = self._create_app()

        # 启动服务
        server_config = uvicorn.Config(
            self.app, host=host, port=port, log_level=self.settings.log_level.lower()
        )
        server = uvicorn.Server(server_config)

        self.logger.info("即时App模式启动成功，监听 %s:%d", host, port)
        await server.serve()

    async def stop(self):
        """停止服务"""
        self.logger.info("正在停止即时App模式...")
        if self.k8s_client:
            await self.k8s_client.close()
