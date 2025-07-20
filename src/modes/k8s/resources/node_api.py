# -*- coding: utf-8 -*-
"""
Node资源管理API
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from kubernetes import client

from src.core.k8s_utils import K8sUtils
from src.core.resource_parser import ResourceParser


class NodeRequest(BaseModel):
    """Node请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    node_name: Optional[str] = Field(None, description="Node名称，为空则查询所有Node")
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class ResourceCapacity(BaseModel):
    """资源容量模型"""

    cpu: Optional[str] = Field(None, description="CPU容量")
    memory: Optional[str] = Field(None, description="内存容量")
    storage: Optional[str] = Field(None, description="存储容量")
    pods: Optional[str] = Field(None, description="Pod容量")
    hugepages_1gi: Optional[str] = Field(None, description="1Gi大页内存")
    hugepages_2mi: Optional[str] = Field(None, description="2Mi大页内存")
    ephemeral_storage: Optional[str] = Field(None, description="临时存储")


class ResourceUsage(BaseModel):
    """资源使用情况模型"""

    cpu_usage: Optional[str] = Field(None, description="CPU使用量")
    memory_usage: Optional[str] = Field(None, description="内存使用量")
    cpu_percentage: Optional[float] = Field(None, description="CPU使用百分比")
    memory_percentage: Optional[float] = Field(None, description="内存使用百分比")
    pod_count: Optional[int] = Field(None, description="当前Pod数量")
    pod_percentage: Optional[float] = Field(None, description="Pod使用百分比")


class NodeCondition(BaseModel):
    """Node条件模型"""

    type: str = Field(..., description="条件类型")
    status: str = Field(..., description="条件状态")
    last_heartbeat_time: Optional[str] = Field(None, description="最后心跳时间")
    last_transition_time: Optional[str] = Field(None, description="最后转换时间")
    reason: Optional[str] = Field(None, description="原因")
    message: Optional[str] = Field(None, description="消息")


class SystemInfo(BaseModel):
    """系统信息模型"""

    machine_id: Optional[str] = Field(None, description="机器ID")
    system_uuid: Optional[str] = Field(None, description="系统UUID")
    boot_id: Optional[str] = Field(None, description="启动ID")
    kernel_version: Optional[str] = Field(None, description="内核版本")
    os_image: Optional[str] = Field(None, description="操作系统镜像")
    container_runtime_version: Optional[str] = Field(None, description="容器运行时版本")
    kubelet_version: Optional[str] = Field(None, description="Kubelet版本")
    kube_proxy_version: Optional[str] = Field(None, description="Kube-proxy版本")
    operating_system: Optional[str] = Field(None, description="操作系统")
    architecture: Optional[str] = Field(None, description="架构")


class NodeDetail(BaseModel):
    """Node详细信息模型"""

    name: str = Field(..., description="Node名称")
    uid: str = Field(..., description="Node UID")
    status: str = Field(..., description="Node状态")
    roles: List[str] = Field(default_factory=list, description="节点角色")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")
    taints: List[Dict[str, Any]] = Field(default_factory=list, description="污点")
    capacity: ResourceCapacity = Field(..., description="资源容量")
    allocatable: ResourceCapacity = Field(..., description="可分配资源")
    usage: Optional[ResourceUsage] = Field(None, description="资源使用情况")
    conditions: List[NodeCondition] = Field(
        default_factory=list, description="Node条件"
    )
    system_info: Optional[SystemInfo] = Field(None, description="系统信息")
    addresses: List[Dict[str, str]] = Field(
        default_factory=list, description="地址信息"
    )
    health_score: float = Field(100.0, description="健康分数 (0-100)")
    error_indicators: List[str] = Field(default_factory=list, description="错误指示器")
    unschedulable: bool = Field(False, description="是否不可调度")


class NodeListResponse(BaseModel):
    """Node列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")


class NodeDetailResponse(BaseModel):
    """Node详情响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[NodeDetail] = Field(None, description="Node详情")


