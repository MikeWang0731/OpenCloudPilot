# -*- coding: utf-8 -*-
"""
Kubernetes资源管理相关API（Pod、Node、Namespace等）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from kubernetes import client


class ClusterRequest(BaseModel):
    """集群请求模型"""

    cluster_name: str
    force_refresh: Optional[bool] = False


class PodListRequest(BaseModel):
    """Pod列表请求模型"""

    cluster_name: str
    namespace: Optional[str] = "default"


class PodRequest(BaseModel):
    """Pod请求模型"""

    namespace: Optional[str] = "default"


class RefreshRequest(BaseModel):
    """刷新请求模型"""

    force_refresh: Optional[bool] = False


def create_server_resource_router(server_mode_instance) -> APIRouter:
    """创建Server模式的资源管理API路由"""
    router = APIRouter(prefix="/k8s/resource", tags=["K8s Resource - Server"])

    @router.post("/pods")
    async def list_cluster_pods(request: PodListRequest):
        """列出指定集群和命名空间的Pod"""
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
            v1 = client.CoreV1Api(dynamic_client.client)
            pods = v1.list_namespaced_pod(namespace=namespace)

            return {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "namespace": namespace,
                    "pod_count": len(pods.items),
                    "pods": [
                        {
                            "name": pod.metadata.name,
                            "status": pod.status.phase,
                            "ready": sum(
                                1
                                for condition in (pod.status.conditions or [])
                                if condition.type == "Ready"
                                and condition.status == "True"
                            ),
                            "restarts": sum(
                                container.restart_count or 0
                                for container in (pod.status.container_statuses or [])
                            ),
                        }
                        for pod in pods.items
                    ],
                },
            }

        except Exception as e:
            server_mode_instance.logger.error(
                "获取集群 %s Pod列表失败: %s", cluster_name, e
            )
            return {"code": 500, "message": f"获取Pod列表失败: {str(e)}"}

    @router.post("/namespaces")
    async def cluster_namespaces(request: ClusterRequest):
        """获取指定集群的命名空间详细信息"""
        cluster_name = request.cluster_name
        force_refresh = request.force_refresh
        try:
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            namespaces = await monitor.get_namespaces_detail(
                force_refresh=force_refresh
            )
            return {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "count": len(namespaces),
                    "namespaces": [monitor.to_dict(ns) for ns in namespaces],
                },
            }
        except Exception as e:
            server_mode_instance.logger.error(
                "获取集群 %s 命名空间详细信息失败: %s", cluster_name, e
            )
            return {"code": 500, "message": f"获取命名空间信息失败: {str(e)}"}

    @router.post("/nodes")
    async def cluster_nodes(request: ClusterRequest):
        """获取指定集群的节点详细信息"""
        cluster_name = request.cluster_name
        force_refresh = request.force_refresh
        try:
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            nodes = await monitor.get_nodes_detail(force_refresh=force_refresh)
            return {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "count": len(nodes),
                    "nodes": [monitor.to_dict(node) for node in nodes],
                },
            }
        except Exception as e:
            server_mode_instance.logger.error(
                "获取集群 %s 节点详细信息失败: %s", cluster_name, e
            )
            return {"code": 500, "message": f"获取节点信息失败: {str(e)}"}

    return router


def create_instant_resource_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的资源管理API路由"""
    router = APIRouter(prefix="/k8s/resource", tags=["K8s Resource - Instant"])

    @router.post("/pods")
    async def list_pods(request: PodRequest):
        """列出指定命名空间的Pod"""
        namespace = request.namespace
        try:
            v1 = client.CoreV1Api(instant_mode_instance.k8s_client)
            pods = v1.list_namespaced_pod(namespace=namespace)

            return {
                "code": 200,
                "data": {
                    "namespace": namespace,
                    "pod_count": len(pods.items),
                    "pods": [
                        {
                            "name": pod.metadata.name,
                            "status": pod.status.phase,
                            "ready": sum(
                                1
                                for condition in (pod.status.conditions or [])
                                if condition.type == "Ready"
                                and condition.status == "True"
                            ),
                            "restarts": sum(
                                container.restart_count or 0
                                for container in (pod.status.container_statuses or [])
                            ),
                        }
                        for pod in pods.items
                    ],
                },
            }
        except Exception as e:
            instant_mode_instance.logger.error("获取Pod列表失败: %s", e)
            return {"code": 500, "message": f"获取Pod列表失败: {str(e)}"}

    @router.post("/namespaces")
    async def cluster_namespaces(request: RefreshRequest):
        """获取命名空间详细信息"""
        force_refresh = request.force_refresh
        try:
            namespaces = (
                await instant_mode_instance.cluster_monitor.get_namespaces_detail(
                    force_refresh=force_refresh
                )
            )
            return {
                "code": 200,
                "data": {
                    "count": len(namespaces),
                    "namespaces": [
                        instant_mode_instance.cluster_monitor.to_dict(ns)
                        for ns in namespaces
                    ],
                },
            }
        except Exception as e:
            instant_mode_instance.logger.error("获取命名空间详细信息失败: %s", e)
            return {"code": 500, "message": f"获取命名空间信息失败: {str(e)}"}

    @router.post("/nodes")
    async def cluster_nodes(request: RefreshRequest):
        """获取节点详细信息"""
        force_refresh = request.force_refresh
        try:
            nodes = await instant_mode_instance.cluster_monitor.get_nodes_detail(
                force_refresh=force_refresh
            )
            return {
                "code": 200,
                "data": {
                    "count": len(nodes),
                    "nodes": [
                        instant_mode_instance.cluster_monitor.to_dict(node)
                        for node in nodes
                    ],
                },
            }
        except Exception as e:
            instant_mode_instance.logger.error("获取节点详细信息失败: %s", e)
            return {"code": 500, "message": f"获取节点信息失败: {str(e)}"}

    return router
