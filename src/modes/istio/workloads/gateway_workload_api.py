# -*- coding: utf-8 -*-
"""
Gateway工作负载管理API
"""

import logging, re
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from kubernetes import client

from src.core.k8s_utils import K8sUtils
from src.core.resource_parser import ResourceParser
from src.core.error_handler import create_error_handler, with_timeout
from src.core.resource_cache import get_resource_cache
from src.core.async_utils import (
    get_batch_processor,
    get_resource_fetcher,
    async_timeout,
    monitor_performance,
    get_performance_monitor,
)
from src.modes.istio.utils.istio_parser import IstioParser
from src.modes.istio.utils.health_analyzer import HealthAnalyzer
from src.modes.istio.utils.cache_utils import (
    with_istio_cache,
    istio_cache_response,
    extract_istio_cache_params,
    handle_cache_failure,
)
from src.modes.istio.utils.async_optimizer import (
    optimize_concurrent_operation,
    optimize_memory_usage,
    monitor_istio_performance,
    get_concurrent_fetcher,
    get_memory_optimizer,
)


class GatewayWorkloadRequest(BaseModel):
    """Gateway工作负载请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        "istio-system", description="命名空间，默认istio-system"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class GatewayLogRequest(BaseModel):
    """Gateway日志请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        "istio-system", description="命名空间，默认istio-system"
    )
    container_name: Optional[str] = Field(
        "istio-proxy", description="容器名称，默认istio-proxy"
    )
    since_time: Optional[datetime] = Field(None, description="开始时间")
    until_time: Optional[datetime] = Field(None, description="结束时间")
    tail_lines: Optional[int] = Field(
        100, ge=1, le=10000, description="获取最后N行日志"
    )
    previous: Optional[bool] = Field(False, description="是否获取前一个容器实例的日志")
    timestamps: Optional[bool] = Field(True, description="是否包含时间戳")


