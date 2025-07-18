# -*- coding: utf-8 -*-
"""
Istio Gateway相关API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict


class ClusterRequest(BaseModel):
    """集群请求模型"""

    cluster_name: str
    force_refresh: Optional[bool] = False


class GatewayRequest(BaseModel):
    """Gateway请求模型"""

    cluster_name: str
    namespace: Optional[str] = "istio-system"


class RefreshRequest(BaseModel):
    """刷新请求模型"""

    force_refresh: Optional[bool] = False


def create_server_gateway_router(server_mode_instance) -> APIRouter:
    """创建Server模式的Istio Gateway API路由"""
    router = APIRouter(prefix="/istio/gateway", tags=["Istio Gateway - Server"])

    @router.post("/list")
    async def list_gateways(request: GatewayRequest):
        """列出指定集群和命名空间的Gateway"""
        cluster_name = request.cluster_name
        namespace = request.namespace
        try:
            # 获取或创建客户端
            if cluster_name not in server_mode_instance.cluster_clients:
                client_instance = await server_mode_instance._create_k8s_client(
                    cluster_name
                )
                if not client_instance:
                    return {"code": 404, "message": "集群不存在或连接失败"}
                server_mode_instance.cluster_clients[cluster_name] = client_instance

            dynamic_client = server_mode_instance.cluster_clients[cluster_name]

            # 获取Gateway资源
            gateway_api = dynamic_client.resources.get(
                api_version="networking.istio.io/v1beta1", kind="Gateway"
            )
            gateways = gateway_api.get(namespace=namespace)

            return {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "namespace": namespace,
                    "gateway_count": len(gateways.items),
                    "gateways": [
                        {
                            "name": gw.metadata.name,
                            "namespace": gw.metadata.namespace,
                            "servers": gw.spec.get("servers", []),
                            "selector": gw.spec.get("selector", {}),
                        }
                        for gw in gateways.items
                    ],
                },
            }

        except Exception as e:
            server_mode_instance.logger.error(
                "获取集群 %s Gateway列表失败: %s", cluster_name, e
            )
            return {"code": 500, "message": f"获取Gateway列表失败: {str(e)}"}

    return router


def create_instant_gateway_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的Istio Gateway API路由"""
    router = APIRouter(prefix="/istio/gateway", tags=["Istio Gateway - Instant"])

    @router.post("/list")
    async def list_gateways(request: RefreshRequest):
        """列出Gateway"""
        try:
            # 获取Gateway资源
            gateway_api = instant_mode_instance.dynamic_client.resources.get(
                api_version="networking.istio.io/v1beta1", kind="Gateway"
            )
            gateways = gateway_api.get()

            return {
                "code": 200,
                "data": {
                    "gateway_count": len(gateways.items),
                    "gateways": [
                        {
                            "name": gw.metadata.name,
                            "namespace": gw.metadata.namespace,
                            "servers": gw.spec.get("servers", []),
                            "selector": gw.spec.get("selector", {}),
                        }
                        for gw in gateways.items
                    ],
                },
            }
        except Exception as e:
            instant_mode_instance.logger.error("获取Gateway列表失败: %s", e)
            return {"code": 500, "message": f"获取Gateway列表失败: {str(e)}"}

    return router
