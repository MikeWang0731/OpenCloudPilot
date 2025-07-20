# -*- coding: utf-8 -*-
"""
Pod资源管理API
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from kubernetes import client

from src.core.k8s_utils import K8sUtils
from src.core.resource_parser import ResourceParser
from src.core.error_handler import create_error_handler, with_timeout
from src.core.resource_cache import get_resource_cache
from src.core.pagination import (
    PaginationRequest,
    LimitRequest,
    get_paginator,
    create_default_sort_func,
)
from src.core.async_utils import (
    get_batch_processor,
    get_resource_fetcher,
    async_timeout,
    monitor_performance,
    get_performance_monitor,
)
from src.core.pagination import (
    PaginationRequest,
    LimitRequest,
    get_paginator,
    create_default_sort_func,
)


class PodRequest(BaseModel):
    """Pod请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    pod_name: Optional[str] = Field(None, description="Pod名称，为空则查询所有Pod")
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")

    # 分页参数
    page: int = Field(1, ge=1, description="页码，从1开始")
    page_size: int = Field(50, ge=1, le=500, description="每页大小，最大500")
    sort_by: Optional[str] = Field("name", description="排序字段")
    sort_order: Optional[str] = Field("asc", description="排序顺序 (asc/desc)")

    # 限制参数
    limit: Optional[int] = Field(None, ge=1, le=10000, description="最大返回数量")


class ResourceUsage(BaseModel):
    """资源使用情况模型"""

    cpu_usage: Optional[str] = Field(None, description="CPU使用量")
    memory_usage: Optional[str] = Field(None, description="内存使用量")
    cpu_percentage: Optional[float] = Field(None, description="CPU使用百分比")
    memory_percentage: Optional[float] = Field(None, description="内存使用百分比")


class ResourceRequests(BaseModel):
    """资源请求和限制模型"""

    cpu_request: Optional[str] = Field(None, description="CPU请求")
    memory_request: Optional[str] = Field(None, description="内存请求")
    cpu_limit: Optional[str] = Field(None, description="CPU限制")
    memory_limit: Optional[str] = Field(None, description="内存限制")


class ContainerPort(BaseModel):
    """容器端口模型"""

    name: Optional[str] = Field(None, description="端口名称")
    container_port: int = Field(..., description="容器端口")
    protocol: Optional[str] = Field("TCP", description="协议")
    host_port: Optional[int] = Field(None, description="主机端口")


class ContainerInfo(BaseModel):
    """容器信息模型"""

    name: str = Field(..., description="容器名称")
    image: str = Field(..., description="镜像名称")
    image_pull_policy: Optional[str] = Field(None, description="镜像拉取策略")
    state: str = Field(..., description="容器状态")
    ready: bool = Field(..., description="是否就绪")
    restart_count: int = Field(0, description="重启次数")
    started_at: Optional[str] = Field(None, description="启动时间")
    finished_at: Optional[str] = Field(None, description="结束时间")
    exit_code: Optional[int] = Field(None, description="退出码")
    reason: Optional[str] = Field(None, description="状态原因")
    message: Optional[str] = Field(None, description="状态消息")
    ports: List[ContainerPort] = Field(default_factory=list, description="端口列表")
    resources: ResourceRequests = Field(
        default_factory=ResourceRequests, description="资源配置"
    )


class PodCondition(BaseModel):
    """Pod条件模型"""

    type: str = Field(..., description="条件类型")
    status: str = Field(..., description="条件状态")
    last_transition_time: Optional[str] = Field(None, description="最后转换时间")
    reason: Optional[str] = Field(None, description="原因")
    message: Optional[str] = Field(None, description="消息")


