# -*- coding: utf-8 -*-
"""
Kubernetes集群概览相关API
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


class RefreshRequest(BaseModel):
    """刷新请求模型"""

    force_refresh: Optional[bool] = False


class ClusterRequest(BaseModel):
    """集群请求模型"""

    cluster_name: str
    force_refresh: Optional[bool] = False


def create_server_overview_router(server_mode_instance) -> APIRouter:
    """创建Server模式的概览API路由"""
    router = APIRouter(prefix="/k8s/overview", tags=["K8s Overview - Server"])

    @router.post("/cluster")
    async def cluster_overview(request: ClusterRequest):
        """获取指定集群的资源概览"""
        cluster_name = request.cluster_name
        force_refresh = request.force_refresh
        try:
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            overview = await monitor.get_resource_overview(
                cluster_name, force_refresh=force_refresh
            )
            result = monitor.to_dict(overview)
            result["cluster_name"] = cluster_name
            return {"code": 200, "data": result}
        except Exception as e:
            server_mode_instance.logger.error(
                "获取集群 %s 概览失败: %s", cluster_name, e
            )
            return {"code": 500, "message": f"获取集群概览失败: {str(e)}"}

    return router


def create_instant_overview_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的概览API路由"""
    router = APIRouter(prefix="/k8s/overview", tags=["K8s Overview - Instant"])

    @router.post("/cluster")
    async def cluster_overview(request: RefreshRequest):
        """获取集群资源概览"""
        force_refresh = request.force_refresh
        try:
            overview = (
                await instant_mode_instance.cluster_monitor.get_resource_overview(
                    force_refresh=force_refresh
                )
            )
            return {
                "code": 200,
                "data": instant_mode_instance.cluster_monitor.to_dict(overview),
            }
        except Exception as e:
            instant_mode_instance.logger.error("获取集群概览失败: %s", e)
            return {"code": 500, "message": f"获取集群概览失败: {str(e)}"}

    return router
