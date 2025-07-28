# -*- coding: utf-8 -*-
"""
Istiod工作负载管理API
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


class IstiodRequest(BaseModel):
    """Istiod请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        "istio-system", description="命名空间，默认istio-system"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class IstiodLogRequest(BaseModel):
    """Istiod日志请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        "istio-system", description="命名空间，默认istio-system"
    )
    container_name: Optional[str] = Field(
        "discovery", description="容器名称，默认discovery"
    )
    since_time: Optional[datetime] = Field(None, description="开始时间")
    until_time: Optional[datetime] = Field(None, description="结束时间")
    tail_lines: Optional[int] = Field(
        100, ge=1, le=10000, description="获取最后N行日志"
    )
    previous: Optional[bool] = Field(False, description="是否获取前一个容器实例的日志")
    timestamps: Optional[bool] = Field(True, description="是否包含时间戳")


class IstiodEventRequest(BaseModel):
    """Istiod事件请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        "istio-system", description="命名空间，默认istio-system"
    )
    since_time: Optional[datetime] = Field(None, description="开始时间")
    last_hours: Optional[int] = Field(24, ge=1, le=168, description="最近N小时")
    limit: Optional[int] = Field(100, ge=1, le=1000, description="返回事件数量限制")


class ContainerInfo(BaseModel):
    """容器信息模型"""

    name: str = Field(..., description="容器名称")
    image: str = Field(..., description="镜像名称")
    state: str = Field(..., description="容器状态")
    ready: bool = Field(..., description="是否就绪")
    restart_count: int = Field(0, description="重启次数")
    started_at: Optional[str] = Field(None, description="启动时间")
    resources: Dict[str, Any] = Field(default_factory=dict, description="资源配置")


class ReplicaInfo(BaseModel):
    """副本信息模型"""

    desired: int = Field(..., description="期望副本数")
    current: int = Field(..., description="当前副本数")
    available: int = Field(..., description="可用副本数")
    ready: int = Field(..., description="就绪副本数")
    updated: int = Field(..., description="已更新副本数")


class IstiodHealth(BaseModel):
    """Istiod健康状态模型"""

    overall_score: float = Field(..., description="总体健康分数 (0-100)")
    status: str = Field(..., description="健康状态")
    component_scores: Dict[str, float] = Field(
        default_factory=dict, description="组件分数"
    )
    issues: List[str] = Field(default_factory=list, description="问题列表")
    recommendations: List[str] = Field(default_factory=list, description="建议列表")


class IstiodDetail(BaseModel):
    """Istiod详细信息模型"""

    name: str = Field(..., description="Deployment名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="Deployment UID")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")
    replicas: ReplicaInfo = Field(..., description="副本信息")
    containers: List[ContainerInfo] = Field(
        default_factory=list, description="容器列表"
    )
    conditions: List[Dict[str, Any]] = Field(
        default_factory=list, description="部署条件"
    )
    health: IstiodHealth = Field(..., description="健康状态")
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


class IstiodLogResponse(BaseModel):
    """Istiod日志响应模型"""

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


class IstiodEventResponse(BaseModel):
    """Istiod事件响应模型"""

    namespace: str = Field(..., description="命名空间")
    events: List[EventDetail] = Field(default_factory=list, description="事件列表")
    total_events: int = Field(0, description="总事件数")
    warning_events: int = Field(0, description="警告事件数")
    error_events: int = Field(0, description="错误事件数")


class IstiodDetailResponse(BaseModel):
    """Istiod详情响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[IstiodDetail] = Field(None, description="Istiod详情")


class IstiodLogListResponse(BaseModel):
    """Istiod日志列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[IstiodLogResponse] = Field(None, description="日志数据")