class GatewayEventRequest(BaseModel):
    """Gateway事件请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        "istio-system", description="命名空间，默认istio-system"
    )
    since_time: Optional[datetime] = Field(None, description="开始时间")
    last_hours: Optional[int] = Field(24, ge=1, le=168, description="最近N小时")
    limit: Optional[int] = Field(100, ge=1, le=1000, description="返回事件数量限制")


class ServiceInfo(BaseModel):
    """服务信息模型"""

    name: str = Field(..., description="服务名称")
    namespace: str = Field(..., description="命名空间")
    type: str = Field(..., description="服务类型")
    cluster_ip: Optional[str] = Field(None, description="集群IP")
    external_ips: List[str] = Field(default_factory=list, description="外部IP列表")
    ports: List[Dict[str, Any]] = Field(default_factory=list, description="端口列表")
    load_balancer_ip: Optional[str] = Field(None, description="负载均衡器IP")


class PodInfo(BaseModel):
    """Pod信息模型"""

    name: str = Field(..., description="Pod名称")
    namespace: str = Field(..., description="命名空间")
    status: str = Field(..., description="Pod状态")
    node_name: Optional[str] = Field(None, description="节点名称")
    pod_ip: Optional[str] = Field(None, description="Pod IP")
    ready: bool = Field(..., description="是否就绪")
    restart_count: int = Field(0, description="重启次数")
    age: str = Field(..., description="年龄")


class TrafficMetrics(BaseModel):
    """流量指标模型"""

    connections_active: Optional[int] = Field(None, description="活跃连接数")
    requests_per_second: Optional[float] = Field(None, description="每秒请求数")
    response_time_avg: Optional[float] = Field(None, description="平均响应时间")
    error_rate: Optional[float] = Field(None, description="错误率")


class GatewayWorkloadHealth(BaseModel):
    """Gateway工作负载健康状态模型"""

    overall_score: float = Field(..., description="总体健康分数 (0-100)")
    status: str = Field(..., description="健康状态")
    component_scores: Dict[str, float] = Field(
        default_factory=dict, description="组件分数"
    )
    issues: List[str] = Field(default_factory=list, description="问题列表")
    recommendations: List[str] = Field(default_factory=list, description="建议列表")


class GatewayWorkloadDetail(BaseModel):
    """Gateway工作负载详细信息模型"""

    name: str = Field(..., description="Deployment名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="Deployment UID")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")
    service_info: ServiceInfo = Field(..., description="服务信息")
    pods: List[PodInfo] = Field(default_factory=list, description="Pod列表")
    health: GatewayWorkloadHealth = Field(..., description="健康状态")
    traffic_metrics: TrafficMetrics = Field(..., description="流量指标")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="配置信息")
    version: Optional[str] = Field(None, description="Istio版本")


class LogEntry(BaseModel):
    """日志条目模型"""

    timestamp: Optional[str] = Field(None, description="时间戳")
    container_name: str = Field(..., description="容器名称")
    message: str = Field(..., description="日志消息")
    level: Optional[str] = Field(None, description="日志级别")
    is_error: bool = Field(False, description="是否为错误日志")
    line_number: int = Field(..., description="行号")


class GatewayLogResponse(BaseModel):
    """Gateway日志响应模型"""

    pod_name: str = Field(..., description="Pod名称")
    namespace: str = Field(..., description="命名空间")
    container_name: str = Field(..., description="容器名称")
    total_lines: int = Field(..., description="总行数")
    entries: List[LogEntry] = Field(default_factory=list, description="日志条目列表")
    error_count: int = Field(0, description="错误日志数量")
    warning_count: int = Field(0, description="警告日志数量")


class EventDetail(BaseModel):
    """事件详情模型"""

    name: str = Field(..., description="事件名称")
    namespace: str = Field(..., description="命名空间")
    type: str = Field(..., description="事件类型")
    reason: str = Field(..., description="事件原因")
    message: str = Field(..., description="事件消息")
    first_timestamp: Optional[str] = Field(None, description="首次发生时间")
    last_timestamp: Optional[str] = Field(None, description="最后发生时间")
    count: int = Field(1, description="发生次数")
    involved_object: Dict[str, Any] = Field(
        default_factory=dict, description="相关对象"
    )


class GatewayEventResponse(BaseModel):
    """Gateway事件响应模型"""

    namespace: str = Field(..., description="命名空间")
    events: List[EventDetail] = Field(default_factory=list, description="事件列表")
    total_events: int = Field(0, description="总事件数")
    warning_events: int = Field(0, description="警告事件数")
    error_events: int = Field(0, description="错误事件数")


class GatewayWorkloadDetailResponse(BaseModel):
    """Gateway工作负载详情响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[GatewayWorkloadDetail] = Field(
        None, description="Gateway工作负载详情"
    )


class GatewayLogListResponse(BaseModel):
    """Gateway日志列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[GatewayLogResponse] = Field(None, description="日志数据")


class GatewayEventListResponse(BaseModel):
    """Gateway事件列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[GatewayEventResponse] = Field(None, description="事件数据")


# Gateway工作负载信息提取函数