class PodDetail(BaseModel):
    """Pod详细信息模型"""

    name: str = Field(..., description="Pod名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="Pod UID")
    status: str = Field(..., description="Pod状态")
    phase: str = Field(..., description="Pod阶段")
    node_name: Optional[str] = Field(None, description="节点名称")
    pod_ip: Optional[str] = Field(None, description="Pod IP")
    host_ip: Optional[str] = Field(None, description="主机IP")
    creation_timestamp: str = Field(..., description="创建时间")
    start_time: Optional[str] = Field(None, description="启动时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")
    owner_references: List[Dict[str, Any]] = Field(
        default_factory=list, description="所有者引用"
    )
    containers: List[ContainerInfo] = Field(
        default_factory=list, description="容器列表"
    )
    init_containers: List[ContainerInfo] = Field(
        default_factory=list, description="初始化容器列表"
    )
    conditions: List[PodCondition] = Field(default_factory=list, description="Pod条件")
    resource_usage: Optional[ResourceUsage] = Field(None, description="资源使用情况")
    health_score: float = Field(100.0, description="健康分数 (0-100)")
    error_indicators: List[str] = Field(default_factory=list, description="错误指示器")
    qos_class: Optional[str] = Field(None, description="QoS类别")
    restart_policy: Optional[str] = Field(None, description="重启策略")
    service_account: Optional[str] = Field(None, description="服务账户")
    priority: Optional[int] = Field(None, description="优先级")
    priority_class_name: Optional[str] = Field(None, description="优先级类名")


class PodListResponse(BaseModel):
    """Pod列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")
    pagination: Optional[Dict[str, Any]] = Field(None, description="分页信息")


class PodDetailResponse(BaseModel):
    """Pod详情响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[PodDetail] = Field(None, description="Pod详情")


# Pod信息提取函数


def get_container_info(
    container_spec: Dict[str, Any], container_status: Optional[Dict[str, Any]] = None
) -> ContainerInfo:
    """
    提取容器信息

    Args:
        container_spec: 容器规格
        container_status: 容器状态

    Returns:
        ContainerInfo: 容器信息对象
    """
    logger = logging.getLogger("cloudpilot.pod_api")

    try:
        # 基本信息
        name = container_spec.get("name", "")
        image = container_spec.get("image", "")
        image_pull_policy = container_spec.get("imagePullPolicy", "")

        # 端口信息
        ports = []
        for port_spec in container_spec.get("ports", []):
            port = ContainerPort(
                name=port_spec.get("name"),
                container_port=port_spec.get("containerPort", 0),
                protocol=port_spec.get("protocol", "TCP"),
                host_port=port_spec.get("hostPort"),
            )
            ports.append(port)

        # 资源配置
        resources_spec = container_spec.get("resources", {})
        requests = resources_spec.get("requests", {})
        limits = resources_spec.get("limits", {})

        resources = ResourceRequests(
            cpu_request=requests.get("cpu"),
            memory_request=requests.get("memory"),
            cpu_limit=limits.get("cpu"),
            memory_limit=limits.get("memory"),
        )

        # 状态信息
        state = "Unknown"
        ready = False
        restart_count = 0
        started_at = None
        finished_at = None
        exit_code = None
        reason = None
        message = None

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
                waiting_info = container_state["waiting"]
                reason = waiting_info.get("reason")
                message = waiting_info.get("message")
            elif "terminated" in container_state:
                state = "Terminated"
                terminated_info = container_state["terminated"]
                exit_code = terminated_info.get("exitCode")
                reason = terminated_info.get("reason")
                message = terminated_info.get("message")
                if "startedAt" in terminated_info:
                    started_at = terminated_info["startedAt"]
                if "finishedAt" in terminated_info:
                    finished_at = terminated_info["finishedAt"]

        return ContainerInfo(
            name=name,
            image=image,
            image_pull_policy=image_pull_policy,
            state=state,
            ready=ready,
            restart_count=restart_count,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            reason=reason,
            message=message,
            ports=ports,
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


def calculate_pod_health_score(
    pod_data: Dict[str, Any], containers: List[ContainerInfo]
) -> float:
    """
    计算Pod健康分数供LLM分析

    Args:
        pod_data: Pod原始数据
        containers: 容器信息列表

    Returns:
        float: 健康分数 (0-100)
    """
    logger = logging.getLogger("cloudpilot.pod_api")

    try:
        score = 100.0

        # 检查Pod状态
        phase = pod_data.get("status", {}).get("phase", "")
        if phase != "Running":
            if phase == "Pending":
                score -= 30
            elif phase in ["Failed", "Unknown"]:
                score -= 50

        # 检查容器状态
        for container in containers:
            if not container.ready:
                score -= 20

            if container.state not in ["Running", "Completed"]:
                score -= 15

            # 检查重启次数
            if container.restart_count > 0:
                score -= min(container.restart_count * 5, 25)

        # 检查Pod条件
        conditions = pod_data.get("status", {}).get("conditions", [])
        for condition in conditions:
            if condition.get("type") == "Ready" and condition.get("status") != "True":
                score -= 20
            elif (
                condition.get("type") == "PodScheduled"
                and condition.get("status") != "True"
            ):
                score -= 15

        # 确保分数在0-100范围内
        score = max(0.0, min(100.0, score))

        return score

    except Exception as e:
        logger.error("计算Pod健康分数失败: %s", str(e))
        return 0.0


@async_timeout(30)
@monitor_performance("get_pod_details", get_performance_monitor())
async def get_pod_details(
    dynamic_client, namespace: str, pod_name: str, cluster_name: str = "current"
) -> Optional[PodDetail]:
    """
    提取Pod详细信息

    Args:
        k8s_client: Kubernetes客户端
        namespace: 命名空间
        pod_name: Pod名称
        cluster_name: 集群名称

    Returns:
        Optional[PodDetail]: Pod详细信息，如果不存在则返回None
    """
    logger = logging.getLogger("cloudpilot.pod_api")

    try:
        logger.info(
            "[Pod详情][%s]开始提取Pod信息: %s/%s", cluster_name, namespace, pod_name
        )

        # 获取Pod信息
        v1 = client.CoreV1Api(dynamic_client.client)
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)

        # 初始化工具类
        k8s_utils = K8sUtils(dynamic_client)
        resource_parser = ResourceParser()

        # 基本信息
        metadata = pod.metadata
        spec = pod.spec
        status = pod.status

        # 并发提取容器信息
        resource_fetcher = get_resource_fetcher()

        # 准备容器信息获取配置
        container_configs = []
        container_statuses = {cs.name: cs for cs in (status.container_statuses or [])}

        for container_spec in spec.containers:
            container_status = container_statuses.get(container_spec.name)
            container_configs.append(
                {
                    "name": f"container_{container_spec.name}",
                    "func": get_container_info,
                    "args": [
                        container_spec.to_dict(),
                        container_status.to_dict() if container_status else None,
                    ],
                }
            )

        # 准备初始化容器信息获取配置
        init_container_statuses = {
            cs.name: cs for cs in (status.init_container_statuses or [])
        }

        for init_container_spec in spec.init_containers or []:
            init_container_status = init_container_statuses.get(
                init_container_spec.name
            )
            container_configs.append(
                {
                    "name": f"init_container_{init_container_spec.name}",
                    "func": get_container_info,
                    "args": [
                        init_container_spec.to_dict(),
                        (
                            init_container_status.to_dict()
                            if init_container_status
                            else None
                        ),
                    ],
                }
            )

        # 并发获取所有容器信息
        container_results = await resource_fetcher.fetch_multiple_resources(
            container_configs
        )

        # 分离普通容器和初始化容器
        containers = []
        init_containers = []

        for key, container_info in container_results.items():
            if container_info:
                if key.startswith("init_container_"):
                    init_containers.append(container_info)
                else:
                    containers.append(container_info)

        # 提取Pod条件
        conditions = []
        for condition in status.conditions or []:
            pod_condition = PodCondition(
                type=condition.type,
                status=condition.status,
                last_transition_time=k8s_utils.format_timestamp(
                    condition.last_transition_time
                ),
                reason=condition.reason,
                message=condition.message,
            )
            conditions.append(pod_condition)

        # 提取所有者引用
        owner_references = []
        for owner_ref in metadata.owner_references or []:
            owner_references.append(
                {
                    "kind": owner_ref.kind,
                    "name": owner_ref.name,
                    "uid": owner_ref.uid,
                    "controller": owner_ref.controller,
                }
            )

        # 计算健康分数和错误指示器
        pod_dict = pod.to_dict()
        health_score = calculate_pod_health_score(pod_dict, containers)
        error_indicators = resource_parser.extract_error_indicators(
            {
                "kind": "Pod",
                "name": pod_name,
                "namespace": namespace,
                "status": status.phase,
                "restart_count": sum(c.restart_count for c in containers),
                "node_status": "Ready" if status.phase == "Running" else "NotReady",
            }
        )

        # 构建PodDetail对象
        pod_detail = PodDetail(
            name=metadata.name,
            namespace=metadata.namespace,
            uid=metadata.uid,
            status=status.phase or "Unknown",
            phase=status.phase or "Unknown",
            node_name=spec.node_name,
            pod_ip=status.pod_ip,
            host_ip=status.host_ip,
            creation_timestamp=k8s_utils.format_timestamp(metadata.creation_timestamp),
            start_time=k8s_utils.format_timestamp(status.start_time),
            age=k8s_utils.calculate_age(metadata.creation_timestamp),
            labels=metadata.labels or {},
            annotations=metadata.annotations or {},
            owner_references=owner_references,
            containers=containers,
            init_containers=init_containers,
            conditions=conditions,
            health_score=health_score,
            error_indicators=error_indicators,
            qos_class=status.qos_class,
            restart_policy=spec.restart_policy,
            service_account=spec.service_account_name,
            priority=spec.priority,
            priority_class_name=spec.priority_class_name,
        )

        logger.info(
            "[Pod详情][%s]成功提取Pod信息: %s/%s", cluster_name, namespace, pod_name
        )
        return pod_detail

    except client.ApiException as e:
        if e.status == 404:
            logger.warning(
                "[Pod详情][%s]Pod不存在: %s/%s", cluster_name, namespace, pod_name
            )
            return None
        else:
            logger.error(
                "[Pod详情][%s]API错误: %s/%s, 状态码: %d",
                cluster_name,
                namespace,
                pod_name,
                e.status,
            )
            raise
    except Exception as e:
        logger.error(
            "[Pod详情][%s]提取Pod详情失败: %s/%s, 错误: %s",
            cluster_name,
            namespace,
            pod_name,
            str(e),
        )
        raise


def create_server_pod_router(server_mode_instance) -> APIRouter:
    """创建Server模式的Pod API路由"""
    router = APIRouter(
        prefix="/k8s/resources/pods", tags=["K8s Pod Resources - Server"]
    )

    @router.post("/list", response_model=PodListResponse)
    async def list_pods(request: PodRequest):
        """获取Pod列表"""
        cluster_name = request.cluster_name
        error_handler = create_error_handler(server_mode_instance.logger)

        if not cluster_name:
            raise error_handler.handle_validation_error(
                "Server模式下cluster_name参数必需",
                resource_type="pod",
                operation="list",
            )

        try:
            # 获取资源缓存
            cache = get_resource_cache()

            # 尝试从缓存获取数据
            if not request.force_refresh:
                cached_data = await cache.get(
                    cluster_name=cluster_name,
                    resource_type="pod",
                    operation="list",
                    namespace=request.namespace,
                )
                if cached_data:
                    server_mode_instance.logger.info(
                        "[Pod列表][%s]使用缓存数据，命名空间: %s",
                        cluster_name,
                        request.namespace or "所有",
                    )
                    return cached_data

            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                raise error_handler.handle_validation_error(
                    "集群不存在或连接失败",
                    cluster_name=cluster_name,
                    resource_type="pod",
                    operation="list",
                )

            server_mode_instance.logger.info(
                "[Pod列表][%s]开始获取Pod列表，命名空间: %s",
                cluster_name,
                request.namespace or "所有",
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                raise error_handler.handle_validation_error(
                    "集群客户端不存在",
                    cluster_name=cluster_name,
                    resource_type="pod",
                    operation="list",
                )

            # 获取Pod列表 (带超时处理)
            @with_timeout(timeout_seconds=30)
            async def get_pod_list():
                v1 = client.CoreV1Api(dynamic_client.client)
                if request.namespace:
                    return v1.list_namespaced_pod(namespace=request.namespace)
                return v1.list_pod_for_all_namespaces()

            pod_list = await get_pod_list()

            # 使用批处理器并发处理Pod信息提取
            batch_processor = get_batch_processor()
            k8s_utils = K8sUtils(dynamic_client)

            async def extract_pod_info(pod):
                """提取单个Pod信息"""
                return {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase or "Unknown",
                    "node_name": pod.spec.node_name,
                    "pod_ip": pod.status.pod_ip,
                    "creation_timestamp": k8s_utils.format_timestamp(
                        pod.metadata.creation_timestamp
                    ),
                    "age": k8s_utils.calculate_age(pod.metadata.creation_timestamp),
                    "ready": sum(
                        1 for cs in (pod.status.container_statuses or []) if cs.ready
                    ),
                    "total_containers": len(pod.spec.containers),
                    "restart_count": sum(
                        cs.restart_count for cs in (pod.status.container_statuses or [])
                    ),
                    "labels": pod.metadata.labels or {},
                }

            # 并发处理所有Pod
            pods = await batch_processor.process_batch(
                pod_list.items,
                extract_pod_info,
                error_handler=lambda pod, e: {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": "Error",
                    "error": str(e),
                },
            )

            # 应用分页和排序
            paginator = get_paginator()
            pagination_request = PaginationRequest(
                page=request.page,
                page_size=request.page_size,
                sort_by=request.sort_by,
                sort_order=request.sort_order,
            )

            # 应用限制
            if request.limit:
                pods = pods[: request.limit]

            # 分页处理
            paginated_data = paginator.paginate_list(
                pods, pagination_request, create_default_sort_func("name")
            )

            server_mode_instance.logger.info(
                "[Pod列表][%s]成功获取%d个Pod，分页: %d/%d",
                cluster_name,
                len(pods),
                paginated_data.pagination.page,
                paginated_data.pagination.total_pages,
            )

            response_data = {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "namespace": request.namespace,
                    "pods": paginated_data.items,
                    "count": len(paginated_data.items),
                    "total_count": paginated_data.pagination.total_items,
                },
                "pagination": paginated_data.pagination.dict(),
            }

            # 缓存响应数据
            await cache.set(
                cluster_name=cluster_name,
                resource_type="pod",
                operation="list",
                data=response_data,
                namespace=request.namespace,
            )

            return response_data

        except Exception as e:
            raise error_handler.handle_k8s_exception(
                e,
                cluster_name=cluster_name,
                resource_type="pod",
                operation="list",
                namespace=request.namespace,
            )

    @router.post("/detail", response_model=PodDetailResponse)
    async def get_pod_detail(request: PodRequest):
        """获取Pod详细信息"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        if not request.pod_name:
            return {"code": 400, "message": "pod_name参数必需"}

        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        try:
            # 获取资源缓存
            cache = get_resource_cache()

            # 尝试从缓存获取数据
            if not request.force_refresh:
                cached_data = await cache.get(
                    cluster_name=cluster_name,
                    resource_type="pod",
                    operation="detail",
                    namespace=request.namespace,
                    pod_name=request.pod_name,
                )
                if cached_data:
                    server_mode_instance.logger.info(
                        "[Pod详情][%s]使用缓存数据: %s/%s",
                        cluster_name,
                        request.namespace,
                        request.pod_name,
                    )
                    return cached_data

            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[Pod详情][%s]开始获取Pod详情: %s/%s",
                cluster_name,
                request.namespace,
                request.pod_name,
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取Pod详情
            pod_detail = await get_pod_details(
                dynamic_client, request.namespace, request.pod_name, cluster_name
            )

            if not pod_detail:
                response_data = {
                    "code": 404,
                    "message": f"Pod {request.namespace}/{request.pod_name} 不存在",
                }
                # 缓存404响应（较短TTL）
                await cache.set(
                    cluster_name=cluster_name,
                    resource_type="pod",
                    operation="detail",
                    data=response_data,
                    namespace=request.namespace,
                    pod_name=request.pod_name,
                )
                return response_data

            server_mode_instance.logger.info(
                "[Pod详情][%s]成功获取Pod详情: %s/%s",
                cluster_name,
                request.namespace,
                request.pod_name,
            )

            response_data = {"code": 200, "data": pod_detail}

            # 缓存响应数据
            await cache.set(
                cluster_name=cluster_name,
                resource_type="pod",
                operation="detail",
                data=response_data,
                namespace=request.namespace,
                pod_name=request.pod_name,
            )

            return response_data

        except Exception as e:
            server_mode_instance.logger.error(
                "[Pod详情][%s]获取Pod详情失败: %s/%s, 错误: %s",
                cluster_name,
                request.namespace,
                request.pod_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Pod详情失败: {str(e)}"}

    return router


def create_instant_pod_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的Pod API路由"""
    router = APIRouter(
        prefix="/k8s/resources/pods", tags=["K8s Pod Resources - Instant"]
    )

    @router.post("/list", response_model=PodListResponse)
    async def list_pods(request: PodRequest):
        """获取Pod列表"""
        error_handler = create_error_handler(instant_mode_instance.logger)
        cluster_name = "current"

        try:
            # 获取资源缓存
            cache = get_resource_cache()

            # 尝试从缓存获取数据
            if not request.force_refresh:
                cached_data = await cache.get(
                    cluster_name=cluster_name,
                    resource_type="pod",
                    operation="list",
                    namespace=request.namespace,
                )
                if cached_data:
                    instant_mode_instance.logger.info(
                        "[Pod列表][当前集群]使用缓存数据，命名空间: %s",
                        request.namespace or "所有",
                    )
                    return cached_data

            instant_mode_instance.logger.info(
                "[Pod列表][当前集群]开始获取Pod列表，命名空间: %s",
                request.namespace or "所有",
            )

            # 获取Pod列表 (带超时处理)
            @with_timeout(timeout_seconds=30)
            async def get_pod_list():
                v1 = client.CoreV1Api(instant_mode_instance.k8s_client)
                if request.namespace:
                    return v1.list_namespaced_pod(namespace=request.namespace)
                return v1.list_pod_for_all_namespaces()

            pod_list = await get_pod_list()

            # 使用批处理器并发处理Pod信息提取
            batch_processor = get_batch_processor()
            k8s_utils = K8sUtils(instant_mode_instance.dynamic_client)

            async def extract_pod_info(pod):
                """提取单个Pod信息"""
                return {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase or "Unknown",
                    "node_name": pod.spec.node_name,
                    "pod_ip": pod.status.pod_ip,
                    "creation_timestamp": k8s_utils.format_timestamp(
                        pod.metadata.creation_timestamp
                    ),
                    "age": k8s_utils.calculate_age(pod.metadata.creation_timestamp),
                    "ready": sum(
                        1 for cs in (pod.status.container_statuses or []) if cs.ready
                    ),
                    "total_containers": len(pod.spec.containers),
                    "restart_count": sum(
                        cs.restart_count for cs in (pod.status.container_statuses or [])
                    ),
                    "labels": pod.metadata.labels or {},
                }

            # 并发处理所有Pod
            pods = await batch_processor.process_batch(
                pod_list.items,
                extract_pod_info,
                error_handler=lambda pod, e: {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": "Error",
                    "error": str(e),
                },
            )

            # 应用分页和排序
            paginator = get_paginator()
            pagination_request = PaginationRequest(
                page=request.page,
                page_size=request.page_size,
                sort_by=request.sort_by,
                sort_order=request.sort_order,
            )

            # 应用限制
            if request.limit:
                pods = pods[: request.limit]

            # 分页处理
            paginated_data = paginator.paginate_list(
                pods, pagination_request, create_default_sort_func("name")
            )

            instant_mode_instance.logger.info(
                "[Pod列表][当前集群]成功获取%d个Pod，分页: %d/%d",
                len(pods),
                paginated_data.pagination.page,
                paginated_data.pagination.total_pages,
            )

            response_data = {
                "code": 200,
                "data": {
                    "namespace": request.namespace,
                    "pods": paginated_data.items,
                    "count": len(paginated_data.items),
                    "total_count": paginated_data.pagination.total_items,
                },
                "pagination": paginated_data.pagination.dict(),
            }

            # 缓存响应数据
            await cache.set(
                cluster_name=cluster_name,
                resource_type="pod",
                operation="list",
                data=response_data,
                namespace=request.namespace,
            )

            return response_data

        except Exception as e:
            raise error_handler.handle_k8s_exception(
                e,
                cluster_name="当前集群",
                resource_type="pod",
                operation="list",
                namespace=request.namespace,
            )

    @router.post("/detail", response_model=PodDetailResponse)
    async def get_pod_detail(request: PodRequest):
        """获取Pod详细信息"""
        if not request.pod_name:
            return {"code": 400, "message": "pod_name参数必需"}

        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        cluster_name = "current"

        try:
            # 获取资源缓存
            cache = get_resource_cache()

            # 尝试从缓存获取数据
            if not request.force_refresh:
                cached_data = await cache.get(
                    cluster_name=cluster_name,
                    resource_type="pod",
                    operation="detail",
                    namespace=request.namespace,
                    pod_name=request.pod_name,
                )
                if cached_data:
                    instant_mode_instance.logger.info(
                        "[Pod详情][当前集群]使用缓存数据: %s/%s",
                        request.namespace,
                        request.pod_name,
                    )
                    return cached_data

            instant_mode_instance.logger.info(
                "[Pod详情][当前集群]开始获取Pod详情: %s/%s",
                request.namespace,
                request.pod_name,
            )

            # 获取Pod详情
            pod_detail = await get_pod_details(
                instant_mode_instance.dynamic_client,
                request.namespace,
                request.pod_name,
                "当前集群",
            )

            if not pod_detail:
                response_data = {
                    "code": 404,
                    "message": f"Pod {request.namespace}/{request.pod_name} 不存在",
                }
                # 缓存404响应（较短TTL）
                await cache.set(
                    cluster_name=cluster_name,
                    resource_type="pod",
                    operation="detail",
                    data=response_data,
                    namespace=request.namespace,
                    pod_name=request.pod_name,
                )
                return response_data

            instant_mode_instance.logger.info(
                "[Pod详情][当前集群]成功获取Pod详情: %s/%s",
                request.namespace,
                request.pod_name,
            )

            response_data = {"code": 200, "data": pod_detail}

            # 缓存响应数据
            await cache.set(
                cluster_name=cluster_name,
                resource_type="pod",
                operation="detail",
                data=response_data,
                namespace=request.namespace,
                pod_name=request.pod_name,
            )

            return response_data

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Pod详情][当前集群]获取Pod详情失败: %s/%s, 错误: %s",
                request.namespace,
                request.pod_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Pod详情失败: {str(e)}"}

    return router