class IstiodEventListResponse(BaseModel):
    """Istiod事件列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[IstiodEventResponse] = Field(None, description="事件数据")


# Istiod信息提取函数


def get_container_info_from_status(
    container_spec: Dict[str, Any], container_status: Optional[Dict[str, Any]] = None
) -> ContainerInfo:
    """
    从容器规格和状态提取容器信息

    Args:
        container_spec: 容器规格
        container_status: 容器状态

    Returns:
        ContainerInfo: 容器信息对象
    """
    logger = logging.getLogger("cloudpilot.istiod_api")

    try:
        name = container_spec.get("name", "")
        image = container_spec.get("image", "")

        # 状态信息
        state = "Unknown"
        ready = False
        restart_count = 0
        started_at = None

        if container_status:
            ready = container_status.get("ready", False)
            restart_count = container_status.get("restartCount", 0)

            # 解析容器状态
            container_state = container_status.get("state", {})
            if "running" in container_state:
                state = "Running"
                running_info = container_state["running"]
                if "startedAt" in running_info:
                    started_at = running_info["startedAt"]
            elif "waiting" in container_state:
                state = "Waiting"
            elif "terminated" in container_state:
                state = "Terminated"

        # 资源配置
        resources = container_spec.get("resources", {})

        return ContainerInfo(
            name=name,
            image=image,
            state=state,
            ready=ready,
            restart_count=restart_count,
            started_at=started_at,
            resources=resources,
        )

    except Exception as e:
        logger.error("提取容器信息失败: %s", str(e))
        return ContainerInfo(
            name=container_spec.get("name", "unknown"),
            image=container_spec.get("image", "unknown"),
            state="Error",
            ready=False,
        )


@async_timeout(30)
@monitor_performance("get_istiod_details", get_performance_monitor())
@monitor_istio_performance("get_istiod_details", slow_threshold=5.0)
@optimize_memory_usage(max_object_size=1024 * 1024)
@optimize_concurrent_operation(max_concurrent=5, rate_limit_delay=0.1)
@istio_cache_response("istiod", "detail", cache_params_func=extract_istio_cache_params)
async def get_istiod_details(
    dynamic_client, namespace: str = "istio-system", cluster_name: str = "current"
) -> Optional[IstiodDetail]:
    """
    获取Istiod详细信息

    Args:
        dynamic_client: Kubernetes动态客户端
        namespace: 命名空间
        cluster_name: 集群名称

    Returns:
        Optional[IstiodDetail]: Istiod详细信息，如果不存在则返回None
    """
    logger = logging.getLogger("cloudpilot.istiod_api")
    start_time = datetime.now()

    try:
        logger.info(
            "[Istiod详情][%s]开始获取Istiod信息 - 请求参数: namespace=%s",
            cluster_name,
            namespace,
        )

        # 获取istiod deployment
        apps_v1 = client.AppsV1Api(dynamic_client.client)

        try:
            deployment = apps_v1.read_namespaced_deployment(
                name="istiod", namespace=namespace
            )
        except client.ApiException as e:
            if e.status == 404:
                logger.warning(
                    "[Istiod详情][%s]Istiod deployment不存在: %s",
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

        # 提取副本信息
        replicas = ReplicaInfo(
            desired=spec.replicas or 0,
            current=status.replicas or 0,
            available=status.available_replicas or 0,
            ready=status.ready_replicas or 0,
            updated=status.updated_replicas or 0,
        )

        # 获取Pod信息以提取容器状态
        v1 = client.CoreV1Api(dynamic_client.client)
        pod_list = v1.list_namespaced_pod(
            namespace=namespace, label_selector="app=istiod"
        )

        containers = []
        if pod_list.items:
            # 使用第一个Pod的容器信息
            pod = pod_list.items[0]
            container_statuses = {
                cs.name: cs for cs in (pod.status.container_statuses or [])
            }

            for container_spec in pod.spec.containers:
                container_status = container_statuses.get(container_spec.name)
                container_info = get_container_info_from_status(
                    container_spec.to_dict(),
                    container_status.to_dict() if container_status else None,
                )
                containers.append(container_info)

        # 提取部署条件
        conditions = []
        for condition in status.conditions or []:
            conditions.append(
                {
                    "type": condition.type,
                    "status": condition.status,
                    "last_transition_time": k8s_utils.format_timestamp(
                        condition.last_transition_time
                    ),
                    "reason": condition.reason,
                    "message": condition.message,
                }
            )

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
        health = IstiodHealth(
            overall_score=health_score.overall_score,
            status=health_score.status.value,
            component_scores=health_score.component_scores,
            issues=health_score.issues,
            recommendations=health_score.recommendations,
        )

        # 构建IstiodDetail对象
        istiod_detail = IstiodDetail(
            name=metadata.name,
            namespace=metadata.namespace,
            uid=metadata.uid,
            creation_timestamp=k8s_utils.format_timestamp(metadata.creation_timestamp),
            age=k8s_utils.calculate_age(metadata.creation_timestamp),
            labels=metadata.labels or {},
            annotations=metadata.annotations or {},
            replicas=replicas,
            containers=containers,
            conditions=conditions,
            health=health,
            configuration=configuration,
            version=version,
        )

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            "[Istiod详情][%s]成功获取Istiod信息 - 响应摘要: namespace=%s, 健康分数=%.1f, 副本数=%d/%d, 处理时间=%.2fs",
            cluster_name,
            namespace,
            istiod_detail.health.overall_score,
            istiod_detail.replicas.ready,
            istiod_detail.replicas.desired,
            processing_time,
        )

        # 性能警告检查
        if processing_time > 3.0:
            logger.warning(
                "[Istiod详情][%s]操作耗时较长 - 处理时间=%.2fs, 建议检查集群性能",
                cluster_name,
                processing_time,
            )

        return istiod_detail

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[Istiod详情][%s]获取Istiod详情失败 - 错误详情: namespace=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            namespace,
            type(e).__name__,
            str(e),
            processing_time,
        )
        raise


@monitor_istio_performance("get_istiod_logs", slow_threshold=3.0)
@optimize_memory_usage(max_object_size=512 * 1024)
@istio_cache_response(
    "istio_logs", "retrieve", cache_params_func=extract_istio_cache_params
)
async def get_istiod_logs(
    k8s_client,
    namespace: str = "istio-system",
    container_name: str = "discovery",
    since_time: Optional[datetime] = None,
    until_time: Optional[datetime] = None,
    tail_lines: Optional[int] = 100,
    previous: bool = False,
    timestamps: bool = True,
    cluster_name: str = "current",
) -> Optional[IstiodLogResponse]:
    """
    获取Istiod日志

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
        Optional[IstiodLogResponse]: 日志响应，如果失败则返回None
    """
    logger = logging.getLogger("cloudpilot.istiod_api")
    start_time = datetime.now()

    try:
        logger.info(
            "[Istiod日志][%s]开始获取Istiod日志 - 请求参数: namespace=%s, container=%s, tail_lines=%s, previous=%s",
            cluster_name,
            namespace,
            container_name,
            tail_lines,
            previous,
        )

        # 获取istiod Pod
        v1 = client.CoreV1Api(k8s_client)
        pod_list = v1.list_namespaced_pod(
            namespace=namespace, label_selector="app=istiod"
        )

        if not pod_list.items:
            logger.warning(
                "[Istiod日志][%s]未找到Istiod Pod: %s", cluster_name, namespace
            )
            return None

        # 使用第一个Pod
        pod = pod_list.items[0]
        pod_name = pod.metadata.name

        # 验证容器是否存在
        container_names = [c.name for c in pod.spec.containers]
        if container_name not in container_names:
            logger.error(
                "[Istiod日志][%s]容器不存在: %s, 可用容器: %s",
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
                "[Istiod日志][%s]获取日志失败: %s, 状态码: %d",
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

        log_response = IstiodLogResponse(
            pod_name=pod_name,
            namespace=namespace,
            container_name=container_name,
            total_lines=len(entries),
            entries=entries,
            error_count=error_count,
            warning_count=warning_count,
        )

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            "[Istiod日志][%s]成功获取Istiod日志 - 响应摘要: pod=%s, 总行数=%d, 错误数=%d, 警告数=%d, 处理时间=%.2fs",
            cluster_name,
            pod_name,
            len(entries),
            error_count,
            warning_count,
            processing_time,
        )

        # 性能警告检查
        if processing_time > 2.0:
            logger.warning(
                "[Istiod日志][%s]日志获取耗时较长 - 处理时间=%.2fs, 建议减少tail_lines或优化查询条件",
                cluster_name,
                processing_time,
            )

        return log_response

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[Istiod日志][%s]获取Istiod日志失败 - 错误详情: namespace=%s, container=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            namespace,
            container_name,
            type(e).__name__,
            str(e),
            processing_time,
        )
        return None


@monitor_istio_performance("get_istiod_events", slow_threshold=3.0)
@optimize_memory_usage(max_object_size=256 * 1024)
@istio_cache_response(
    "istio_events", "retrieve", cache_params_func=extract_istio_cache_params
)
async def get_istiod_events(
    k8s_client,
    namespace: str = "istio-system",
    since_time: Optional[datetime] = None,
    last_hours: int = 24,
    limit: int = 100,
    cluster_name: str = "current",
) -> Optional[IstiodEventResponse]:
    """
    获取Istiod相关事件

    Args:
        k8s_client: Kubernetes客户端
        namespace: 命名空间
        since_time: 开始时间
        last_hours: 最近N小时
        limit: 返回事件数量限制
        cluster_name: 集群名称

    Returns:
        Optional[IstiodEventResponse]: 事件响应，如果失败则返回None
    """
    logger = logging.getLogger("cloudpilot.istiod_api")
    start_time = datetime.now()

    try:
        logger.info(
            "[Istiod事件][%s]开始获取Istiod事件 - 请求参数: namespace=%s, last_hours=%d, limit=%d",
            cluster_name,
            namespace,
            last_hours,
            limit,
        )

        # 获取事件
        v1 = client.CoreV1Api(k8s_client)
        event_list = v1.list_namespaced_event(namespace=namespace)

        # 过滤istiod相关事件
        istiod_events = []
        for event in event_list.items:
            involved_object = event.involved_object
            if (involved_object.name and "istiod" in involved_object.name.lower()) or (
                involved_object.kind == "Deployment"
                and involved_object.name == "istiod"
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
                istiod_events.append(event_detail)

        # 按时间排序，最新的在前
        istiod_events.sort(
            key=lambda x: x.last_timestamp or x.first_timestamp, reverse=True
        )

        # 应用限制
        if limit:
            istiod_events = istiod_events[:limit]

        # 统计
        total_events = len(istiod_events)
        warning_events = sum(1 for event in istiod_events if event.type == "Warning")
        error_events = sum(
            1 for event in istiod_events if "error" in event.reason.lower()
        )

        event_response = IstiodEventResponse(
            namespace=namespace,
            events=istiod_events,
            total_events=total_events,
            warning_events=warning_events,
            error_events=error_events,
        )

        # 计算处理时间并记录成功日志
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            "[Istiod事件][%s]成功获取Istiod事件 - 响应摘要: namespace=%s, 总事件数=%d, 警告事件=%d, 错误事件=%d, 处理时间=%.2fs",
            cluster_name,
            namespace,
            total_events,
            warning_events,
            error_events,
            processing_time,
        )

        # 性能警告检查
        if processing_time > 2.0:
            logger.warning(
                "[Istiod事件][%s]事件查询耗时较长 - 处理时间=%.2fs, 建议减少查询范围或优化过滤条件",
                cluster_name,
                processing_time,
            )

        return event_response

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            "[Istiod事件][%s]获取Istiod事件失败 - 错误详情: namespace=%s, 错误类型=%s, 错误信息=%s, 处理时间=%.2fs",
            cluster_name,
            namespace,
            type(e).__name__,
            str(e),
            processing_time,
        )
        return None


def create_server_istiod_router(server_mode_instance) -> APIRouter:
    """创建Server模式的Istiod API路由"""
    router = APIRouter(
        prefix="/istio/workloads/istiod", tags=["Istio Istiod Workload - Server"]
    )

    @router.post("/detail", response_model=IstiodDetailResponse)
    async def get_istiod_detail(request: IstiodRequest):
        """获取Istiod详细信息"""
        cluster_name = request.cluster_name
        error_handler = create_error_handler(server_mode_instance.logger)

        if not cluster_name:
            raise error_handler.handle_validation_error(
                "Server模式下cluster_name参数必需",
                resource_type="istiod",
                operation="detail",
            )

        try:
            # 使用缓存装饰器处理缓存逻辑
            async def fetch_istiod_data():
                # 获取动态客户端
                dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
                if not dynamic_client:
                    raise error_handler.handle_validation_error(
                        "集群客户端不存在",
                        cluster_name=cluster_name,
                        resource_type="istiod",
                        operation="detail",
                    )

                # 获取Istiod详情
                istiod_detail = await get_istiod_details(
                    dynamic_client, request.namespace, cluster_name
                )

                if not istiod_detail:
                    return {
                        "code": 404,
                        "message": f"Istiod在命名空间 {request.namespace} 中不存在",
                    }

                return {"code": 200, "data": istiod_detail}

            # 使用缓存获取数据
            return await with_istio_cache(
                cluster_name=cluster_name,
                resource_type="istiod",
                operation="detail",
                force_refresh=request.force_refresh,
                cache_params={"namespace": request.namespace},
                fetch_func=fetch_istiod_data,
            )

            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                raise error_handler.handle_validation_error(
                    "集群不存在或连接失败",
                    cluster_name=cluster_name,
                    resource_type="istiod",
                    operation="detail",
                )

        except Exception as e:
            raise error_handler.handle_k8s_exception(
                e,
                cluster_name=cluster_name,
                resource_type="istiod",
                operation="detail",
                namespace=request.namespace,
            )

    @router.post("/logs", response_model=IstiodLogListResponse)
    async def get_istiod_logs_endpoint(request: IstiodLogRequest):
        """获取Istiod日志"""
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
            log_response = await get_istiod_logs(
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
                    "message": f"无法获取Istiod日志: {request.namespace}",
                }

            return {"code": 200, "data": log_response}

        except Exception as e:
            server_mode_instance.logger.error(
                "[Istiod日志][%s]获取Istiod日志失败: %s, 错误: %s",
                cluster_name,
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Istiod日志失败: {str(e)}"}

    @router.post("/events", response_model=IstiodEventListResponse)
    async def get_istiod_events_endpoint(request: IstiodEventRequest):
        """获取Istiod事件"""
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
            event_response = await get_istiod_events(
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
                    "message": f"无法获取Istiod事件: {request.namespace}",
                }

            return {"code": 200, "data": event_response}

        except Exception as e:
            server_mode_instance.logger.error(
                "[Istiod事件][%s]获取Istiod事件失败: %s, 错误: %s",
                cluster_name,
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Istiod事件失败: {str(e)}"}

    return router


def create_instant_istiod_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的Istiod API路由"""
    router = APIRouter(
        prefix="/istio/workloads/istiod", tags=["Istio Istiod Workload - Instant"]
    )

    @router.post("/detail", response_model=IstiodDetailResponse)
    async def get_istiod_detail(request: IstiodRequest):
        """获取Istiod详细信息"""
        cluster_name = "current"

        try:
            # 使用缓存装饰器处理缓存逻辑
            async def fetch_istiod_data():
                # 获取Istiod详情
                istiod_detail = await get_istiod_details(
                    instant_mode_instance.k8s_client, request.namespace, cluster_name
                )

                if not istiod_detail:
                    return {
                        "code": 404,
                        "message": f"Istiod在命名空间 {request.namespace} 中不存在",
                    }

                return {"code": 200, "data": istiod_detail}

            # 使用缓存获取数据
            return await with_istio_cache(
                cluster_name=cluster_name,
                resource_type="istiod",
                operation="detail",
                force_refresh=request.force_refresh,
                cache_params={"namespace": request.namespace},
                fetch_func=fetch_istiod_data,
            )

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Istiod详情][当前集群]获取Istiod详情失败: %s, 错误: %s",
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Istiod详情失败: {str(e)}"}

    @router.post("/logs", response_model=IstiodLogListResponse)
    async def get_istiod_logs_endpoint(request: IstiodLogRequest):
        """获取Istiod日志"""
        try:
            # 获取日志
            log_response = await get_istiod_logs(
                instant_mode_instance.k8s_client,
                request.namespace,
                request.container_name,
                request.since_time,
                request.until_time,
                request.tail_lines,
                request.previous,
                request.timestamps,
                "当前集群",
            )

            if not log_response:
                return {
                    "code": 404,
                    "message": f"无法获取Istiod日志: {request.namespace}",
                }

            return {"code": 200, "data": log_response}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Istiod日志][当前集群]获取Istiod日志失败: %s, 错误: %s",
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Istiod日志失败: {str(e)}"}

    @router.post("/events", response_model=IstiodEventListResponse)
    async def get_istiod_events_endpoint(request: IstiodEventRequest):
        """获取Istiod事件"""
        try:
            # 获取事件
            event_response = await get_istiod_events(
                instant_mode_instance.k8s_client,
                request.namespace,
                request.since_time,
                request.last_hours,
                request.limit,
                "当前集群",
            )

            if not event_response:
                return {
                    "code": 404,
                    "message": f"无法获取Istiod事件: {request.namespace}",
                }

            return {"code": 200, "data": event_response}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Istiod事件][当前集群]获取Istiod事件失败: %s, 错误: %s",
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取Istiod事件失败: {str(e)}"}

    return router
