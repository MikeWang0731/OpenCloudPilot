"""
Gateway API Module

This module handles Istio Gateway resource management operations with comprehensive
configuration analysis, validation, and health assessment.
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


class GatewayAPI:
    """
    API for managing Istio Gateway resources.
    Provides comprehensive Gateway resource management with configuration analysis,
    validation, and health assessment.
    """

    def __init__(self):
        """Initialize the GatewayAPI"""
        self.health_analyzer = HealthAnalyzer()

    def get_gateway_details(
        self, request: "GatewayRequest", dynamic_client=None, mode_instance=None
    ) -> "GatewayDetailResponse":
        """
        Get Gateway detailed information

        Args:
            request: Gateway request parameters
            dynamic_client: Kubernetes dynamic client
            mode_instance: Mode instance (server or instant)

        Returns:
            Gateway detailed information response
        """
        return get_gateway_details(request, dynamic_client, mode_instance)

    def get_gateway_list(
        self, request: "GatewayListRequest", dynamic_client=None, mode_instance=None
    ) -> "GatewayListResponse":
        """
        Get Gateway list

        Args:
            request: Gateway list request parameters
            dynamic_client: Kubernetes dynamic client
            mode_instance: Mode instance (server or instant)

        Returns:
            Gateway list response
        """
        return get_gateway_list(request, dynamic_client, mode_instance)

    def validate_config(self, config_data: Dict[str, Any]) -> "GatewayValidation":
        """
        Validate Gateway configuration

        Args:
            config_data: Parsed Gateway configuration

        Returns:
            Validation result
        """
        return validate_gateway_config(config_data)

    def analyze_health(self, config_data: Dict[str, Any]) -> HealthScore:
        """
        Analyze Gateway health status

        Args:
            config_data: Parsed Gateway configuration

        Returns:
            Health score
        """
        return analyze_gateway_health(config_data, self.health_analyzer)


class GatewayRequest(BaseModel):
    """Gateway请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    gateway_name: Optional[str] = Field(
        None, description="Gateway名称，为空则查询所有Gateway"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class GatewayListRequest(BaseModel):
    """Gateway列表请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class GatewayServer(BaseModel):
    """Gateway服务器配置模型"""

    port: Dict[str, Any] = Field(..., description="端口配置")
    hosts: List[str] = Field(..., description="主机列表")
    tls: Optional[Dict[str, Any]] = Field(None, description="TLS配置")
    default_endpoint: Optional[str] = Field(None, description="默认端点")


class GatewayValidation(BaseModel):
    """Gateway配置验证结果"""

    is_valid: bool = Field(..., description="配置是否有效")
    issues: List[str] = Field(default_factory=list, description="配置问题")
    warnings: List[str] = Field(default_factory=list, description="配置警告")
    recommendations: List[str] = Field(default_factory=list, description="改进建议")


class GatewayHealth(BaseModel):
    """Gateway健康状态"""

    overall_score: float = Field(..., description="总体健康分数 (0-100)")
    status: str = Field(..., description="健康状态")
    component_scores: Dict[str, float] = Field(
        default_factory=dict, description="组件分数"
    )
    issues: List[str] = Field(default_factory=list, description="健康问题")
    recommendations: List[str] = Field(default_factory=list, description="改进建议")
    last_updated: datetime = Field(..., description="最后更新时间")


class GatewayDetail(BaseModel):
    """Gateway详细信息模型"""

    name: str = Field(..., description="Gateway名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="Gateway UID")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")

    # Gateway specific fields
    servers: List[GatewayServer] = Field(default_factory=list, description="服务器配置")
    selector: Dict[str, str] = Field(default_factory=dict, description="选择器")

    # Analysis results
    validation: GatewayValidation = Field(..., description="配置验证结果")
    health: GatewayHealth = Field(..., description="健康状态")

    # Status information
    status: Dict[str, Any] = Field(default_factory=dict, description="状态信息")


class GatewayListItem(BaseModel):
    """Gateway列表项模型"""

    name: str = Field(..., description="Gateway名称")
    namespace: str = Field(..., description="命名空间")
    age: str = Field(..., description="年龄")
    servers_count: int = Field(..., description="服务器数量")
    hosts_count: int = Field(..., description="主机数量")
    health_status: str = Field(..., description="健康状态")
    health_score: float = Field(..., description="健康分数")


class GatewayListResponse(BaseModel):
    """Gateway列表响应模型"""

    success: bool = Field(..., description="请求是否成功")
    data: List[GatewayListItem] = Field(default_factory=list, description="Gateway列表")
    total: int = Field(..., description="总数")
    message: str = Field(..., description="响应消息")


class GatewayDetailResponse(BaseModel):
    """Gateway详情响应模型"""

    success: bool = Field(..., description="请求是否成功")
    data: Optional[GatewayDetail] = Field(None, description="Gateway详情")
    message: str = Field(..., description="响应消息")


@istio_cache_response("gateway", "detail", cache_params_func=extract_istio_cache_params)
async def get_gateway_details(
    request: GatewayRequest, dynamic_client=None, mode_instance=None
) -> GatewayDetailResponse:
    """
    获取Gateway详细信息

    Args:
        request: Gateway请求参数

    Returns:
        Gateway详细信息响应
    """
    cluster_name = request.cluster_name or "default"
    start_time = datetime.now()

    try:
        logger.info(
            "[Gateway详情][%s]开始获取Gateway详情 - 请求参数: gateway_name=%s, namespace=%s, force_refresh=%s",
            cluster_name,
            request.gateway_name,
            request.namespace,
            request.force_refresh,
        )

        # 获取动态客户端
        if dynamic_client is None:
            if mode_instance and hasattr(mode_instance, "cluster_clients"):
                # Server模式
                dynamic_client = mode_instance.cluster_clients.get(cluster_name)

                # 如果客户端不存在，尝试创建
                if not dynamic_client:
                    try:
                        dynamic_client = await mode_instance._create_k8s_client(
                            cluster_name
                        )
                        if dynamic_client:
                            mode_instance.cluster_clients[cluster_name] = dynamic_client
                        else:
                            return GatewayDetailResponse(
                                success=False, message=f"无法连接到集群: {cluster_name}"
                            )
                    except Exception as e:
                        return GatewayDetailResponse(
                            success=False, message=f"创建集群客户端失败: {str(e)}"
                        )

            elif mode_instance and hasattr(mode_instance, "dynamic_client"):
                # Instant模式
                dynamic_client = mode_instance.dynamic_client
            else:
                return GatewayDetailResponse(
                    success=False, message="无法获取Kubernetes客户端"
                )

        # 获取自定义对象API
        custom_api = client.CustomObjectsApi(dynamic_client.client)

        # 查询Gateway资源
        try:
            if request.gateway_name:
                # 查询特定Gateway
                gateway_resource = custom_api.get_namespaced_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    namespace=request.namespace or "default",
                    plural="gateways",
                    name=request.gateway_name,
                )
            else:
                return GatewayDetailResponse(
                    success=False, message="Gateway名称不能为空"
                )

        except client.exceptions.ApiException as e:
            if e.status == 404:
                return GatewayDetailResponse(
                    success=False,
                    message=f"Gateway '{request.gateway_name}' 不存在",
                )
            else:
                return GatewayDetailResponse(
                    success=False, message=f"查询Gateway失败: {e.reason}"
                )

        # 解析Gateway配置
        parsed_config = IstioParser.parse_traffic_config(gateway_resource)

        # 验证配置
        validation_result = validate_gateway_config(parsed_config)

        # 分析健康状态
        health_analyzer = HealthAnalyzer()
        health_score = analyze_gateway_health(parsed_config, health_analyzer)

        # 构建详细信息
        gateway_detail = _build_gateway_detail(
            parsed_config, validation_result, health_score
        )

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            "[Gateway详情][%s]成功获取Gateway详情 - 响应摘要: gateway_name=%s, 服务器数=%d, 主机数=%d, 健康分数=%.1f, 处理时间=%.2fs",
            cluster_name,
            request.gateway_name,
            len(gateway_detail.servers),
            sum(len(server.hosts) for server in gateway_detail.servers),
            gateway_detail.health.overall_score,
            processing_time,
        )

        # 性能警告检查
        if processing_time > 2.0:
            logger.warning(
                "[Gateway详情][%s]操作耗时较长 - 处理时间=%.2fs, 建议检查集群性能或网络连接",
                cluster_name,
                processing_time,
            )

        return GatewayDetailResponse(
            success=True, data=gateway_detail, message="获取Gateway详情成功"
        )
    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[Gateway详情][%s]获取Gateway详情失败 - 错误详情: gateway_name=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            request.gateway_name,
            type(e).__name__,
            str(e),
            processing_time,
        )
        return GatewayDetailResponse(
            success=False, message=f"获取Gateway详情失败: {str(e)}"
        )


@istio_cache_response("gateway", "list", cache_params_func=extract_istio_cache_params)
async def get_gateway_list(
    request: GatewayListRequest, dynamic_client=None, mode_instance=None
) -> GatewayListResponse:
    """
    获取Gateway列表

    Args:
        request: Gateway列表请求参数

    Returns:
        Gateway列表响应
    """
    cluster_name = request.cluster_name or "default"
    start_time = datetime.now()

    try:
        logger.info(
            "[Gateway列表][%s]开始获取Gateway列表 - 请求参数: namespace=%s, force_refresh=%s",
            cluster_name,
            request.namespace,
            request.force_refresh,
        )

        # 获取动态客户端
        if dynamic_client is None:
            if mode_instance and hasattr(mode_instance, "cluster_clients"):
                # Server模式
                dynamic_client = mode_instance.cluster_clients.get(cluster_name)

                # 如果客户端不存在，尝试创建
                if not dynamic_client:
                    try:
                        dynamic_client = await mode_instance._create_k8s_client(
                            cluster_name
                        )
                        if dynamic_client:
                            mode_instance.cluster_clients[cluster_name] = dynamic_client
                        else:
                            return GatewayListResponse(
                                success=False,
                                data=[],
                                total=0,
                                message=f"无法连接到集群: {cluster_name}",
                            )
                    except Exception as e:
                        return GatewayListResponse(
                            success=False,
                            data=[],
                            total=0,
                            message=f"创建集群客户端失败: {str(e)}",
                        )

            elif mode_instance and hasattr(mode_instance, "dynamic_client"):
                # Instant模式
                dynamic_client = mode_instance.dynamic_client
            else:
                return GatewayListResponse(
                    success=False, data=[], total=0, message="无法获取Kubernetes客户端"
                )

        # 获取自定义对象API
        custom_api = client.CustomObjectsApi(dynamic_client.client)

        # 查询Gateway资源
        try:
            if request.namespace:
                # 查询特定命名空间
                gateway_list = custom_api.list_namespaced_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    namespace=request.namespace,
                    plural="gateways",
                )
            else:
                # 查询所有命名空间
                gateway_list = custom_api.list_cluster_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    plural="gateways",
                )

        except client.exceptions.ApiException as e:
            return GatewayListResponse(
                success=False,
                data=[],
                total=0,
                message=f"查询Gateway列表失败: {e.reason}",
            )

        # 处理Gateway列表
        gateway_items = []
        health_analyzer = HealthAnalyzer()

        for gateway_resource in gateway_list.get("items", []):
            try:
                # 解析Gateway配置
                parsed_config = IstioParser.parse_traffic_config(gateway_resource)

                # 分析健康状态
                health_score = analyze_gateway_health(parsed_config, health_analyzer)

                # 构建列表项
                gateway_item = _build_gateway_list_item(parsed_config, health_score)
                gateway_items.append(gateway_item)

            except Exception as e:
                logger.warning(
                    "[Gateway列表][%s]处理Gateway失败 - 资源名称=%s, 错误类型=%s, 错误信息=%s",
                    cluster_name,
                    gateway_resource.get("metadata", {}).get("name", "unknown"),
                    type(e).__name__,
                    str(e),
                )
                continue

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        healthy_count = sum(
            1 for item in gateway_items if item.health_status == "healthy"
        )
        avg_health_score = (
            sum(item.health_score for item in gateway_items) / len(gateway_items)
            if gateway_items
            else 0
        )

        logger.info(
            "[Gateway列表][%s]成功获取Gateway列表 - 响应摘要: 总数=%d, 健康数=%d, 平均健康分数=%.1f, 处理时间=%.2fs",
            cluster_name,
            len(gateway_items),
            healthy_count,
            avg_health_score,
            processing_time,
        )

        # 性能警告检查
        if processing_time > 3.0:
            logger.warning(
                "[Gateway列表][%s]列表查询耗时较长 - 处理时间=%.2fs, 建议优化查询条件或检查集群性能",
                cluster_name,
                processing_time,
            )

        return GatewayListResponse(
            success=True,
            data=gateway_items,
            total=len(gateway_items),
            message=f"获取Gateway列表成功，共 {len(gateway_items)} 个",
        )

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[Gateway列表][%s]获取Gateway列表失败 - 错误详情: namespace=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            request.namespace,
            type(e).__name__,
            str(e),
            processing_time,
        )
        return GatewayListResponse(
            success=False,
            data=[],
            total=0,
            message=f"获取Gateway列表失败: {str(e)}",
        )


def validate_gateway_config(config_data: Dict[str, Any]) -> GatewayValidation:
    """
    验证Gateway配置

    Args:
        config_data: 解析后的Gateway配置

    Returns:
        验证结果
    """
    try:
        validation_result = IstioParser.validate_istio_config(config_data)

        return GatewayValidation(
            is_valid=validation_result["is_valid"],
            issues=validation_result["issues"],
            warnings=validation_result["warnings"],
            recommendations=validation_result["recommendations"],
        )

    except Exception as e:
        logger.error(
            "[Gateway配置验证][未知集群]配置验证失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        return GatewayValidation(
            is_valid=False,
            issues=[f"配置验证失败: {str(e)}"],
            warnings=[],
            recommendations=["检查Gateway配置格式和内容"],
        )


def analyze_gateway_health(
    config_data: Dict[str, Any], health_analyzer: HealthAnalyzer
) -> HealthScore:
    """
    分析Gateway健康状态

    Args:
        config_data: 解析后的Gateway配置
        health_analyzer: 健康分析器实例

    Returns:
        健康分数
    """
    try:
        return health_analyzer.analyze_traffic_config_health(config_data)

    except Exception as e:
        logger.error(
            "[Gateway健康分析][未知集群]健康分析失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        return HealthScore(
            overall_score=0.0,
            status="unknown",
            component_scores={},
            issues=[f"健康分析失败: {str(e)}"],
            recommendations=["检查Gateway配置和状态"],
            last_updated=datetime.now(),
        )


def _build_gateway_detail(
    config_data: Dict[str, Any],
    validation: GatewayValidation,
    health_score: HealthScore,
) -> GatewayDetail:
    """构建Gateway详细信息"""
    metadata = config_data["metadata"]
    spec = config_data["spec"]

    # 计算年龄
    creation_time = metadata.get("creation_timestamp")
    if creation_time:
        age = _calculate_age(creation_time)
    else:
        age = "Unknown"

    # 解析服务器配置
    servers = []
    for server_config in spec.get("servers", []):
        server = GatewayServer(
            port=server_config.get("port", {}),
            hosts=server_config.get("hosts", []),
            tls=server_config.get("tls"),
            default_endpoint=server_config.get("defaultEndpoint"),
        )
        servers.append(server)

    # 构建健康状态
    health = GatewayHealth(
        overall_score=health_score.overall_score,
        status=health_score.status.value,
        component_scores=health_score.component_scores,
        issues=health_score.issues,
        recommendations=health_score.recommendations,
        last_updated=health_score.last_updated,
    )

    return GatewayDetail(
        name=metadata["name"],
        namespace=metadata["namespace"],
        uid=metadata.get("uid", ""),
        creation_timestamp=str(metadata.get("creation_timestamp", "")),
        age=age,
        labels=metadata.get("labels", {}),
        annotations=metadata.get("annotations", {}),
        servers=servers,
        selector=spec.get("selector", {}),
        validation=validation,
        health=health,
        status=config_data.get("status", {}),
    )


def _build_gateway_list_item(
    config_data: Dict[str, Any], health_score: HealthScore
) -> GatewayListItem:
    """构建Gateway列表项"""
    metadata = config_data["metadata"]
    spec = config_data["spec"]

    # 计算年龄
    creation_time = metadata.get("creation_timestamp")
    if creation_time:
        age = _calculate_age(creation_time)
    else:
        age = "Unknown"

    # 统计服务器和主机数量
    servers = spec.get("servers", [])
    servers_count = len(servers)
    hosts_count = sum(len(server.get("hosts", [])) for server in servers)

    return GatewayListItem(
        name=metadata["name"],
        namespace=metadata["namespace"],
        age=age,
        servers_count=servers_count,
        hosts_count=hosts_count,
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


def create_gateway_router_for_server(server_mode_instance) -> APIRouter:
    """
    为Server模式创建Gateway API路由

    Args:
        server_mode_instance: Server模式实例

    Returns:
        配置好的APIRouter
    """
    router = APIRouter(
        prefix="/istio/components/gateway", tags=["Istio Gateway Components - Server"]
    )

    @router.post("/list", response_model=GatewayListResponse)
    async def list_gateways(request: GatewayListRequest):
        """获取Gateway列表"""
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
                return GatewayListResponse(
                    success=False,
                    data=[],
                    total=0,
                    message=f"创建集群客户端失败: {str(e)}",
                )

        return await get_gateway_list(
            request, dynamic_client=dynamic_client, mode_instance=server_mode_instance
        )

    @router.post("/detail", response_model=GatewayDetailResponse)
    async def get_gateway_detail(request: GatewayRequest):
        """获取Gateway详情"""
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
                return GatewayDetailResponse(
                    success=False, message=f"创建集群客户端失败: {str(e)}"
                )

        return await get_gateway_details(
            request, dynamic_client=dynamic_client, mode_instance=server_mode_instance
        )

    return router


def create_gateway_router_for_instant(instant_mode_instance) -> APIRouter:
    """
    为Instant模式创建Gateway API路由

    Args:
        instant_mode_instance: Instant模式实例

    Returns:
        配置好的APIRouter
    """
    router = APIRouter(
        prefix="/istio/components/gateway", tags=["Istio Gateway Components - Instant"]
    )

    @router.post("/list", response_model=GatewayListResponse)
    async def list_gateways(request: GatewayListRequest):
        """获取Gateway列表"""
        # Instant模式不需要cluster_name
        request.cluster_name = None
        return await get_gateway_list(request, mode_instance=instant_mode_instance)

    @router.post("/detail", response_model=GatewayDetailResponse)
    async def get_gateway_detail(request: GatewayRequest):
        """获取Gateway详情"""
        # Instant模式不需要cluster_name
        request.cluster_name = None
        return await get_gateway_details(request, mode_instance=instant_mode_instance)

    return router