@async_timeout(30)
@monitor_performance("get_gateway_workload_details", get_performance_monitor())
@istio_cache_response(
    "gateway_workload", "detail", cache_params_func=extract_istio_cache_params
)
async def get_gateway_workload_details(
    dynamic_client, namespace: str = "istio-system", cluster_name: str = "current"
) -> Optional[GatewayWorkloadDetail]:
    """
    获取Gateway工作负载详细信息

    Args:
        dynamic_client: Kubernetes动态客户端
        namespace: 命名空间
        cluster_name: 集群名称

    Returns:
        Optional[GatewayWorkloadDetail]: Gateway工作负载详细信息，如果不存在则返回None
    """
    logger = logging.getLogger("cloudpilot.gateway_workload_api")

    try:
        logger.info(
            "[Gateway工作负载详情][%s]开始获取Gateway工作负载信息: %s",
            cluster_name,
            namespace,
        )

        # 获取istio-ingressgateway deployment
        apps_v1 = client.AppsV1Api(dynamic_client.client)

        try:
            deployment = apps_v1.read_namespaced_deployment(
                name="istio-ingressgateway", namespace=namespace
            )
        except client.ApiException as e:
            if e.status == 404:
                logger.warning(
                    "[Gateway工作负载详情][%s]istio-ingressgateway deployment不存在: %s",
                    cluster_name,
                    namespace,
                )
                return None
            raise

        # 初始化工具类
        k8s_utils = K8sUtils(dynamic_client)
        istio_parser = IstioParser()
        health_analyzer = HealthAnalyzer()

        # 基本信息
        metadata = deployment.metadata
        spec = deployment.spec
        status = deployment.status

        # 获取服务信息
        v1 = client.CoreV1Api(dynamic_client.client)
        try:
            service = v1.read_namespaced_service(
                name="istio-ingressgateway", namespace=namespace
            )
            service_info = ServiceInfo(
                name=service.metadata.name,
                namespace=service.metadata.namespace,
                type=service.spec.type,
                cluster_ip=service.spec.cluster_ip,
                external_ips=service.spec.external_i_ps or [],
                ports=[
                    {
                        "name": port.name,
                        "port": port.port,
                        "target_port": port.target_port,
                        "protocol": port.protocol,
                        "node_port": getattr(port, "node_port", None),
                    }
                    for port in service.spec.ports or []
                ],
                load_balancer_ip=(
                    getattr(service.status.load_balancer.ingress[0], "ip", None)
                    if service.status.load_balancer
                    and service.status.load_balancer.ingress
                    else None
                ),
            )
        except client.ApiException:
            # 如果服务不存在，创建默认服务信息
            service_info = ServiceInfo(
                name="istio-ingressgateway",
                namespace=namespace,
                type="Unknown",
            )

        # 获取Pod信息
        pod_list = v1.list_namespaced_pod(
            namespace=namespace, label_selector="app=istio-ingressgateway"
        )

        pods = []
        for pod in pod_list.items:
            pod_info = PodInfo(
                name=pod.metadata.name,
                namespace=pod.metadata.namespace,
                status=pod.status.phase or "Unknown",
                node_name=pod.spec.node_name,
                pod_ip=pod.status.pod_ip,
                ready=all(cs.ready for cs in (pod.status.container_statuses or [])),
                restart_count=sum(
                    cs.restart_count for cs in (pod.status.container_statuses or [])
                ),
                age=k8s_utils.calculate_age(pod.metadata.creation_timestamp),
            )
            pods.append(pod_info)

        # 解析工作负载数据进行健康分析
        workload_data = istio_parser.parse_istio_workload(deployment.to_dict())
        health_score = health_analyzer.analyze_workload_health(workload_data)

        # 提取Istio版本
        version = None
        if metadata.labels:
            version = metadata.labels.get("istio.io/rev") or metadata.labels.get(
                "version"
            )

        # 构建配置信息
        configuration = {
            "strategy": spec.strategy.to_dict() if spec.strategy else {},
            "selector": spec.selector.to_dict() if spec.selector else {},
            "template_spec": spec.template.to_dict() if spec.template else {},
        }

        # 构建健康状态
        health = GatewayWorkloadHealth(
            overall_score=health_score.overall_score,
            status=health_score.status.value,
            component_scores=health_score.component_scores,
            issues=health_score.issues,
            recommendations=health_score.recommendations,
        )

        # 构建流量指标（暂时为空，后续可以通过Prometheus获取）
        traffic_metrics = TrafficMetrics()

        # 构建GatewayWorkloadDetail对象
        gateway_detail = GatewayWorkloadDetail(
            name=metadata.name,
            namespace=metadata.namespace,
            uid=metadata.uid,
            creation_timestamp=k8s_utils.format_timestamp(metadata.creation_timestamp),
            age=k8s_utils.calculate_age(metadata.creation_timestamp),
            labels=metadata.labels or {},
            annotations=metadata.annotations or {},
            service_info=service_info,
            pods=pods,
            health=health,
            traffic_metrics=traffic_metrics,
            configuration=configuration,
            version=version,
        )

        logger.info(
            "[Gateway工作负载详情][%s]成功获取Gateway工作负载信息: %s",
            cluster_name,
            namespace,
        )
        return gateway_detail

    except Exception as e:
        logger.error(
            "[Gateway工作负载详情][%s]获取Gateway工作负载详情失败: %s, 错误: %s",
            cluster_name,
            namespace,
            str(e),
        )
        raise


