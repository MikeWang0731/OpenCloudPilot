# -*- coding: utf-8 -*-
"""
Istio Health Summary API

This module provides health summary endpoints for dashboard integration,
aggregating health information from multiple Istio resources.
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from kubernetes import client

from src.core.k8s_utils import K8sUtils
from src.modes.istio.utils.istio_parser import IstioParser
from src.modes.istio.utils.health_analyzer import HealthAnalyzer, HealthScore
from src.modes.istio.utils.cache_utils import (
    with_istio_cache,
    istio_cache_response,
    extract_istio_cache_params,
)

logger = logging.getLogger(__name__)


class HealthSummaryRequest(BaseModel):
    """Health summary request model"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    resource_types: Optional[List[str]] = Field(
        None, description="资源类型列表，为空则查询所有类型"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class ResourceHealthSummary(BaseModel):
    """Resource health summary model"""

    resource_type: str = Field(..., description="资源类型")
    resource_name: str = Field(..., description="资源名称")
    namespace: str = Field(..., description="命名空间")
    health_score: float = Field(..., description="健康分数")
    status: str = Field(..., description="健康状态")
    issues_count: int = Field(..., description="问题数量")
    recommendations_count: int = Field(..., description="建议数量")


class OverallHealthSummary(BaseModel):
    """Overall health summary model"""

    total_resources: int = Field(..., description="总资源数")
    average_score: float = Field(..., description="平均健康分数")
    status_distribution: Dict[str, int] = Field(
        default_factory=dict, description="状态分布"
    )
    common_issues: List[str] = Field(default_factory=list, description="常见问题")
    top_recommendations: List[str] = Field(default_factory=list, description="主要建议")


