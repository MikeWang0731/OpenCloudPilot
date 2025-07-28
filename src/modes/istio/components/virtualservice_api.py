"""
VirtualService API Module

This module handles Istio VirtualService resource management operations with comprehensive
routing rule analysis, configuration validation, and health assessment.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from kubernetes import client

from src.modes.istio.utils.istio_parser import IstioParser
from src.modes.istio.utils.health_analyzer import HealthAnalyzer, HealthScore
from src.modes.istio.utils.cache_utils import (
    istio_cache_response,
    extract_istio_cache_params,
)

logger = logging.getLogger(__name__)


class VirtualServiceAPI:
    """
    API for managing Istio VirtualService resources.
    Provides comprehensive VirtualService resource management with routing rule analysis,
    configuration validation, and health assessment.
    """

    def __init__(self):
        """Initialize the VirtualServiceAPI"""
        self.health_analyzer = HealthAnalyzer()

    def get_virtualservice_details(
        self, request: "VirtualServiceRequest", dynamic_client=None, mode_instance=None
    ) -> "VirtualServiceDetailResponse":
        """
        Get VirtualService detailed information

        Args:
            request: VirtualService request parameters
            dynamic_client: Kubernetes dynamic client
            mode_instance: Mode instance (server or instant)

        Returns:
            VirtualService detailed information response
        """
        return get_virtualservice_details(request, dynamic_client, mode_instance)

    def get_virtualservice_list(
        self,
        request: "VirtualServiceListRequest",
        dynamic_client=None,
        mode_instance=None,
    ) -> "VirtualServiceListResponse":
        """
        Get VirtualService list

        Args:
            request: VirtualService list request parameters
            dynamic_client: Kubernetes dynamic client
            mode_instance: Mode instance (server or instant)

        Returns:
            VirtualService list response
        """
        return get_virtualservice_list(request, dynamic_client, mode_instance)

    def validate_config(
        self, config_data: Dict[str, Any]
    ) -> "VirtualServiceValidation":
        """
        Validate VirtualService configuration

        Args:
            config_data: Parsed VirtualService configuration

        Returns:
            Validation result
        """
        return validate_virtualservice_config(config_data)

    def analyze_health(self, config_data: Dict[str, Any]) -> HealthScore:
        """
        Analyze VirtualService health status

        Args:
            config_data: Parsed VirtualService configuration

        Returns:
            Health score
        """
        return analyze_virtualservice_health(config_data, self.health_analyzer)


class VirtualServiceRequest(BaseModel):
    """VirtualService请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    virtualservice_name: Optional[str] = Field(
        None, description="VirtualService名称，为空则查询所有VirtualService"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class VirtualServiceListRequest(BaseModel):
    """VirtualService列表请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class HTTPRoute(BaseModel):
    """HTTP路由规则模型"""

    match: List[Dict[str, Any]] = Field(default_factory=list, description="匹配条件")
    route: List[Dict[str, Any]] = Field(default_factory=list, description="路由目标")
    redirect: Optional[Dict[str, Any]] = Field(None, description="重定向配置")
    rewrite: Optional[Dict[str, Any]] = Field(None, description="重写配置")
    timeout: Optional[str] = Field(None, description="超时配置")
    retries: Optional[Dict[str, Any]] = Field(None, description="重试配置")
    fault: Optional[Dict[str, Any]] = Field(None, description="故障注入")
    mirror: Optional[Dict[str, Any]] = Field(None, description="流量镜像")


class TCPRoute(BaseModel):
    """TCP路由规则模型"""

    match: List[Dict[str, Any]] = Field(default_factory=list, description="匹配条件")
    route: List[Dict[str, Any]] = Field(default_factory=list, description="路由目标")


class TLSRoute(BaseModel):
    """TLS路由规则模型"""

    match: List[Dict[str, Any]] = Field(default_factory=list, description="匹配条件")
    route: List[Dict[str, Any]] = Field(default_factory=list, description="路由目标")


class VirtualServiceValidation(BaseModel):
    """VirtualService配置验证结果"""

    is_valid: bool = Field(..., description="配置是否有效")
    issues: List[str] = Field(default_factory=list, description="配置问题")
    warnings: List[str] = Field(default_factory=list, description="配置警告")
    recommendations: List[str] = Field(default_factory=list, description="改进建议")


class VirtualServiceHealth(BaseModel):
    """VirtualService健康状态"""

    overall_score: float = Field(..., description="总体健康分数 (0-100)")
    status: str = Field(..., description="健康状态")
    component_scores: Dict[str, float] = Field(
        default_factory=dict, description="组件分数"
    )
    issues: List[str] = Field(default_factory=list, description="健康问题")
    recommendations: List[str] = Field(default_factory=list, description="改进建议")
    last_updated: datetime = Field(..., description="最后更新时间")


class VirtualServiceDetail(BaseModel):
    """VirtualService详细信息模型"""

    name: str = Field(..., description="VirtualService名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="VirtualService UID")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")

    # VirtualService specific fields
    hosts: List[str] = Field(default_factory=list, description="主机列表")
    gateways: List[str] = Field(default_factory=list, description="网关列表")
    http_routes: List[HTTPRoute] = Field(
        default_factory=list, description="HTTP路由规则"
    )
    tcp_routes: List[TCPRoute] = Field(default_factory=list, description="TCP路由规则")
    tls_routes: List[TLSRoute] = Field(default_factory=list, description="TLS路由规则")

    # Analysis results
    validation: VirtualServiceValidation = Field(..., description="配置验证结果")
    health: VirtualServiceHealth = Field(..., description="健康状态")

    # Status information
    status: Dict[str, Any] = Field(default_factory=dict, description="状态信息")


class VirtualServiceListItem(BaseModel):
    """VirtualService列表项模型"""

    name: str = Field(..., description="VirtualService名称")
    namespace: str = Field(..., description="命名空间")
    age: str = Field(..., description="年龄")
    hosts_count: int = Field(..., description="主机数量")
    gateways_count: int = Field(..., description="网关数量")
    routes_count: int = Field(..., description="路由规则数量")
    health_status: str = Field(..., description="健康状态")
    health_score: float = Field(..., description="健康分数")


class VirtualServiceListResponse(BaseModel):
    """VirtualService列表响应模型"""

    success: bool = Field(..., description="请求是否成功")
    data: List[VirtualServiceListItem] = Field(
        default_factory=list, description="VirtualService列表"
    )
    total: int = Field(..., description="总数")
    message: str = Field(..., description="响应消息")


class VirtualServiceDetailResponse(BaseModel):
    """VirtualService详情响应模型"""

    success: bool = Field(..., description="请求是否成功")
    data: Optional[VirtualServiceDetail] = Field(None, description="VirtualService详情")
    message: str = Field(..., description="响应消息")


@istio_cache_response(
    "virtualservice", "detail", cache_params_func=extract_istio_cache_params
)
async def get_virtualservice_details(
    request: VirtualServiceRequest, dynamic_client=None, mode_instance=None
) -> VirtualServiceDetailResponse:
    """
    获取VirtualService详细信息

    Args:
        request: VirtualService请求参数

    Returns:
        VirtualService详细信息响应
    """
    try:
        cluster_name = request.cluster_name or "default"
        start_time = datetime.now()

        logger.info(
            "[VirtualService详情][%s]开始获取VirtualService详情 - 请求参数: virtualservice_name=%s, namespace=%s, force_refresh=%s",
            cluster_name,
            request.virtualservice_name,
            request.namespace,
            request.force_refresh,
        )

        # 获取动态客户端
        if dynamic_client is None:
            if mode_instance and hasattr(mode_instance, "cluster_clients"):
                # Server模式
                dynamic_client = mode_instance.cluster_clients.get(cluster_name)
            elif mode_instance and hasattr(mode_instance, "dynamic_client"):
                # Instant模式
                dynamic_client = mode_instance.dynamic_client
            else:
                return VirtualServiceDetailResponse(
                    success=False, message="无法获取Kubernetes客户端"
                )

        if not dynamic_client:
            return VirtualServiceDetailResponse(
                success=False, message=f"无法连接到集群: {cluster_name}"
            )

        # 获取自定义对象API
        custom_api = client.CustomObjectsApi(dynamic_client.client)

        # 查询VirtualService资源
        try:
            if request.virtualservice_name:
                # 查询特定VirtualService
                vs_resource = custom_api.get_namespaced_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    namespace=request.namespace or "default",
                    plural="virtualservices",
                    name=request.virtualservice_name,
                )
            else:
                return VirtualServiceDetailResponse(
                    success=False, message="VirtualService名称不能为空"
                )

        except client.exceptions.ApiException as e:
            if e.status == 404:
                return VirtualServiceDetailResponse(
                    success=False,
                    message=f"VirtualService '{request.virtualservice_name}' 不存在",
                )
            else:
                return VirtualServiceDetailResponse(
                    success=False, message=f"查询VirtualService失败: {e.reason}"
                )

        # 解析VirtualService配置
        parsed_config = IstioParser.parse_traffic_config(vs_resource)

        # 验证配置
        validation_result = validate_virtualservice_config(parsed_config)

        # 分析健康状态
        health_analyzer = HealthAnalyzer()
        health_score = analyze_virtualservice_health(parsed_config, health_analyzer)

        # 构建详细信息
        vs_detail = _build_virtualservice_detail(
            parsed_config, validation_result, health_score
        )

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            "[VirtualService详情][%s]成功获取VirtualService详情 - 响应摘要: virtualservice_name=%s, 主机数=%d, 网关数=%d, 路由规则数=%d, 健康分数=%.1f, 处理时间=%.2fs",
            cluster_name,
            request.virtualservice_name,
            len(vs_detail.hosts),
            len(vs_detail.gateways),
            len(vs_detail.http_routes)
            + len(vs_detail.tcp_routes)
            + len(vs_detail.tls_routes),
            vs_detail.health.overall_score,
            processing_time,
        )

        # 性能警告检查
        if processing_time > 2.0:
            logger.warning(
                "[VirtualService详情][%s]操作耗时较长 - 处理时间=%.2fs, 建议检查集群性能或网络连接",
                cluster_name,
                processing_time,
            )

        return VirtualServiceDetailResponse(
            success=True, data=vs_detail, message="获取VirtualService详情成功"
        )

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[VirtualService详情][%s]获取VirtualService详情失败 - 错误详情: virtualservice_name=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            request.virtualservice_name,
            type(e).__name__,
            str(e),
            processing_time,
        )
        return VirtualServiceDetailResponse(
            success=False, message=f"获取VirtualService详情失败: {str(e)}"
        )


@istio_cache_response(
    "virtualservice", "list", cache_params_func=extract_istio_cache_params
)
async def get_virtualservice_list(
    request: VirtualServiceListRequest, dynamic_client=None, mode_instance=None
) -> VirtualServiceListResponse:
    """
    获取VirtualService列表

    Args:
        request: VirtualService列表请求参数

    Returns:
        VirtualService列表响应
    """
    try:
        cluster_name = request.cluster_name or "default"
        start_time = datetime.now()

        logger.info(
            "[VirtualService列表][%s]开始获取VirtualService列表 - 请求参数: namespace=%s, force_refresh=%s",
            cluster_name,
            request.namespace,
            request.force_refresh,
        )

        # 获取动态客户端
        if dynamic_client is None:
            if mode_instance and hasattr(mode_instance, "cluster_clients"):
                # Server模式
                dynamic_client = mode_instance.cluster_clients.get(cluster_name)
            elif mode_instance and hasattr(mode_instance, "dynamic_client"):
                # Instant模式
                dynamic_client = mode_instance.dynamic_client
            else:
                return VirtualServiceListResponse(
                    success=False, data=[], total=0, message="无法获取Kubernetes客户端"
                )

        if not dynamic_client:
            return VirtualServiceListResponse(
                success=False,
                data=[],
                total=0,
                message=f"无法连接到集群: {cluster_name}",
            )

        # 获取自定义对象API
        custom_api = client.CustomObjectsApi(dynamic_client.client)

        # 查询VirtualService资源
        try:
            if request.namespace:
                # 查询特定命名空间
                vs_list = custom_api.list_namespaced_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    namespace=request.namespace,
                    plural="virtualservices",
                )
            else:
                # 查询所有命名空间
                vs_list = custom_api.list_cluster_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    plural="virtualservices",
                )

        except client.exceptions.ApiException as e:
            return VirtualServiceListResponse(
                success=False,
                data=[],
                total=0,
                message=f"查询VirtualService列表失败: {e.reason}",
            )

        # 处理VirtualService列表
        vs_items = []
        health_analyzer = HealthAnalyzer()

        for vs_resource in vs_list.get("items", []):
            try:
                # 解析VirtualService配置
                parsed_config = IstioParser.parse_traffic_config(vs_resource)

                # 分析健康状态
                health_score = analyze_virtualservice_health(
                    parsed_config, health_analyzer
                )

                # 构建列表项
                vs_item = _build_virtualservice_list_item(parsed_config, health_score)
                vs_items.append(vs_item)

            except Exception as e:
                logger.warning(
                    "[VirtualService列表][%s]处理VirtualService失败 - 资源名称=%s, 错误类型=%s, 错误信息=%s",
                    cluster_name,
                    vs_resource.get("metadata", {}).get("name", "unknown"),
                    type(e).__name__,
                    str(e),
                )
                continue

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        healthy_count = sum(1 for item in vs_items if item.health_status == "healthy")
        avg_health_score = (
            sum(item.health_score for item in vs_items) / len(vs_items)
            if vs_items
            else 0
        )
        total_routes = sum(item.routes_count for item in vs_items)

        logger.info(
            "[VirtualService列表][%s]成功获取VirtualService列表 - 响应摘要: 总数=%d, 健康数=%d, 平均健康分数=%.1f, 总路由规则数=%d, 处理时间=%.2fs",
            cluster_name,
            len(vs_items),
            healthy_count,
            avg_health_score,
            total_routes,
            processing_time,
        )

        # 性能警告检查
        if processing_time > 3.0:
            logger.warning(
                "[VirtualService列表][%s]列表查询耗时较长 - 处理时间=%.2fs, 建议优化查询条件或检查集群性能",
                cluster_name,
                processing_time,
            )

        return VirtualServiceListResponse(
            success=True,
            data=vs_items,
            total=len(vs_items),
            message=f"获取VirtualService列表成功，共 {len(vs_items)} 个",
        )

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[VirtualService列表][%s]获取VirtualService列表失败 - 错误详情: namespace=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            request.namespace,
            type(e).__name__,
            str(e),
            processing_time,
        )
        return VirtualServiceListResponse(
            success=False,
            data=[],
            total=0,
            message=f"获取VirtualService列表失败: {str(e)}",
        )


def validate_virtualservice_config(
    config_data: Dict[str, Any]
) -> VirtualServiceValidation:
    """
    验证VirtualService配置

    Args:
        config_data: 解析后的VirtualService配置

    Returns:
        验证结果
    """
    try:
        validation_result = IstioParser.validate_istio_config(config_data)

        return VirtualServiceValidation(
            is_valid=validation_result["is_valid"],
            issues=validation_result["issues"],
            warnings=validation_result["warnings"],
            recommendations=validation_result["recommendations"],
        )

    except Exception as e:
        logger.error(
            "[VirtualService配置验证][未知集群]配置验证失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        return VirtualServiceValidation(
            is_valid=False,
            issues=[f"配置验证失败: {str(e)}"],
            warnings=[],
            recommendations=["检查VirtualService配置格式和内容"],
        )


def analyze_virtualservice_health(
    config_data: Dict[str, Any], health_analyzer: HealthAnalyzer
) -> HealthScore:
    """
    分析VirtualService健康状态

    Args:
        config_data: 解析后的VirtualService配置
        health_analyzer: 健康分析器实例

    Returns:
        健康分数
    """
    try:
        return health_analyzer.analyze_traffic_config_health(config_data)

    except Exception as e:
        logger.error(
            "[VirtualService健康分析][未知集群]健康分析失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        return HealthScore(
            overall_score=0.0,
            status="unknown",
            component_scores={},
            issues=[f"健康分析失败: {str(e)}"],
            recommendations=["检查VirtualService配置和状态"],
            last_updated=datetime.now(),
        )


def _build_virtualservice_detail(
    config_data: Dict[str, Any],
    validation: VirtualServiceValidation,
    health_score: HealthScore,
) -> VirtualServiceDetail:
    """构建VirtualService详细信息"""
    metadata = config_data["metadata"]
    spec = config_data["spec"]

    # 计算年龄
    creation_time = metadata.get("creation_timestamp")
    if creation_time:
        age = _calculate_age(creation_time)
    else:
        age = "Unknown"

    # 解析路由规则
    http_routes = []
    for route_config in spec.get("http", []):
        route = HTTPRoute(
            match=route_config.get("match", []),
            route=route_config.get("route", []),
            redirect=route_config.get("redirect"),
            rewrite=route_config.get("rewrite"),
            timeout=route_config.get("timeout"),
            retries=route_config.get("retries"),
            fault=route_config.get("fault"),
            mirror=route_config.get("mirror"),
        )
        http_routes.append(route)

    tcp_routes = []
    for route_config in spec.get("tcp", []):
        route = TCPRoute(
            match=route_config.get("match", []),
            route=route_config.get("route", []),
        )
        tcp_routes.append(route)

    tls_routes = []
    for route_config in spec.get("tls", []):
        route = TLSRoute(
            match=route_config.get("match", []),
            route=route_config.get("route", []),
        )
        tls_routes.append(route)

    # 构建健康状态
    health = VirtualServiceHealth(
        overall_score=health_score.overall_score,
        status=health_score.status.value,
        component_scores=health_score.component_scores,
        issues=health_score.issues,
        recommendations=health_score.recommendations,
        last_updated=health_score.last_updated,
    )

    return VirtualServiceDetail(
        name=metadata["name"],
        namespace=metadata["namespace"],
        uid=metadata.get("uid", ""),
        creation_timestamp=str(metadata.get("creation_timestamp", "")),
        age=age,
        labels=metadata.get("labels", {}),
        annotations=metadata.get("annotations", {}),
        hosts=spec.get("hosts", []),
        gateways=spec.get("gateways", []),
        http_routes=http_routes,
        tcp_routes=tcp_routes,
        tls_routes=tls_routes,
        validation=validation,
        health=health,
        status=config_data.get("status", {}),
    )


def _build_virtualservice_list_item(
    config_data: Dict[str, Any], health_score: HealthScore
) -> VirtualServiceListItem:
    """构建VirtualService列表项"""
    metadata = config_data["metadata"]
    spec = config_data["spec"]

    # 计算年龄
    creation_time = metadata.get("creation_timestamp")
    if creation_time:
        age = _calculate_age(creation_time)
    else:
        age = "Unknown"

    # 统计路由规则数量
    routes_count = (
        len(spec.get("http", [])) + len(spec.get("tcp", [])) + len(spec.get("tls", []))
    )

    return VirtualServiceListItem(
        name=metadata["name"],
        namespace=metadata["namespace"],
        age=age,
        hosts_count=len(spec.get("hosts", [])),
        gateways_count=len(spec.get("gateways", [])),
        routes_count=routes_count,
        health_status=health_score.status.value,
        health_score=health_score.overall_score,
    )


def _calculate_age(creation_timestamp: datetime) -> str:
    """计算资源年龄"""
    try:
        if isinstance(creation_timestamp, str):
            creation_time = datetime.fromisoformat(
                creation_timestamp.replace("Z", "+00:00")
            )
        else:
            creation_time = creation_timestamp

        now = datetime.now(timezone.utc)
        age_delta = now - creation_time

        days = age_delta.days
        hours, remainder = divmod(age_delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        if days > 0:
            return f"{days}d"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{minutes}m"

    except Exception:
        return "Unknown"


def create_virtualservice_router_for_server(server_mode_instance) -> APIRouter:
    """
    为Server模式创建VirtualService API路由

    Args:
        server_mode_instance: Server模式实例

    Returns:
        配置好的APIRouter
    """
    router = APIRouter(
        prefix="/istio/components/virtualservice",
        tags=["Istio VirtualService Components - Server"],
    )

    @router.post("/list", response_model=VirtualServiceListResponse)
    async def list_virtualservices(request: VirtualServiceListRequest):
        """获取VirtualService列表"""
        # 获取动态客户端
        dynamic_client = server_mode_instance.cluster_clients.get(request.cluster_name)

        # 如果客户端不存在，尝试创建
        if not dynamic_client:
            try:
                dynamic_client = await server_mode_instance._create_k8s_client(
                    request.cluster_name
                )
                if dynamic_client:
                    server_mode_instance.cluster_clients[request.cluster_name] = (
                        dynamic_client
                    )
            except Exception as e:
                return VirtualServiceListResponse(
                    success=False,
                    data=[],
                    total=0,
                    message=f"创建集群客户端失败: {str(e)}",
                )
        return await get_virtualservice_list(
            request, mode_instance=server_mode_instance
        )

    @router.post("/detail", response_model=VirtualServiceDetailResponse)
    async def get_virtualservice_detail(request: VirtualServiceRequest):
        """获取VirtualService详情"""
        # 获取动态客户端
        dynamic_client = server_mode_instance.cluster_clients.get(request.cluster_name)

        # 如果客户端不存在，尝试创建
        if not dynamic_client:
            try:
                dynamic_client = await server_mode_instance._create_k8s_client(
                    request.cluster_name
                )
                if dynamic_client:
                    server_mode_instance.cluster_clients[request.cluster_name] = (
                        dynamic_client
                    )
            except Exception as e:
                return VirtualServiceListResponse(
                    success=False,
                    data=[],
                    total=0,
                    message=f"创建集群客户端失败: {str(e)}",
                )
        return await get_virtualservice_details(
            request, mode_instance=server_mode_instance
        )

    return router


def create_virtualservice_router_for_instant(instant_mode_instance) -> APIRouter:
    """
    为Instant模式创建VirtualService API路由

    Args:
        instant_mode_instance: Instant模式实例

    Returns:
        配置好的APIRouter
    """
    router = APIRouter(
        prefix="/istio/components/virtualservice",
        tags=["Istio VirtualService Components - Instant"],
    )

    @router.post("/list", response_model=VirtualServiceListResponse)
    async def list_virtualservices(request: VirtualServiceListRequest):
        """获取VirtualService列表"""
        # Instant模式不需要cluster_name
        request.cluster_name = None
        return await get_virtualservice_list(
            request, mode_instance=instant_mode_instance
        )

    @router.post("/detail", response_model=VirtualServiceDetailResponse)
    async def get_virtualservice_detail(request: VirtualServiceRequest):
        """获取VirtualService详情"""
        # Instant模式不需要cluster_name
        request.cluster_name = None
        return await get_virtualservice_details(
            request, mode_instance=instant_mode_instance
        )

    return router