@monitor_istio_performance("get_gateway_workload_logs", slow_threshold=3.0)
@optimize_memory_usage(max_object_size=512 * 1024)
@istio_cache_response(
    "istio_logs", "retrieve", cache_params_func=extract_istio_cache_params
)
async def get_gateway_workload_logs(
    k8s_client,
    namespace: str = "istio-system",
    container_name: str = "istio-proxy",
    since_time: Optional[datetime] = None,
    until_time: Optional[datetime] = None,
    tail_lines: Optional[int] = 100,
    previous: bool = False,
    timestamps: bool = True,
    cluster_name: str = "current",
) -> Optional[GatewayLogResponse]:
    """
    获取Gateway工作负载日志

    Args:
        k8s_client: Kubernetes客户端
        namespace: 命名空间
        container_name: 容器名称
        since_time: 开始时间
        until_time: 结束时间
        tail_lines: 获取行数
        previous: 是否获取前一个实例
        timestamps: 是否包含时间戳
        cluster_name: 集群名称

    Returns:
        Optional[GatewayLogResponse]: 日志响应，如果失败则返回None
    """
    logger = logging.getLogger("cloudpilot.gateway_workload_api")

    try:
        logger.info(
            "[Gateway工作负载日志][%s]开始获取Gateway工作负载日志: %s, 容器: %s",
            cluster_name,
            namespace,
            container_name,
        )

        # 获取istio-ingressgateway Pod
        v1 = client.CoreV1Api(k8s_client)
        pod_list = v1.list_namespaced_pod(
            namespace=namespace, label_selector="app=istio-ingressgateway"
        )

        if not pod_list.items:
            logger.warning(
                "[Gateway工作负载日志][%s]未找到istio-ingressgateway Pod: %s",
                cluster_name,
                namespace,
            )
            return None

        # 使用第一个Pod
        pod = pod_list.items[0]
        pod_name = pod.metadata.name

        # 验证容器是否存在
        container_names = [c.name for c in pod.spec.containers]
        if container_name not in container_names:
            logger.error(
                "[Gateway工作负载日志][%s]容器不存在: %s, 可用容器: %s",
                cluster_name,
                container_name,
                container_names,
            )
            return None

        # 构建日志查询参数
        log_params = {
            "name": pod_name,
            "namespace": namespace,
            "container": container_name,
            "timestamps": timestamps,
            "previous": previous,
        }

        # 添加时间过滤
        if since_time:
            log_params["since_seconds"] = int(
                (
                    datetime.now().replace(tzinfo=None)
                    - since_time.replace(tzinfo=None)
                ).total_seconds()
            )

        # 添加行数限制
        if tail_lines and tail_lines > 0:
            log_params["tail_lines"] = min(tail_lines, 1000)

        # 获取日志
        try:
            raw_logs = v1.read_namespaced_pod_log(**log_params)
        except client.ApiException as e:
            logger.error(
                "[Gateway工作负载日志][%s]获取日志失败: %s, 状态码: %d",
                cluster_name,
                pod_name,
                e.status,
            )
            return None

        # 解析日志条目
        entries = []
        date_patterns = [
            r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)",  # ISO format
            r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})",  # YYYY/MM/DD HH:MM:SS
            r"^(\w{3} \d{2} \d{2}:\d{2}:\d{2})",  # MMM DD HH:MM:SS
        ]
        if raw_logs:
            lines = raw_logs.strip().split("\n")
            for line_num, line in enumerate(lines, 1):
                if not line.strip():
                    continue

                # 简单的日志解析
                timestamp = None
                for pattern in date_patterns:
                    match = re.match(pattern, line)
                    if match:
                        timestamp = match.group(1)
                        break
                message = line
                level = "info"
                is_error = False

                # 检测错误
                if any(
                    keyword in line.lower()
                    for keyword in ["error", "err", "exception", "fail"]
                ):
                    level = "error"
                    is_error = True
                elif any(keyword in line.lower() for keyword in ["warn", "warning"]):
                    level = "warning"

                entry = LogEntry(
                    timestamp=timestamp,
                    container_name=container_name,
                    message=message,
                    level=level,
                    is_error=is_error,
                    line_number=line_num,
                )
                entries.append(entry)

        # 统计错误和警告
        error_count = sum(1 for entry in entries if entry.is_error)
        warning_count = sum(1 for entry in entries if entry.level == "warning")

        log_response = GatewayLogResponse(
            pod_name=pod_name,
            namespace=namespace,
            container_name=container_name,
            total_lines=len(entries),
            entries=entries,
            error_count=error_count,
            warning_count=warning_count,
        )

        logger.info(
            "[Gateway工作负载日志][%s]成功获取Gateway工作负载日志: %s, 行数: %d, 错误: %d",
            cluster_name,
            pod_name,
            len(entries),
            error_count,
        )

        return log_response

    except Exception as e:
        logger.error(
            "[Gateway工作负载日志][%s]获取Gateway工作负载日志失败: %s, 错误: %s",
            cluster_name,
            namespace,
            str(e),
        )
        return None