class HealthSummaryResponse(BaseModel):
    """Health summary response model"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="健康摘要数据")


async def get_istio_health_summary(
    dynamic_client,
    namespace: Optional[str] = None,
    resource_types: Optional[List[str]] = None,
    cluster_name: str = "current",
) -> Dict[str, Any]:
    """
    Get comprehensive Istio health summary

    Args:
        dynamic_client: Kubernetes dynamic client
        namespace: Target namespace (None for all namespaces)
        resource_types: Resource types to include (None for all types)
        cluster_name: Cluster name

    Returns:
        Comprehensive health summary
    """
    from datetime import datetime

    start_time = datetime.now()

    logger.info(
        "[Istio健康摘要][%s]开始获取健康摘要 - 请求参数: namespace=%s, resource_types=%s",
        cluster_name,
        namespace,
        resource_types,
    )

    try:
        health_analyzer = HealthAnalyzer()
        istio_parser = IstioParser()
        health_scores = []
        resource_summaries = []

        # Default resource types if not specified
        if not resource_types:
            resource_types = [
                "istiod",
                "gateway-workload",
                "gateway",
                "virtualservice",
                "destinationrule",
            ]

        # Get workload health (istiod, gateway-workload)
        if "istiod" in resource_types or "gateway-workload" in resource_types:
            workload_health = await _get_workload_health_summary(
                dynamic_client, namespace, resource_types, cluster_name
            )
            health_scores.extend(workload_health["scores"])
            resource_summaries.extend(workload_health["summaries"])

        # Get component health (gateway, virtualservice, destinationrule)
        component_types = [
            t
            for t in resource_types
            if t in ["gateway", "virtualservice", "destinationrule"]
        ]
        if component_types:
            component_health = await _get_component_health_summary(
                dynamic_client, namespace, component_types, cluster_name
            )
            health_scores.extend(component_health["scores"])
            resource_summaries.extend(component_health["summaries"])

        # Generate overall summary
        overall_summary = health_analyzer.get_health_summary(health_scores)

        result = {
            "overall": overall_summary,
            "resources": resource_summaries,
            "cluster_name": cluster_name,
            "namespace": namespace,
            "timestamp": logger.info.__globals__.get("datetime", __import__("datetime"))
            .datetime.now()
            .isoformat(),
        }

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            "[Istio健康摘要][%s]成功获取健康摘要 - 响应摘要: 总资源数=%d, 平均健康分数=%.1f, 处理时间=%.2fs",
            cluster_name,
            overall_summary["total_resources"],
            overall_summary["average_score"],
            processing_time,
        )

        # 性能警告检查
        if processing_time > 5.0:
            logger.warning(
                "[Istio健康摘要][%s]健康摘要查询耗时较长 - 处理时间=%.2fs, 建议优化查询条件或检查集群性能",
                cluster_name,
                processing_time,
            )

        return result

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[Istio健康摘要][%s]获取健康摘要失败 - 错误详情: namespace=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            namespace,
            type(e).__name__,
            str(e),
            processing_time,
        )
        raise


async def _get_workload_health_summary(
    dynamic_client,
    namespace: Optional[str],
    resource_types: List[str],
    cluster_name: str,
) -> Dict[str, Any]:
    """Get workload health summary"""
    health_scores = []
    resource_summaries = []

    try:
        apps_v1 = client.AppsV1Api(dynamic_client.client)
        istio_parser = IstioParser()
        health_analyzer = HealthAnalyzer()

        # Get istiod health
        if "istiod" in resource_types:
            try:
                deployment = apps_v1.read_namespaced_deployment(
                    name="istiod", namespace=namespace or "istio-system"
                )
                workload_data = istio_parser.parse_istio_workload(deployment.to_dict())
                health_score = health_analyzer.calculate_workload_health(workload_data)
                health_scores.append(health_score)

                resource_summaries.append(
                    ResourceHealthSummary(
                        resource_type="istiod",
                        resource_name="istiod",
                        namespace=deployment.metadata.namespace,
                        health_score=health_score.overall_score,
                        status=health_score.status.value,
                        issues_count=len(health_score.issues),
                        recommendations_count=len(health_score.recommendations),
                    )
                )
            except client.ApiException as e:
                if e.status != 404:
                    logger.warning(
                        "[Istio健康摘要][%s]获取istiod失败 - 错误类型=%s, 错误信息=%s",
                        cluster_name,
                        type(e).__name__,
                        str(e),
                    )

        # Get gateway workload health
        if "gateway-workload" in resource_types:
            try:
                deployment = apps_v1.read_namespaced_deployment(
                    name="istio-ingressgateway", namespace=namespace or "istio-system"
                )
                workload_data = istio_parser.parse_istio_workload(deployment.to_dict())
                health_score = health_analyzer.calculate_workload_health(workload_data)
                health_scores.append(health_score)

                resource_summaries.append(
                    ResourceHealthSummary(
                        resource_type="gateway-workload",
                        resource_name="istio-ingressgateway",
                        namespace=deployment.metadata.namespace,
                        health_score=health_score.overall_score,
                        status=health_score.status.value,
                        issues_count=len(health_score.issues),
                        recommendations_count=len(health_score.recommendations),
                    )
                )
            except client.ApiException as e:
                if e.status != 404:
                    logger.warning(
                        "[Istio健康摘要][%s]获取gateway workload失败 - 错误类型=%s, 错误信息=%s",
                        cluster_name,
                        type(e).__name__,
                        str(e),
                    )

    except Exception as e:
        logger.error(
            "[Istio健康摘要][%s]获取工作负载健康摘要失败 - 错误类型=%s, 错误信息=%s",
            cluster_name,
            type(e).__name__,
            str(e),
        )

    return {"scores": health_scores, "summaries": resource_summaries}


async def _get_component_health_summary(
    dynamic_client,
    namespace: Optional[str],
    resource_types: List[str],
    cluster_name: str,
) -> Dict[str, Any]:
    """Get component health summary"""
    health_scores = []
    resource_summaries = []

    try:
        istio_parser = IstioParser()
        health_analyzer = HealthAnalyzer()

        # Get Gateway health
        if "gateway" in resource_types:
            try:
                gateways = dynamic_client.resources.get(
                    api_version="networking.istio.io/v1beta1", kind="Gateway"
                )
                if namespace:
                    gateway_list = gateways.get(namespace=namespace)
                else:
                    gateway_list = gateways.get()

                for gateway in gateway_list.items:
                    component_data = istio_parser.parse_istio_component(
                        gateway.to_dict()
                    )
                    health_score = health_analyzer.analyze_component_health(
                        component_data
                    )
                    health_scores.append(health_score)

                    resource_summaries.append(
                        ResourceHealthSummary(
                            resource_type="gateway",
                            resource_name=gateway.metadata.name,
                            namespace=gateway.metadata.namespace,
                            health_score=health_score.overall_score,
                            status=health_score.status.value,
                            issues_count=len(health_score.issues),
                            recommendations_count=len(health_score.recommendations),
                        )
                    )
            except Exception as e:
                logger.warning(
                    "[Istio健康摘要][%s]获取Gateway健康信息失败 - 错误类型=%s, 错误信息=%s",
                    cluster_name,
                    type(e).__name__,
                    str(e),
                )

        # Get VirtualService health
        if "virtualservice" in resource_types:
            try:
                virtualservices = dynamic_client.resources.get(
                    api_version="networking.istio.io/v1beta1", kind="VirtualService"
                )
                if namespace:
                    vs_list = virtualservices.get(namespace=namespace)
                else:
                    vs_list = virtualservices.get()

                for vs in vs_list.items:
                    component_data = istio_parser.parse_istio_component(vs.to_dict())
                    health_score = health_analyzer.analyze_component_health(
                        component_data
                    )
                    health_scores.append(health_score)

                    resource_summaries.append(
                        ResourceHealthSummary(
                            resource_type="virtualservice",
                            resource_name=vs.metadata.name,
                            namespace=vs.metadata.namespace,
                            health_score=health_score.overall_score,
                            status=health_score.status.value,
                            issues_count=len(health_score.issues),
                            recommendations_count=len(health_score.recommendations),
                        )
                    )
            except Exception as e:
                logger.warning(
                    "[Istio健康摘要][%s]获取VirtualService健康信息失败 - 错误类型=%s, 错误信息=%s",
                    cluster_name,
                    type(e).__name__,
                    str(e),
                )

        # Get DestinationRule health
        if "destinationrule" in resource_types:
            try:
                destinationrules = dynamic_client.resources.get(
                    api_version="networking.istio.io/v1beta1", kind="DestinationRule"
                )
                if namespace:
                    dr_list = destinationrules.get(namespace=namespace)
                else:
                    dr_list = destinationrules.get()

                for dr in dr_list.items:
                    component_data = istio_parser.parse_istio_component(dr.to_dict())
                    health_score = health_analyzer.analyze_component_health(
                        component_data
                    )
                    health_scores.append(health_score)

                    resource_summaries.append(
                        ResourceHealthSummary(
                            resource_type="destinationrule",
                            resource_name=dr.metadata.name,
                            namespace=dr.metadata.namespace,
                            health_score=health_score.overall_score,
                            status=health_score.status.value,
                            issues_count=len(health_score.issues),
                            recommendations_count=len(health_score.recommendations),
                        )
                    )
            except Exception as e:
                logger.warning(
                    "[Istio健康摘要][%s]获取DestinationRule健康信息失败 - 错误类型=%s, 错误信息=%s",
                    cluster_name,
                    type(e).__name__,
                    str(e),
                )

    except Exception as e:
        logger.error(
            "[Istio健康摘要][%s]获取组件健康摘要失败 - 错误类型=%s, 错误信息=%s",
            cluster_name,
            type(e).__name__,
            str(e),
        )

    return {"scores": health_scores, "summaries": resource_summaries}


def create_server_health_summary_router(server_mode_instance) -> APIRouter:
    """Create Server mode health summary router"""
    router = APIRouter(prefix="/istio/health", tags=["Istio Health Summary - Server"])

    @router.post("/summary", response_model=HealthSummaryResponse)
    async def get_health_summary(request: HealthSummaryRequest):
        """Get Istio health summary for dashboard integration"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # Get cluster monitor
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            # Get dynamic client
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # Use cache wrapper
            async def fetch_health_summary():
                summary_data = await get_istio_health_summary(
                    dynamic_client,
                    request.namespace,
                    request.resource_types,
                    cluster_name,
                )
                return {"code": 200, "data": summary_data}

            return await with_istio_cache(
                cluster_name=cluster_name,
                resource_type="health",
                operation="summary",
                force_refresh=request.force_refresh,
                cache_params={
                    "namespace": request.namespace,
                    "resource_types": request.resource_types,
                },
                fetch_func=fetch_health_summary,
            )

        except Exception as e:
            server_mode_instance.logger.error(
                "[Istio健康摘要][%s]获取健康摘要失败: %s", cluster_name, str(e)
            )
            return {"code": 500, "message": f"获取健康摘要失败: {str(e)}"}

    return router


def create_instant_health_summary_router(instant_mode_instance) -> APIRouter:
    """Create Instant mode health summary router"""
    router = APIRouter(prefix="/istio/health", tags=["Istio Health Summary - Instant"])

    @router.post("/summary", response_model=HealthSummaryResponse)
    async def get_health_summary(request: HealthSummaryRequest):
        """Get Istio health summary for dashboard integration"""
        cluster_name = "current"

        try:
            # Use cache wrapper
            async def fetch_health_summary():
                summary_data = await get_istio_health_summary(
                    instant_mode_instance.dynamic_client,
                    request.namespace,
                    request.resource_types,
                    cluster_name,
                )
                return {"code": 200, "data": summary_data}

            return await with_istio_cache(
                cluster_name=cluster_name,
                resource_type="health",
                operation="summary",
                force_refresh=request.force_refresh,
                cache_params={
                    "namespace": request.namespace,
                    "resource_types": request.resource_types,
                },
                fetch_func=fetch_health_summary,
            )

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Istio健康摘要][当前集群]获取健康摘要失败: %s", str(e)
            )
            return {"code": 500, "message": f"获取健康摘要失败: {str(e)}"}

    return router