class NodeCapacityResponse(BaseModel):
    """Node容量响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="Node容量数据")


# Node信息提取函数


def calculate_resource_utilization(
    capacity: Dict[str, Any],
    allocatable: Dict[str, Any],
    pod_count: int = 0,
    cluster_name: str = "current",
) -> ResourceUsage:
    """
    计算Node资源利用率

    Args:
        capacity: 资源容量
        allocatable: 可分配资源
        pod_count: 当前Pod数量
        cluster_name: 集群名称

    Returns:
        ResourceUsage: 资源使用情况
    """
    logger = logging.getLogger("cloudpilot.node_api")

    try:
        logger.debug("[Node详情][%s]开始计算资源利用率", cluster_name)

        resource_parser = ResourceParser()

        # 解析CPU容量和可分配量
        cpu_capacity = resource_parser.parse_resource_usage(capacity.get("cpu", "0"),"cpu")
        cpu_allocatable = resource_parser.parse_resource_usage(
            allocatable.get("cpu", "0"),"cpu"
        )

        # 解析内存容量和可分配量
        memory_capacity = resource_parser.parse_resource_usage(
            capacity.get("memory", "0"),"memory"
        )
        memory_allocatable = resource_parser.parse_resource_usage(
            allocatable.get("memory", "0"),"memory"
        )

        # 解析Pod容量
        pod_capacity = int(capacity.get("pods", "0"))

        # 计算使用百分比（基于可分配资源）
        cpu_percentage = None
        memory_percentage = None
        pod_percentage = None

        if cpu_allocatable > 0:
            # 这里暂时使用可分配量作为使用量的基准，实际应该从metrics获取
            cpu_percentage = 0.0  # 需要metrics数据

        if memory_allocatable > 0:
            memory_percentage = 0.0  # 需要metrics数据

        if pod_capacity > 0:
            pod_percentage = (pod_count / pod_capacity) * 100.0

        usage = ResourceUsage(
            cpu_usage=None,  # 需要metrics数据
            memory_usage=None,  # 需要metrics数据
            cpu_percentage=cpu_percentage,
            memory_percentage=memory_percentage,
            pod_count=pod_count,
            pod_percentage=pod_percentage,
        )

        logger.debug(
            "[Node详情][%s]资源利用率计算完成，Pod使用率: %.1f%%",
            cluster_name,
            pod_percentage or 0.0,
        )

        return usage

    except Exception as e:
        logger.error("[Node详情][%s]计算资源利用率失败: %s", cluster_name, str(e))
        return ResourceUsage()


def analyze_node_conditions(
    conditions: List[Dict[str, Any]], cluster_name, dynamic_client
) -> tuple[List[NodeCondition], List[str]]:
    """
    分析Node健康条件

    Args:
        conditions: Node条件列表
        cluster_name: 集群名称

    Returns:
        tuple: (Node条件列表, 错误指示器列表)
    """
    logger = logging.getLogger("cloudpilot.node_api")

    try:
        logger.debug("[Node详情][%s]开始分析Node条件", cluster_name)

        k8s_utils = K8sUtils(dynamic_client)  # 临时创建，仅用于时间格式化
        node_conditions = []
        error_indicators = []

        for condition in conditions:
            node_condition = NodeCondition(
                type=condition.get("type", ""),
                status=condition.get("status", ""),
                last_heartbeat_time=k8s_utils.format_timestamp(
                    condition.get("lastHeartbeatTime")
                ),
                last_transition_time=k8s_utils.format_timestamp(
                    condition.get("lastTransitionTime")
                ),
                reason=condition.get("reason"),
                message=condition.get("message"),
            )
            node_conditions.append(node_condition)

            # 检查异常条件
            condition_type = condition.get("type", "")
            condition_status = condition.get("status", "")

            if condition_type == "Ready" and condition_status != "True":
                error_indicators.append("节点未就绪")
            elif condition_type == "MemoryPressure" and condition_status == "True":
                error_indicators.append("内存压力")
            elif condition_type == "DiskPressure" and condition_status == "True":
                error_indicators.append("磁盘压力")
            elif condition_type == "PIDPressure" and condition_status == "True":
                error_indicators.append("PID压力")
            elif condition_type == "NetworkUnavailable" and condition_status == "True":
                error_indicators.append("网络不可用")

        logger.debug(
            "[Node详情][%s]Node条件分析完成，发现%d个错误指示器",
            cluster_name,
            len(error_indicators),
        )

        return node_conditions, error_indicators

    except Exception as e:
        logger.error("[Node详情][%s]分析Node条件失败: %s", cluster_name, str(e))
        return [], [f"条件分析失败: {str(e)}"]


def calculate_node_health_score(
    node_data: Dict[str, Any],
    conditions: List[NodeCondition],
    error_indicators: List[str],
) -> float:
    """
    计算Node健康分数供LLM分析

    Args:
        node_data: Node原始数据
        conditions: Node条件列表
        error_indicators: 错误指示器列表

    Returns:
        float: 健康分数 (0-100)
    """
    logger = logging.getLogger("cloudpilot.node_api")

    try:
        score = 100.0

        # 检查Node是否可调度
        spec = node_data.get("spec", {})
        if spec.get("unschedulable", False):
            score -= 20

        # 检查污点数量
        taints = spec.get("taints", [])
        if taints:
            # 每个污点减少5分，最多减少25分
            score -= min(len(taints) * 5, 25)

        # 检查条件状态
        ready_condition = next((c for c in conditions if c.type == "Ready"), None)
        if ready_condition and ready_condition.status != "True":
            score -= 50

        # 根据错误指示器扣分
        for error in error_indicators:
            if "内存压力" in error:
                score -= 30
            elif "磁盘压力" in error:
                score -= 25
            elif "PID压力" in error:
                score -= 20
            elif "网络不可用" in error:
                score -= 40
            elif "未就绪" in error:
                score -= 50

        # 确保分数在0-100范围内
        score = max(0.0, min(100.0, score))

        return score

    except Exception as e:
        logger.error("计算Node健康分数失败: %s", str(e))
        return 0.0


def get_node_details(
    dynamic_client, node_name: str, cluster_name: str = "current"
) -> Optional[NodeDetail]:
    """
    提取Node详细信息

    Args:
        dynamic_client: Kubernetes动态客户端
        node_name: Node名称
        cluster_name: 集群名称

    Returns:
        Optional[NodeDetail]: Node详细信息，如果不存在则返回None
    """
    logger = logging.getLogger("cloudpilot.node_api")

    try:
        logger.info("[Node详情][%s]开始提取Node信息: %s", cluster_name, node_name)

        # 获取Node信息
        v1 = client.CoreV1Api(dynamic_client.client)
        node = v1.read_node(name=node_name)

        # 初始化工具类
        k8s_utils = K8sUtils(dynamic_client)
        resource_parser = ResourceParser()

        # 基本信息
        metadata = node.metadata
        spec = node.spec
        status = node.status

        # 提取角色信息
        roles = []
        labels = metadata.labels or {}
        for label_key in labels:
            if label_key.startswith("node-role.kubernetes.io/"):
                role = label_key.replace("node-role.kubernetes.io/", "")
                if role:
                    roles.append(role)

        # 如果没有找到角色标签，检查旧格式
        if not roles:
            if "kubernetes.io/role" in labels:
                roles.append(labels["kubernetes.io/role"])

        # 默认角色
        if not roles:
            roles.append("worker")

        # 提取资源容量
        capacity_data = status.capacity or {}
        capacity = ResourceCapacity(
            cpu=capacity_data.get("cpu"),
            memory=capacity_data.get("memory"),
            storage=capacity_data.get("storage"),
            pods=capacity_data.get("pods"),
            hugepages_1gi=capacity_data.get("hugepages-1Gi"),
            hugepages_2mi=capacity_data.get("hugepages-2Mi"),
            ephemeral_storage=capacity_data.get("ephemeral-storage"),
        )

        # 提取可分配资源
        allocatable_data = status.allocatable or {}
        allocatable = ResourceCapacity(
            cpu=allocatable_data.get("cpu"),
            memory=allocatable_data.get("memory"),
            storage=allocatable_data.get("storage"),
            pods=allocatable_data.get("pods"),
            hugepages_1gi=allocatable_data.get("hugepages-1Gi"),
            hugepages_2mi=allocatable_data.get("hugepages-2Mi"),
            ephemeral_storage=allocatable_data.get("ephemeral-storage"),
        )

        # 获取当前Pod数量
        pod_list = v1.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={node_name}"
        )
        pod_count = len(pod_list.items)

        # 计算资源使用情况
        usage = calculate_resource_utilization(
            capacity_data, allocatable_data, pod_count, cluster_name
        )

        # 分析Node条件
        conditions_data = status.conditions or []
        conditions, condition_errors = analyze_node_conditions(
            [c.to_dict() for c in conditions_data], cluster_name, dynamic_client
        )

        # 提取系统信息
        node_info = status.node_info
        system_info = None
        if node_info:
            system_info = SystemInfo(
                machine_id=node_info.machine_id,
                system_uuid=node_info.system_uuid,
                boot_id=node_info.boot_id,
                kernel_version=node_info.kernel_version,
                os_image=node_info.os_image,
                container_runtime_version=node_info.container_runtime_version,
                kubelet_version=node_info.kubelet_version,
                kube_proxy_version=node_info.kube_proxy_version,
                operating_system=node_info.operating_system,
                architecture=node_info.architecture,
            )

        # 提取地址信息
        addresses = []
        for addr in status.addresses or []:
            addresses.append(
                {
                    "type": addr.type,
                    "address": addr.address,
                }
            )

        # 提取污点信息
        taints = []
        for taint in spec.taints or []:
            taints.append(
                {
                    "key": taint.key,
                    "value": taint.value,
                    "effect": taint.effect,
                    "time_added": k8s_utils.format_timestamp(taint.time_added),
                }
            )

        # 计算健康分数和错误指示器
        node_dict = node.to_dict()
        additional_errors = resource_parser.extract_error_indicators(
            {
                "kind": "Node",
                "name": node_name,
                "status": (
                    "Ready"
                    if any(c.type == "Ready" and c.status == "True" for c in conditions)
                    else "NotReady"
                ),
                "unschedulable": spec.unschedulable or False,
                "taint_count": len(taints),
            }
        )

        all_errors = condition_errors + additional_errors
        health_score = calculate_node_health_score(node_dict, conditions, all_errors)

        # 构建NodeDetail对象
        node_detail = NodeDetail(
            name=metadata.name,
            uid=metadata.uid,
            status=(
                "Ready"
                if any(c.type == "Ready" and c.status == "True" for c in conditions)
                else "NotReady"
            ),
            roles=roles,
            creation_timestamp=k8s_utils.format_timestamp(metadata.creation_timestamp),
            age=k8s_utils.calculate_age(metadata.creation_timestamp),
            labels=labels,
            annotations=metadata.annotations or {},
            taints=taints,
            capacity=capacity,
            allocatable=allocatable,
            usage=usage,
            conditions=conditions,
            system_info=system_info,
            addresses=addresses,
            health_score=health_score,
            error_indicators=all_errors,
            unschedulable=spec.unschedulable or False,
        )

        logger.info("[Node详情][%s]成功提取Node信息: %s", cluster_name, node_name)
        return node_detail

    except client.ApiException as e:
        if e.status == 404:
            logger.warning("[Node详情][%s]Node不存在: %s", cluster_name, node_name)
            return None
        logger.error(
            "[Node详情][%s]API错误: %s, 状态码: %d", cluster_name, node_name, e.status
        )
        raise
    except Exception as e:
        logger.error(
            "[Node详情][%s]提取Node详情失败: %s, 错误: %s",
            cluster_name,
            node_name,
            str(e),
        )
        raise


def create_server_node_router(server_mode_instance) -> APIRouter:
    """创建Server模式的Node API路由"""
    router = APIRouter(
        prefix="/k8s/resources/nodes", tags=["K8s Node Resources - Server"]
    )

    @router.post("/list", response_model=NodeListResponse)
    async def list_nodes(request: NodeRequest):
        """获取Node列表"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[Node列表][%s]开始获取Node列表", cluster_name
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取Node列表
            v1 = client.CoreV1Api(dynamic_client.client)
            node_list = v1.list_node()

            nodes = []
            k8s_utils = K8sUtils(dynamic_client)
            for node in node_list.items:
                # 提取角色信息
                roles = []
                labels = node.metadata.labels or {}
                for label_key in labels:
                    if label_key.startswith("node-role.kubernetes.io/"):
                        role = label_key.replace("node-role.kubernetes.io/", "")
                        if role:
                            roles.append(role)

                if not roles:
                    if "kubernetes.io/role" in labels:
                        roles.append(labels["kubernetes.io/role"])

                if not roles:
                    roles.append("worker")

                # 检查Node状态
                ready_condition = next(
                    (c for c in (node.status.conditions or []) if c.type == "Ready"),
                    None,
                )
                node_status = (
                    "Ready"
                    if ready_condition and ready_condition.status == "True"
                    else "NotReady"
                )

                # 提取基本Node信息
                node_info = {
                    "name": node.metadata.name,
                    "status": node_status,
                    "roles": roles,
                    "age": k8s_utils.calculate_age(node.metadata.creation_timestamp),
                    "version": (
                        node.status.node_info.kubelet_version
                        if node.status.node_info
                        else "Unknown"
                    ),
                    "internal_ip": next(
                        (
                            addr.address
                            for addr in (node.status.addresses or [])
                            if addr.type == "InternalIP"
                        ),
                        "Unknown",
                    ),
                    "external_ip": next(
                        (
                            addr.address
                            for addr in (node.status.addresses or [])
                            if addr.type == "ExternalIP"
                        ),
                        None,
                    ),
                    "os_image": (
                        node.status.node_info.os_image
                        if node.status.node_info
                        else "Unknown"
                    ),
                    "kernel_version": (
                        node.status.node_info.kernel_version
                        if node.status.node_info
                        else "Unknown"
                    ),
                    "container_runtime": (
                        node.status.node_info.container_runtime_version
                        if node.status.node_info
                        else "Unknown"
                    ),
                    "capacity": {
                        "cpu": (
                            node.status.capacity.get("cpu")
                            if node.status.capacity
                            else None
                        ),
                        "memory": (
                            node.status.capacity.get("memory")
                            if node.status.capacity
                            else None
                        ),
                        "pods": (
                            node.status.capacity.get("pods")
                            if node.status.capacity
                            else None
                        ),
                    },
                    "allocatable": {
                        "cpu": (
                            node.status.allocatable.get("cpu")
                            if node.status.allocatable
                            else None
                        ),
                        "memory": (
                            node.status.allocatable.get("memory")
                            if node.status.allocatable
                            else None
                        ),
                        "pods": (
                            node.status.allocatable.get("pods")
                            if node.status.allocatable
                            else None
                        ),
                    },
                    "unschedulable": node.spec.unschedulable or False,
                    "labels": labels,
                    "taints": [
                        {
                            "key": taint.key,
                            "value": taint.value,
                            "effect": taint.effect,
                        }
                        for taint in (node.spec.taints or [])
                    ],
                }
                nodes.append(node_info)

            server_mode_instance.logger.info(
                "[Node列表][%s]成功获取%d个Node", cluster_name, len(nodes)
            )

            return {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "nodes": nodes,
                    "count": len(nodes),
                },
            }

        except Exception as e:
            server_mode_instance.logger.error(
                "[Node列表][%s]获取Node列表失败: %s", cluster_name, str(e)
            )
            return {"code": 500, "message": f"获取Node列表失败: {str(e)}"}

    @router.post("/detail", response_model=NodeDetailResponse)
    async def get_node_detail(request: NodeRequest):
        """获取Node详细信息"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        if not request.node_name:
            return {"code": 400, "message": "node_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[Node详情][%s]开始获取Node详情: %s", cluster_name, request.node_name
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取Node详情
            node_detail = get_node_details(
                dynamic_client, request.node_name, cluster_name
            )

            if not node_detail:
                return {
                    "code": 404,
                    "message": f"Node {request.node_name} 不存在",
                }

            server_mode_instance.logger.info(
                "[Node详情][%s]成功获取Node详情: %s", cluster_name, request.node_name
            )

            return {"code": 200, "data": node_detail}

        except Exception as e:
            server_mode_instance.logger.error(
                "[Node详情][%s]获取Node详情失败: %s, 错误: %s",
                cluster_name,
                request.node_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Node详情失败: {str(e)}"}

    @router.post("/capacity", response_model=NodeCapacityResponse)
    async def get_node_capacity(request: NodeRequest):
        """获取Node资源容量信息"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[Node详情][%s]开始获取Node容量信息", cluster_name
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取Node列表
            v1 = client.CoreV1Api(dynamic_client.client)

            if request.node_name:
                # 获取单个Node的容量信息
                node = v1.read_node(name=request.node_name)
                nodes = [node]
            else:
                # 获取所有Node的容量信息
                node_list = v1.list_node()
                nodes = node_list.items

            capacity_info = []
            resource_parser = ResourceParser()

            for node in nodes:
                capacity_data = node.status.capacity or {}
                allocatable_data = node.status.allocatable or {}

                # 获取当前Pod数量
                pod_list = v1.list_pod_for_all_namespaces(
                    field_selector=f"spec.nodeName={node.metadata.name}"
                )
                pod_count = len(pod_list.items)

                node_capacity = {
                    "node_name": node.metadata.name,
                    "capacity": {
                        "cpu": capacity_data.get("cpu"),
                        "memory": capacity_data.get("memory"),
                        "storage": capacity_data.get("storage"),
                        "pods": capacity_data.get("pods"),
                        "ephemeral_storage": capacity_data.get("ephemeral-storage"),
                    },
                    "allocatable": {
                        "cpu": allocatable_data.get("cpu"),
                        "memory": allocatable_data.get("memory"),
                        "storage": allocatable_data.get("storage"),
                        "pods": allocatable_data.get("pods"),
                        "ephemeral_storage": allocatable_data.get("ephemeral-storage"),
                    },
                    "usage": {
                        "pod_count": pod_count,
                        "pod_percentage": (
                            (pod_count / int(capacity_data.get("pods", "0"))) * 100.0
                            if capacity_data.get("pods")
                            and int(capacity_data.get("pods", "0")) > 0
                            else 0.0
                        ),
                    },
                    "utilization": {
                        "cpu_allocatable_cores": resource_parser.parse_resource_usage(
                            allocatable_data.get("cpu", "0"), "cpu"
                        ),
                        "memory_allocatable_bytes": resource_parser.parse_resource_usage(
                            allocatable_data.get("memory", "0"), "memory"
                        ),
                    },
                }
                capacity_info.append(node_capacity)

            server_mode_instance.logger.info(
                "[Node详情][%s]成功获取%d个Node的容量信息",
                cluster_name,
                len(capacity_info),
            )

            return {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "node_name": request.node_name,
                    "capacity_info": capacity_info,
                    "count": len(capacity_info),
                },
            }

        except Exception as e:
            server_mode_instance.logger.error(
                "[Node详情][%s]获取Node容量信息失败: %s", cluster_name, str(e)
            )
            return {"code": 500, "message": f"获取Node容量信息失败: {str(e)}"}

    return router