@monitor_istio_performance("get_gateway_workload_events", slow_threshold=3.0)
@optimize_memory_usage(max_object_size=256 * 1024)
@istio_cache_response(
    "istio_events", "retrieve", cache_params_func=extract_istio_cache_params
)
async def get_gateway_workload_events(
    k8s_client,
    namespace: str = "istio-system",
    since_time: Optional[datetime] = None,
    last_hours: int = 24,
    limit: int = 100,
    cluster_name: str = "current",
) -> Optional[GatewayEventResponse]:
    """
    获取Gateway工作负载相关事件

    Args:
        k8s_client: Kubernetes客户端
        namespace: 命名空间
        since_time: 开始时间
        last_hours: 最近N小时
        limit: 返回事件数量限制
        cluster_name: 集群名称

    Returns:
        Optional[GatewayEventResponse]: 事件响应，如果失败则返回None
    """
    logger = logging.getLogger("cloudpilot.gateway_workload_api")

    try:
        logger.info(
            "[Gateway工作负载事件][%s]开始获取Gateway工作负载事件: %s",
            cluster_name,
            namespace,
        )

        # 获取事件
        v1 = client.CoreV1Api(k8s_client)
        event_list = v1.list_namespaced_event(namespace=namespace)

        # 过滤istio-ingressgateway相关事件
        gateway_events = []
        for event in event_list.items:
            involved_object = event.involved_object
            if (
                involved_object.name
                and "istio-ingressgateway" in involved_object.name.lower()
            ) or (
                involved_object.kind == "Deployment"
                and involved_object.name == "istio-ingressgateway"
            ):

                k8s_utils = K8sUtils(None)
                event_detail = EventDetail(
                    name=event.metadata.name,
                    namespace=event.metadata.namespace,
                    type=event.type or "Normal",
                    reason=event.reason or "",
                    message=event.message or "",
                    first_timestamp=k8s_utils.format_timestamp(event.first_timestamp),
                    last_timestamp=k8s_utils.format_timestamp(event.last_timestamp),
                    count=event.count or 1,
                    involved_object={
                        "kind": involved_object.kind,
                        "name": involved_object.name,
                        "namespace": involved_object.namespace,
                    },
                )
                gateway_events.append(event_detail)

        # 按时间排序，最新的在前
        gateway_events.sort(
            key=lambda x: x.last_timestamp or x.first_timestamp, reverse=True
        )

        # 应用限制
        if limit:
            gateway_events = gateway_events[:limit]

        # 统计
        total_events = len(gateway_events)
        warning_events = sum(1 for event in gateway_events if event.type == "Warning")
        error_events = sum(
            1 for event in gateway_events if "error" in event.reason.lower()
        )

        event_response = GatewayEventResponse(
            namespace=namespace,
            events=gateway_events,
            total_events=total_events,
            warning_events=warning_events,
            error_events=error_events,
        )

        logger.info(
            "[Gateway工作负载事件][%s]成功获取Gateway工作负载事件: %s, 总数: %d, 警告: %d",
            cluster_name,
            namespace,
            total_events,
            warning_events,
        )

        return event_response

    except Exception as e:
        logger.error(
            "[Gateway工作负载事件][%s]获取Gateway工作负载事件失败: %s, 错误: %s",
            cluster_name,
            namespace,
            str(e),
        )
        return None


