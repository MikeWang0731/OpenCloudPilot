# -*- coding: utf-8 -*-
"""
Kubernetes集群管理相关API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
from kubernetes import client


class ClusterConfig(BaseModel):
    """集群配置模型"""

    name: str
    api_server: str
    token: Optional[str] = None
    kubeconfig: Optional[str] = None
    description: Optional[str] = None


class ClusterRequest(BaseModel):
    """集群请求模型"""

    cluster_name: str
    force_refresh: Optional[bool] = False


def create_server_cluster_router(server_mode_instance) -> APIRouter:
    """创建Server模式的集群管理API路由"""
    router = APIRouter(prefix="/k8s/cluster", tags=["K8s Cluster - Server"])

    @router.post("/add")
    async def add_cluster(cluster_config: ClusterConfig):
        """添加集群配置"""
        try:
            server_mode_instance._save_cluster_config(cluster_config)
            return {"code": 200, "message": f"集群 {cluster_config.name} 添加成功"}
        except Exception as e:
            return {"code": 500, "message": f"添加集群失败: {str(e)}"}

    @router.get("/list")
    async def list_clusters():
        """获取所有集群列表"""
        try:
            clusters = server_mode_instance._get_cluster_configs()
            # 隐藏敏感信息
            for cluster in clusters:
                cluster.pop("token", None)
                cluster.pop("kubeconfig", None)
            return {"code": 200, "data": {"clusters": clusters, "count": len(clusters)}}
        except Exception as e:
            return {"code": 500, "message": f"获取集群列表失败: {str(e)}"}

    @router.post("/info")
    async def get_cluster_info(request: ClusterRequest):
        """获取指定集群信息"""
        cluster_name = request.cluster_name
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

            # 获取集群版本信息
            version_api = client.VersionApi(dynamic_client.client)
            version_info = version_api.get_code()

            # 获取节点信息
            v1 = client.CoreV1Api(dynamic_client.client)
            nodes = v1.list_node()

            return {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "cluster_version": version_info.git_version,
                    "node_count": len(nodes.items),
                    "nodes": [
                        {
                            "name": node.metadata.name,
                            "status": (
                                "Ready"
                                if any(
                                    condition.type == "Ready"
                                    and condition.status == "True"
                                    for condition in node.status.conditions
                                )
                                else "NotReady"
                            ),
                        }
                        for node in nodes.items
                    ],
                },
            }

        except Exception as e:
            server_mode_instance.logger.error(
                "获取集群 %s 信息失败: %s", cluster_name, e
            )
            return {"code": 500, "message": f"获取集群信息失败: {str(e)}"}

    return router


def create_instant_cluster_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的集群信息API路由"""
    router = APIRouter(prefix="/k8s/cluster", tags=["K8s Cluster - Instant"])

    @router.get("/info")
    async def cluster_info():
        """获取集群基本信息"""
        try:
            # 获取集群版本信息
            version_api = client.VersionApi(instant_mode_instance.k8s_client)
            version_info = version_api.get_code()

            # 获取节点信息
            v1 = client.CoreV1Api(instant_mode_instance.k8s_client)
            nodes = v1.list_node()

            return {
                "code": 200,
                "data": {
                    "cluster_version": version_info.git_version,
                    "node_count": len(nodes.items),
                    "nodes": [
                        {
                            "name": node.metadata.name,
                            "status": (
                                "Ready"
                                if any(
                                    condition.type == "Ready"
                                    and condition.status == "True"
                                    for condition in node.status.conditions
                                )
                                else "NotReady"
                            ),
                        }
                        for node in nodes.items
                    ],
                },
            }
        except Exception as e:
            instant_mode_instance.logger.error("获取集群信息失败: %s", e)
            return {"code": 500, "message": f"获取集群信息失败: {str(e)}"}

    return router