def create_instant_node_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的Node API路由"""
    router = APIRouter(
        prefix="/k8s/resources/nodes", tags=["K8s Node Resources - Instant"]
    )

    @router.post("/list", response_model=NodeListResponse)
    async def list_nodes(request: NodeRequest):
        """获取Node列表"""
        try:
            instant_mode_instance.logger.info("[Node列表][当前集群]开始获取Node列表")

            # 获取Node列表
            v1 = client.CoreV1Api(instant_mode_instance.k8s_client)
            node_list = v1.list_node()

            nodes = []
            k8s_utils = K8sUtils(instant_mode_instance.dynamic_client)
            for node in node_list.items:
                # 提取角色信息
                roles = []
                labels = node.metadata.labels or {}
                for label_key in labels:
                    if label_key.startswith("node-role.kubernetes.io/"):
                        role = label_key.replace("node-role.kubernetes.io/", "")
                        if role:
                            roles.append(role)

                if not roles:
                    if "kubernetes.io/role" in labels:
                        roles.append(labels["kubernetes.io/role"])

                if not roles:
                    roles.append("worker")

                # 检查Node状态
                ready_condition = next(
                    (c for c in (node.status.conditions or []) if c.type == "Ready"),
                    None,
                )
                node_status = (
                    "Ready"
                    if ready_condition and ready_condition.status == "True"
                    else "NotReady"
                )

                # 提取基本Node信息
                node_info = {
                    "name": node.metadata.name,
                    "status": node_status,
                    "roles": roles,
                    "age": k8s_utils.calculate_age(node.metadata.creation_timestamp),
                    "version": (
                        node.status.node_info.kubelet_version
                        if node.status.node_info
                        else "Unknown"
                    ),
                    "internal_ip": next(
                        (
                            addr.address
                            for addr in (node.status.addresses or [])
                            if addr.type == "InternalIP"
                        ),
                        "Unknown",
                    ),
                    "external_ip": next(
                        (
                            addr.address
                            for addr in (node.status.addresses or [])
                            if addr.type == "ExternalIP"
                        ),
                        None,
                    ),
                    "os_image": (
                        node.status.node_info.os_image
                        if node.status.node_info
                        else "Unknown"
                    ),
                    "kernel_version": (
                        node.status.node_info.kernel_version
                        if node.status.node_info
                        else "Unknown"
                    ),
                    "container_runtime": (
                        node.status.node_info.container_runtime_version
                        if node.status.node_info
                        else "Unknown"
                    ),
                    "capacity": {
                        "cpu": (
                            node.status.capacity.get("cpu")
                            if node.status.capacity
                            else None
                        ),
                        "memory": (
                            node.status.capacity.get("memory")
                            if node.status.capacity
                            else None
                        ),
                        "pods": (
                            node.status.capacity.get("pods")
                            if node.status.capacity
                            else None
                        ),
                    },
                    "allocatable": {
                        "cpu": (
                            node.status.allocatable.get("cpu")
                            if node.status.allocatable
                            else None
                        ),
                        "memory": (
                            node.status.allocatable.get("memory")
                            if node.status.allocatable
                            else None
                        ),
                        "pods": (
                            node.status.allocatable.get("pods")
                            if node.status.allocatable
                            else None
                        ),
                    },
                    "unschedulable": node.spec.unschedulable or False,
                    "labels": labels,
                    "taints": [
                        {
                            "key": taint.key,
                            "value": taint.value,
                            "effect": taint.effect,
                        }
                        for taint in (node.spec.taints or [])
                    ],
                }
                nodes.append(node_info)

            instant_mode_instance.logger.info(
                "[Node列表][当前集群]成功获取%d个Node", len(nodes)
            )

            return {
                "code": 200,
                "data": {
                    "nodes": nodes,
                    "count": len(nodes),
                },
            }

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Node列表][当前集群]获取Node列表失败: %s", str(e)
            )
            return {"code": 500, "message": f"获取Node列表失败: {str(e)}"}

    @router.post("/detail", response_model=NodeDetailResponse)
    async def get_node_detail(request: NodeRequest):
        """获取Node详细信息"""
        if not request.node_name:
            return {"code": 400, "message": "node_name参数必需"}

        try:
            instant_mode_instance.logger.info(
                "[Node详情][当前集群]开始获取Node详情: %s", request.node_name
            )

            # 获取Node详情
            node_detail = get_node_details(
                instant_mode_instance.dynamic_client, request.node_name, "当前集群"
            )

            if not node_detail:
                return {
                    "code": 404,
                    "message": f"Node {request.node_name} 不存在",
                }

            instant_mode_instance.logger.info(
                "[Node详情][当前集群]成功获取Node详情: %s", request.node_name
            )

            return {"code": 200, "data": node_detail}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Node详情][当前集群]获取Node详情失败: %s, 错误: %s",
                request.node_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Node详情失败: {str(e)}"}

    @router.post("/capacity", response_model=NodeCapacityResponse)
    async def get_node_capacity(request: NodeRequest):
        """获取Node资源容量信息"""
        try:
            instant_mode_instance.logger.info(
                "[Node详情][当前集群]开始获取Node容量信息"
            )

            # 获取Node列表
            v1 = client.CoreV1Api(instant_mode_instance.k8s_client)

            if request.node_name:
                # 获取单个Node的容量信息
                node = v1.read_node(name=request.node_name)
                nodes = [node]
            else:
                # 获取所有Node的容量信息
                node_list = v1.list_node()
                nodes = node_list.items

            capacity_info = []
            resource_parser = ResourceParser()

            for node in nodes:
                capacity_data = node.status.capacity or {}
                allocatable_data = node.status.allocatable or {}

                # 获取当前Pod数量
                pod_list = v1.list_pod_for_all_namespaces(
                    field_selector=f"spec.nodeName={node.metadata.name}"
                )
                pod_count = len(pod_list.items)

                node_capacity = {
                    "node_name": node.metadata.name,
                    "capacity": {
                        "cpu": capacity_data.get("cpu"),
                        "memory": capacity_data.get("memory"),
                        "storage": capacity_data.get("storage"),
                        "pods": capacity_data.get("pods"),
                        "ephemeral_storage": capacity_data.get("ephemeral-storage"),
                    },
                    "allocatable": {
                        "cpu": allocatable_data.get("cpu"),
                        "memory": allocatable_data.get("memory"),
                        "storage": allocatable_data.get("storage"),
                        "pods": allocatable_data.get("pods"),
                        "ephemeral_storage": allocatable_data.get("ephemeral-storage"),
                    },
                    "usage": {
                        "pod_count": pod_count,
                        "pod_percentage": (
                            (pod_count / int(capacity_data.get("pods", "0"))) * 100.0
                            if capacity_data.get("pods")
                            and int(capacity_data.get("pods", "0")) > 0
                            else 0.0
                        ),
                    },
                    "utilization": {
                        "cpu_allocatable_cores": resource_parser.parse_resource_usage(
                            allocatable_data.get("cpu", "0")
                        ),
                        "memory_allocatable_bytes": resource_parser.parse_resource_usage(
                            allocatable_data.get("memory", "0")
                        ),
                    },
                }
                capacity_info.append(node_capacity)

            instant_mode_instance.logger.info(
                "[Node详情][当前集群]成功获取%d个Node的容量信息", len(capacity_info)
            )

            return {
                "code": 200,
                "data": {
                    "node_name": request.node_name,
                    "capacity_info": capacity_info,
                    "count": len(capacity_info),
                },
            }

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Node详情][当前集群]获取Node容量信息失败: %s", str(e)
            )
            return {"code": 500, "message": f"获取Node容量信息失败: {str(e)}"}

    return router
