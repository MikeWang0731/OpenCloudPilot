"""
DestinationRule API Module

This module handles Istio DestinationRule resource management operations with comprehensive
traffic policy analysis, configuration validation, and health assessment.
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


class DestinationRuleAPI:
    """
    API for managing Istio DestinationRule resources.
    Provides comprehensive DestinationRule resource management with traffic policy analysis,
    configuration validation, and health assessment.
    """

    def __init__(self):
        """Initialize the DestinationRuleAPI"""
        self.health_analyzer = HealthAnalyzer()

    def get_destinationrule_details(
        self, request: "DestinationRuleRequest", dynamic_client=None, mode_instance=None
    ) -> "DestinationRuleDetailResponse":
        """
        Get DestinationRule detailed information

        Args:
            request: DestinationRule request parameters
            dynamic_client: Kubernetes dynamic client
            mode_instance: Mode instance (server or instant)

        Returns:
            DestinationRule detailed information response
        """
        return get_destinationrule_details(request, dynamic_client, mode_instance)

    def get_destinationrule_list(
        self,
        request: "DestinationRuleListRequest",
        dynamic_client=None,
        mode_instance=None,
    ) -> "DestinationRuleListResponse":
        """
        Get DestinationRule list

        Args:
            request: DestinationRule list request parameters
            dynamic_client: Kubernetes dynamic client
            mode_instance: Mode instance (server or instant)

        Returns:
            DestinationRule list response
        """
        return get_destinationrule_list(request, dynamic_client, mode_instance)

    def validate_config(
        self, config_data: Dict[str, Any]
    ) -> "DestinationRuleValidation":
        """
        Validate DestinationRule configuration

        Args:
            config_data: Parsed DestinationRule configuration

        Returns:
            Validation result
        """
        return validate_destinationrule_config(config_data)

    def analyze_health(self, config_data: Dict[str, Any]) -> HealthScore:
        """
        Analyze DestinationRule health status

        Args:
            config_data: Parsed DestinationRule configuration

        Returns:
            Health score
        """
        return analyze_destinationrule_health(config_data, self.health_analyzer)


class DestinationRuleRequest(BaseModel):
    """DestinationRule请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    destinationrule_name: Optional[str] = Field(
        None, description="DestinationRule名称，为空则查询所有DestinationRule"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class DestinationRuleListRequest(BaseModel):
    """DestinationRule列表请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class TrafficPolicy(BaseModel):
    """流量策略模型"""

    load_balancer: Optional[Dict[str, Any]] = Field(None, description="负载均衡配置")
    connection_pool: Optional[Dict[str, Any]] = Field(None, description="连接池配置")
    outlier_detection: Optional[Dict[str, Any]] = Field(
        None, description="异常检测配置"
    )
    tls: Optional[Dict[str, Any]] = Field(None, description="TLS配置")
    port_level_settings: List[Dict[str, Any]] = Field(
        default_factory=list, description="端口级别设置"
    )


class Subset(BaseModel):
    """子集配置模型"""

    name: str = Field(..., description="子集名称")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签选择器")
    traffic_policy: Optional[TrafficPolicy] = Field(None, description="流量策略")


class DestinationRuleValidation(BaseModel):
    """DestinationRule配置验证结果"""

    is_valid: bool = Field(..., description="配置是否有效")
    issues: List[str] = Field(default_factory=list, description="配置问题")
    warnings: List[str] = Field(default_factory=list, description="配置警告")
    recommendations: List[str] = Field(default_factory=list, description="改进建议")


class DestinationRuleHealth(BaseModel):
    """DestinationRule健康状态"""

    overall_score: float = Field(..., description="总体健康分数 (0-100)")
    status: str = Field(..., description="健康状态")
    component_scores: Dict[str, float] = Field(
        default_factory=dict, description="组件分数"
    )
    issues: List[str] = Field(default_factory=list, description="健康问题")
    recommendations: List[str] = Field(default_factory=list, description="改进建议")
    last_updated: datetime = Field(..., description="最后更新时间")


class DestinationRuleDetail(BaseModel):
    """DestinationRule详细信息模型"""

    name: str = Field(..., description="DestinationRule名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="DestinationRule UID")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")

    # DestinationRule specific fields
    host: str = Field(..., description="目标主机")
    traffic_policy: Optional[TrafficPolicy] = Field(None, description="流量策略")
    subsets: List[Subset] = Field(default_factory=list, description="子集配置")
    export_to: List[str] = Field(default_factory=list, description="导出范围")

    # Analysis results
    validation: DestinationRuleValidation = Field(..., description="配置验证结果")
    health: DestinationRuleHealth = Field(..., description="健康状态")

    # Status information
    status: Dict[str, Any] = Field(default_factory=dict, description="状态信息")


class DestinationRuleListItem(BaseModel):
    """DestinationRule列表项模型"""

    name: str = Field(..., description="DestinationRule名称")
    namespace: str = Field(..., description="命名空间")
    age: str = Field(..., description="年龄")
    host: str = Field(..., description="目标主机")
    subsets_count: int = Field(..., description="子集数量")
    has_traffic_policy: bool = Field(..., description="是否有流量策略")
    health_status: str = Field(..., description="健康状态")
    health_score: float = Field(..., description="健康分数")


class DestinationRuleListResponse(BaseModel):
    """DestinationRule列表响应模型"""

    success: bool = Field(..., description="请求是否成功")
    data: List[DestinationRuleListItem] = Field(
        default_factory=list, description="DestinationRule列表"
    )
    total: int = Field(..., description="总数")
    message: str = Field(..., description="响应消息")


class DestinationRuleDetailResponse(BaseModel):
    """DestinationRule详情响应模型"""

    success: bool = Field(..., description="请求是否成功")
    data: Optional[DestinationRuleDetail] = Field(
        None, description="DestinationRule详情"
    )
    message: str = Field(..., description="响应消息")


@istio_cache_response(
    "destinationrule", "detail", cache_params_func=extract_istio_cache_params
)
async def get_destinationrule_details(
    request: DestinationRuleRequest, dynamic_client=None, mode_instance=None
) -> DestinationRuleDetailResponse:
    """
    获取DestinationRule详细信息

    Args:
        request: DestinationRule请求参数

    Returns:
        DestinationRule详细信息响应
    """
    try:
        cluster_name = request.cluster_name or "default"
        start_time = datetime.now()

        logger.info(
            "[DestinationRule详情][%s]开始获取DestinationRule详情 - 请求参数: destinationrule_name=%s, namespace=%s, force_refresh=%s",
            cluster_name,
            request.destinationrule_name,
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
                return DestinationRuleDetailResponse(
                    success=False, message="无法获取Kubernetes客户端"
                )

        if not dynamic_client:
            return DestinationRuleDetailResponse(
                success=False, message=f"无法连接到集群: {cluster_name}"
            )

        # 获取自定义对象API
        custom_api = client.CustomObjectsApi(dynamic_client.client)

        # 查询DestinationRule资源
        try:
            if request.destinationrule_name:
                # 查询特定DestinationRule
                dr_resource = custom_api.get_namespaced_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    namespace=request.namespace or "default",
                    plural="destinationrules",
                    name=request.destinationrule_name,
                )
            else:
                return DestinationRuleDetailResponse(
                    success=False, message="DestinationRule名称不能为空"
                )

        except client.exceptions.ApiException as e:
            if e.status == 404:
                return DestinationRuleDetailResponse(
                    success=False,
                    message=f"DestinationRule '{request.destinationrule_name}' 不存在",
                )
            else:
                return DestinationRuleDetailResponse(
                    success=False, message=f"查询DestinationRule失败: {e.reason}"
                )

        # 解析DestinationRule配置
        parsed_config = IstioParser.parse_traffic_config(dr_resource)

        # 验证配置
        validation_result = validate_destinationrule_config(parsed_config)

        # 分析健康状态
        health_analyzer = HealthAnalyzer()
        health_score = analyze_destinationrule_health(parsed_config, health_analyzer)

        # 构建详细信息
        dr_detail = _build_destinationrule_detail(
            parsed_config, validation_result, health_score
        )

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            "[DestinationRule详情][%s]成功获取DestinationRule详情 - 响应摘要: destinationrule_name=%s, 主机=%s, 子集数=%d, 健康分数=%.1f, 处理时间=%.2fs",
            cluster_name,
            request.destinationrule_name,
            dr_detail.host,
            len(dr_detail.subsets),
            dr_detail.health.overall_score,
            processing_time,
        )

        # 性能警告检查
        if processing_time > 2.0:
            logger.warning(
                "[DestinationRule详情][%s]操作耗时较长 - 处理时间=%.2fs, 建议检查集群性能或网络连接",
                cluster_name,
                processing_time,
            )

        return DestinationRuleDetailResponse(
            success=True, data=dr_detail, message="获取DestinationRule详情成功"
        )

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[DestinationRule详情][%s]获取DestinationRule详情失败 - 错误详情: destinationrule_name=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            request.destinationrule_name,
            type(e).__name__,
            str(e),
            processing_time,
        )
        return DestinationRuleDetailResponse(
            success=False, message=f"获取DestinationRule详情失败: {str(e)}"
        )


@istio_cache_response(
    "destinationrule", "list", cache_params_func=extract_istio_cache_params
)
async def get_destinationrule_list(
    request: DestinationRuleListRequest, dynamic_client=None, mode_instance=None
) -> DestinationRuleListResponse:
    """
    获取DestinationRule列表

    Args:
        request: DestinationRule列表请求参数

    Returns:
        DestinationRule列表响应
    """
    try:
        cluster_name = request.cluster_name or "default"
        start_time = datetime.now()

        logger.info(
            "[DestinationRule列表][%s]开始获取DestinationRule列表 - 请求参数: namespace=%s, force_refresh=%s",
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
                return DestinationRuleListResponse(
                    success=False, data=[], total=0, message="无法获取Kubernetes客户端"
                )

        if not dynamic_client:
            return DestinationRuleListResponse(
                success=False,
                data=[],
                total=0,
                message=f"无法连接到集群: {cluster_name}",
            )

        # 获取自定义对象API
        custom_api = client.CustomObjectsApi(dynamic_client.client)

        # 查询DestinationRule资源
        try:
            if request.namespace:
                # 查询特定命名空间
                dr_list = custom_api.list_namespaced_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    namespace=request.namespace,
                    plural="destinationrules",
                )
            else:
                # 查询所有命名空间
                dr_list = custom_api.list_cluster_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    plural="destinationrules",
                )

        except client.exceptions.ApiException as e:
            return DestinationRuleListResponse(
                success=False,
                data=[],
                total=0,
                message=f"查询DestinationRule列表失败: {e.reason}",
            )

        # 处理DestinationRule列表
        dr_items = []
        health_analyzer = HealthAnalyzer()

        for dr_resource in dr_list.get("items", []):
            try:
                # 解析DestinationRule配置
                parsed_config = IstioParser.parse_traffic_config(dr_resource)

                # 分析健康状态
                health_score = analyze_destinationrule_health(
                    parsed_config, health_analyzer
                )

                # 构建列表项
                dr_item = _build_destinationrule_list_item(parsed_config, health_score)
                dr_items.append(dr_item)

            except Exception as e:
                logger.warning(
                    "[DestinationRule列表][%s]处理DestinationRule失败 - 资源名称=%s, 错误类型=%s, 错误信息=%s",
                    cluster_name,
                    dr_resource.get("metadata", {}).get("name", "unknown"),
                    type(e).__name__,
                    str(e),
                )
                continue

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        healthy_count = sum(1 for item in dr_items if item.health_status == "healthy")
        avg_health_score = (
            sum(item.health_score for item in dr_items) / len(dr_items)
            if dr_items
            else 0
        )

        logger.info(
            "[DestinationRule列表][%s]成功获取DestinationRule列表 - 响应摘要: 总数=%d, 健康数=%d, 平均健康分数=%.1f, 处理时间=%.2fs",
            cluster_name,
            len(dr_items),
            healthy_count,
            avg_health_score,
            processing_time,
        )

        # 性能警告检查
        if processing_time > 3.0:
            logger.warning(
                "[DestinationRule列表][%s]列表查询耗时较长 - 处理时间=%.2fs, 建议优化查询条件或检查集群性能",
                cluster_name,
                processing_time,
            )

        return DestinationRuleListResponse(
            success=True,
            data=dr_items,
            total=len(dr_items),
            message=f"获取DestinationRule列表成功，共 {len(dr_items)} 个",
        )

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[DestinationRule列表][%s]获取DestinationRule列表失败 - 错误详情: namespace=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            request.namespace,
            type(e).__name__,
            str(e),
            processing_time,
        )
        return DestinationRuleListResponse(
            success=False,
            data=[],
            total=0,
            message=f"获取DestinationRule列表失败: {str(e)}",
        )


def validate_destinationrule_config(
    config_data: Dict[str, Any]
) -> DestinationRuleValidation:
    """
    验证DestinationRule配置

    Args:
        config_data: 解析后的DestinationRule配置

    Returns:
        验证结果
    """
    try:
        validation_result = IstioParser.validate_istio_config(config_data)

        return DestinationRuleValidation(
            is_valid=validation_result["is_valid"],
            issues=validation_result["issues"],
            warnings=validation_result["warnings"],
            recommendations=validation_result["recommendations"],
        )

    except Exception as e:
        logger.error(
            "[DestinationRule配置验证][未知集群]配置验证失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        return DestinationRuleValidation(
            is_valid=False,
            issues=[f"配置验证失败: {str(e)}"],
            warnings=[],
            recommendations=["检查DestinationRule配置格式和内容"],
        )


def analyze_destinationrule_health(
    config_data: Dict[str, Any], health_analyzer: HealthAnalyzer
) -> HealthScore:
    """
    分析DestinationRule健康状态

    Args:
        config_data: 解析后的DestinationRule配置
        health_analyzer: 健康分析器实例

    Returns:
        健康分数
    """
    try:
        return health_analyzer.analyze_traffic_config_health(config_data)

    except Exception as e:
        logger.error(
            "[DestinationRule健康分析][未知集群]健康分析失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        return HealthScore(
            overall_score=0.0,
            status="unknown",
            component_scores={},
            issues=[f"健康分析失败: {str(e)}"],
            recommendations=["检查DestinationRule配置和状态"],
            last_updated=datetime.now(),
        )


def _build_destinationrule_detail(
    config_data: Dict[str, Any],
    validation: DestinationRuleValidation,
    health_score: HealthScore,
) -> DestinationRuleDetail:
    """构建DestinationRule详细信息"""
    metadata = config_data["metadata"]
    spec = config_data["spec"]

    # 计算年龄
    creation_time = metadata.get("creation_timestamp")
    if creation_time:
        age = _calculate_age(creation_time)
    else:
        age = "Unknown"

    # 解析流量策略
    traffic_policy = None
    if spec.get("trafficPolicy"):
        tp_config = spec["trafficPolicy"]
        traffic_policy = TrafficPolicy(
            load_balancer=tp_config.get("loadBalancer"),
            connection_pool=tp_config.get("connectionPool"),
            outlier_detection=tp_config.get("outlierDetection"),
            tls=tp_config.get("tls"),
            port_level_settings=tp_config.get("portLevelSettings", []),
        )

    # 解析子集配置
    subsets = []
    for subset_config in spec.get("subsets", []):
        subset_tp = None
        if subset_config.get("trafficPolicy"):
            tp_config = subset_config["trafficPolicy"]
            subset_tp = TrafficPolicy(
                load_balancer=tp_config.get("loadBalancer"),
                connection_pool=tp_config.get("connectionPool"),
                outlier_detection=tp_config.get("outlierDetection"),
                tls=tp_config.get("tls"),
                port_level_settings=tp_config.get("portLevelSettings", []),
            )

        subset = Subset(
            name=subset_config.get("name", ""),
            labels=subset_config.get("labels", {}),
            traffic_policy=subset_tp,
        )
        subsets.append(subset)

    # 构建健康状态
    health = DestinationRuleHealth(
        overall_score=health_score.overall_score,
        status=health_score.status.value,
        component_scores=health_score.component_scores,
        issues=health_score.issues,
        recommendations=health_score.recommendations,
        last_updated=health_score.last_updated,
    )

    return DestinationRuleDetail(
        name=metadata["name"],
        namespace=metadata["namespace"],
        uid=metadata.get("uid", ""),
        creation_timestamp=str(metadata.get("creation_timestamp", "")),
        age=age,
        labels=metadata.get("labels", {}),
        annotations=metadata.get("annotations", {}),
        host=spec.get("host", ""),
        traffic_policy=traffic_policy,
        subsets=subsets,
        export_to=spec.get("exportTo", []),
        validation=validation,
        health=health,
        status=config_data.get("status", {}),
    )


def _build_destinationrule_list_item(
    config_data: Dict[str, Any], health_score: HealthScore
) -> DestinationRuleListItem:
    """构建DestinationRule列表项"""
    metadata = config_data["metadata"]
    spec = config_data["spec"]

    # 计算年龄
    creation_time = metadata.get("creation_timestamp")
    if creation_time:
        age = _calculate_age(creation_time)
    else:
        age = "Unknown"

    return DestinationRuleListItem(
        name=metadata["name"],
        namespace=metadata["namespace"],
        age=age,
        host=spec.get("host", ""),
        subsets_count=len(spec.get("subsets", [])),
        has_traffic_policy=bool(spec.get("trafficPolicy")),
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


def create_destinationrule_router_for_server(server_mode_instance) -> APIRouter:
    """
    为Server模式创建DestinationRule API路由

    Args:
        server_mode_instance: Server模式实例

    Returns:
        配置好的APIRouter
    """
    router = APIRouter(
        prefix="/istio/components/destinationrule",
        tags=["Istio DestinationRule Components - Server"],
    )

    @router.post("/list", response_model=DestinationRuleListResponse)
    async def list_destinationrules(request: DestinationRuleListRequest):
        """获取DestinationRule列表"""
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
                return DestinationRuleListResponse(
                    success=False,
                    data=[],
                    total=0,
                    message=f"创建集群客户端失败: {str(e)}",
                )
        return await get_destinationrule_list(
            request, mode_instance=server_mode_instance
        )

    @router.post("/detail", response_model=DestinationRuleDetailResponse)
    async def get_destinationrule_detail(request: DestinationRuleRequest):
        """获取DestinationRule详情"""
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
                return DestinationRuleListResponse(
                    success=False,
                    data=[],
                    total=0,
                    message=f"创建集群客户端失败: {str(e)}",
                )
        return await get_destinationrule_details(
            request, mode_instance=server_mode_instance
        )

    return router


def create_destinationrule_router_for_instant(instant_mode_instance) -> APIRouter:
    """
    为Instant模式创建DestinationRule API路由

    Args:
        instant_mode_instance: Instant模式实例

    Returns:
        配置好的APIRouter
    """
    router = APIRouter(
        prefix="/istio/components/destinationrule",
        tags=["Istio DestinationRule Components - Instant"],
    )

    @router.post("/list", response_model=DestinationRuleListResponse)
    async def list_destinationrules(request: DestinationRuleListRequest):
        """获取DestinationRule列表"""
        # Instant模式不需要cluster_name
        request.cluster_name = None
        return await get_destinationrule_list(
            request, mode_instance=instant_mode_instance
        )

    @router.post("/detail", response_model=DestinationRuleDetailResponse)
    async def get_destinationrule_detail(request: DestinationRuleRequest):
        """获取DestinationRule详情"""
        # Instant模式不需要cluster_name
        request.cluster_name = None
        return await get_destinationrule_details(
            request, mode_instance=instant_mode_instance
        )

    return router