def create_server_gateway_workload_router(server_mode_instance) -> APIRouter:
    """创建Server模式的Gateway工作负载API路由"""
    router = APIRouter(
        prefix="/istio/workloads/gateway", tags=["Istio Gateway Workload - Server"]
    )

    @router.post("/detail", response_model=GatewayWorkloadDetailResponse)
    async def get_gateway_workload_detail(request: GatewayWorkloadRequest):
        """获取Gateway工作负载详细信息"""
        cluster_name = request.cluster_name
        error_handler = create_error_handler(server_mode_instance.logger)

        if not cluster_name:
            raise error_handler.handle_validation_error(
                "Server模式下cluster_name参数必需",
                resource_type="gateway_workload",
                operation="detail",
            )

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                raise error_handler.handle_validation_error(
                    "集群不存在或连接失败",
                    cluster_name=cluster_name,
                    resource_type="gateway_workload",
                    operation="detail",
                )

            # 使用缓存装饰器处理缓存逻辑
            async def fetch_gateway_workload_data():
                # 获取动态客户端
                dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
                if not dynamic_client:
                    raise error_handler.handle_validation_error(
                        "集群客户端不存在",
                        cluster_name=cluster_name,
                        resource_type="gateway_workload",
                        operation="detail",
                    )

                # 获取Gateway工作负载详情
                gateway_detail = await get_gateway_workload_details(
                    dynamic_client, request.namespace, cluster_name
                )

                if not gateway_detail:
                    return {
                        "code": 404,
                        "message": f"istio-ingressgateway在命名空间 {request.namespace} 中不存在",
                    }

                return {"code": 200, "data": gateway_detail}

            # 使用缓存获取数据
            return await with_istio_cache(
                cluster_name=cluster_name,
                resource_type="gateway_workload",
                operation="detail",
                force_refresh=request.force_refresh,
                cache_params={"namespace": request.namespace},
                fetch_func=fetch_gateway_workload_data,
            )

        except Exception as e:
            raise error_handler.handle_k8s_exception(
                e,
                cluster_name=cluster_name,
                resource_type="gateway_workload",
                operation="detail",
                namespace=request.namespace,
            )

    @router.post("/logs", response_model=GatewayLogListResponse)
    async def get_gateway_workload_logs_endpoint(request: GatewayLogRequest):
        """获取Gateway工作负载日志"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取日志
            log_response = await get_gateway_workload_logs(
                dynamic_client.client,
                request.namespace,
                request.container_name,
                request.since_time,
                request.until_time,
                request.tail_lines,
                request.previous,
                request.timestamps,
                cluster_name,
            )

            if not log_response:
                return {
                    "code": 404,
                    "message": f"无法获取Gateway工作负载日志: {request.namespace}",
                }

            return {"code": 200, "data": log_response}

        except Exception as e:
            server_mode_instance.logger.error(
                "[Gateway工作负载日志][%s]获取Gateway工作负载日志失败: %s, 错误: %s",
                cluster_name,
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Gateway工作负载日志失败: {str(e)}"}

    @router.post("/events", response_model=GatewayEventListResponse)
    async def get_gateway_workload_events_endpoint(request: GatewayEventRequest):
        """获取Gateway工作负载事件"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取事件
            event_response = await get_gateway_workload_events(
                dynamic_client.client,
                request.namespace,
                request.since_time,
                request.last_hours,
                request.limit,
                cluster_name,
            )

            if not event_response:
                return {
                    "code": 404,
                    "message": f"无法获取Gateway工作负载事件: {request.namespace}",
                }

            return {"code": 200, "data": event_response}

        except Exception as e:
            server_mode_instance.logger.error(
                "[Gateway工作负载事件][%s]获取Gateway工作负载事件失败: %s, 错误: %s",
                cluster_name,
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Gateway工作负载事件失败: {str(e)}"}

    return router


def create_instant_gateway_workload_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的Gateway工作负载API路由"""
    router = APIRouter(
        prefix="/istio/workloads/gateway", tags=["Istio Gateway Workload - Instant"]
    )

    @router.post("/detail", response_model=GatewayWorkloadDetailResponse)
    async def get_gateway_workload_detail(request: GatewayWorkloadRequest):
        """获取Gateway工作负载详细信息"""
        cluster_name = "current"

        try:
            # 获取资源缓存
            cache = get_resource_cache()

            # 尝试从缓存获取数据
            if not request.force_refresh:
                cached_data = await cache.get(
                    cluster_name=cluster_name,
                    resource_type="gateway_workload",
                    operation="detail",
                    namespace=request.namespace,
                )
                if cached_data:
                    instant_mode_instance.logger.info(
                        "[Gateway工作负载详情][当前集群]使用缓存数据: %s",
                        request.namespace,
                    )
                    return cached_data

            # 获取Gateway工作负载详情
            gateway_detail = await get_gateway_workload_details(
                instant_mode_instance.dynamic_client, request.namespace, cluster_name
            )

            if not gateway_detail:
                response_data = {
                    "code": 404,
                    "message": f"istio-ingressgateway在命名空间 {request.namespace} 中不存在",
                }
                # 缓存404响应
                await cache.set(
                    cluster_name=cluster_name,
                    resource_type="gateway_workload",
                    operation="detail",
                    data=response_data,
                    namespace=request.namespace,
                )
                return response_data

            response_data = {"code": 200, "data": gateway_detail}

            # 缓存响应数据
            await cache.set(
                cluster_name=cluster_name,
                resource_type="gateway_workload",
                operation="detail",
                data=response_data,
                namespace=request.namespace,
            )

            return response_data

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Gateway工作负载详情][当前集群]获取Gateway工作负载详情失败: %s, 错误: %s",
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Gateway工作负载详情失败: {str(e)}"}

    @router.post("/logs", response_model=GatewayLogListResponse)
    async def get_gateway_workload_logs_endpoint(request: GatewayLogRequest):
        """获取Gateway工作负载日志"""
        cluster_name = "current"

        try:
            # 获取日志
            log_response = await get_gateway_workload_logs(
                instant_mode_instance.k8s_client,
                request.namespace,
                request.container_name,
                request.since_time,
                request.until_time,
                request.tail_lines,
                request.previous,
                request.timestamps,
                cluster_name,
            )

            if not log_response:
                return {
                    "code": 404,
                    "message": f"无法获取Gateway工作负载日志: {request.namespace}",
                }

            return {"code": 200, "data": log_response}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Gateway工作负载日志][当前集群]获取Gateway工作负载日志失败: %s, 错误: %s",
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Gateway工作负载日志失败: {str(e)}"}

    @router.post("/events", response_model=GatewayEventListResponse)
    async def get_gateway_workload_events_endpoint(request: GatewayEventRequest):
        """获取Gateway工作负载事件"""
        cluster_name = "current"

        try:
            # 获取事件
            event_response = await get_gateway_workload_events(
                instant_mode_instance.k8s_client,
                request.namespace,
                request.since_time,
                request.last_hours,
                request.limit,
                cluster_name,
            )

            if not event_response:
                return {
                    "code": 404,
                    "message": f"无法获取Gateway工作负载事件: {request.namespace}",
                }

            return {"code": 200, "data": event_response}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Gateway工作负载事件][当前集群]获取Gateway工作负载事件失败: %s, 错误: %s",
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Gateway工作负载事件失败: {str(e)}"}

    return router
