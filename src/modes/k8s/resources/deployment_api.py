# -*- coding: utf-8 -*-
"""
Deployment资源管理API
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from kubernetes import client

from src.core.k8s_utils import K8sUtils
from src.core.resource_parser import ResourceParser
from src.core.resource_cache import get_resource_cache


class DeploymentRequest(BaseModel):
    """Deployment请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    deployment_name: Optional[str] = Field(
        None, description="Deployment名称，为空则查询所有Deployment"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class ReplicaInfo(BaseModel):
    """副本信息模型"""

    desired: int = Field(..., description="期望副本数")
    current: int = Field(..., description="当前副本数")
    available: int = Field(..., description="可用副本数")
    ready: int = Field(..., description="就绪副本数")
    updated: int = Field(..., description="已更新副本数")
    unavailable: int = Field(0, description="不可用副本数")


class DeploymentStrategy(BaseModel):
    """部署策略模型"""

    type: str = Field(..., description="策略类型")
    max_surge: Optional[str] = Field(None, description="最大激增数")
    max_unavailable: Optional[str] = Field(None, description="最大不可用数")


class DeploymentCondition(BaseModel):
    """Deployment条件模型"""

    type: str = Field(..., description="条件类型")
    status: str = Field(..., description="条件状态")
    last_transition_time: Optional[str] = Field(None, description="最后转换时间")
    last_update_time: Optional[str] = Field(None, description="最后更新时间")
    reason: Optional[str] = Field(None, description="原因")
    message: Optional[str] = Field(None, description="消息")


class RolloutStatus(BaseModel):
    """滚动更新状态模型"""

    observed_generation: int = Field(..., description="观察到的代数")
    current_revision: Optional[str] = Field(None, description="当前版本")
    update_revision: Optional[str] = Field(None, description="更新版本")
    collision_count: Optional[int] = Field(None, description="冲突计数")
    conditions: List[DeploymentCondition] = Field(
        default_factory=list, description="部署条件"
    )


class ReplicaSetInfo(BaseModel):
    """ReplicaSet信息模型"""

    name: str = Field(..., description="ReplicaSet名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="ReplicaSet UID")
    revision: Optional[str] = Field(None, description="版本号")
    desired: int = Field(..., description="期望副本数")
    current: int = Field(..., description="当前副本数")
    ready: int = Field(..., description="就绪副本数")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")
    is_current: bool = Field(..., description="是否为当前版本")


class DeploymentDetail(BaseModel):
    """Deployment详细信息模型"""

    name: str = Field(..., description="Deployment名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="Deployment UID")
    generation: int = Field(..., description="代数")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")
    selector: Dict[str, Any] = Field(default_factory=dict, description="选择器")
    replicas: ReplicaInfo = Field(..., description="副本信息")
    strategy: DeploymentStrategy = Field(..., description="部署策略")
    rollout_status: RolloutStatus = Field(..., description="滚动更新状态")
    replicasets: List[ReplicaSetInfo] = Field(
        default_factory=list, description="关联的ReplicaSet"
    )
    template_spec: Dict[str, Any] = Field(
        default_factory=dict, description="Pod模板规格"
    )
    health_score: float = Field(100.0, description="健康分数 (0-100)")
    error_indicators: List[str] = Field(default_factory=list, description="错误指示器")
    scaling_history: List[Dict[str, Any]] = Field(
        default_factory=list, description="扩缩容历史"
    )


class DeploymentListResponse(BaseModel):
    """Deployment列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")


class DeploymentDetailResponse(BaseModel):
    """Deployment详情响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[DeploymentDetail] = Field(None, description="Deployment详情")


class ScalingHistoryResponse(BaseModel):
    """扩缩容历史响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="扩缩容历史数据")


# Deployment信息提取函数


def get_replicaset_info(
    apps_v1_api, namespace: str, deployment_name: str, cluster_name: str = "current"
) -> List[ReplicaSetInfo]:
    """
    获取Deployment关联的ReplicaSet信息

    Args:
        apps_v1_api: Apps V1 API客户端
        namespace: 命名空间
        deployment_name: Deployment名称
        cluster_name: 集群名称

    Returns:
        List[ReplicaSetInfo]: ReplicaSet信息列表
    """
    logger = logging.getLogger("cloudpilot.deployment_api")

    try:
        logger.info(
            "[Deployment详情][%s]开始获取ReplicaSet信息: %s/%s",
            cluster_name,
            namespace,
            deployment_name,
        )

        # 获取所有ReplicaSet
        rs_list = apps_v1_api.list_namespaced_replica_set(namespace=namespace)

        replicasets = []
        k8s_utils = K8sUtils(None)  # 临时创建，仅用于时间格式化

        for rs in rs_list.items:
            # 检查是否属于指定的Deployment
            owner_refs = rs.metadata.owner_references or []
            is_owned_by_deployment = any(
                owner.kind == "Deployment" and owner.name == deployment_name
                for owner in owner_refs
            )

            if not is_owned_by_deployment:
                continue

            # 提取ReplicaSet信息
            rs_info = ReplicaSetInfo(
                name=rs.metadata.name,
                namespace=rs.metadata.namespace,
                uid=rs.metadata.uid,
                revision=rs.metadata.annotations.get(
                    "deployment.kubernetes.io/revision"
                ),
                desired=rs.spec.replicas or 0,
                current=rs.status.replicas or 0,
                ready=rs.status.ready_replicas or 0,
                creation_timestamp=k8s_utils.format_timestamp(
                    rs.metadata.creation_timestamp
                ),
                age=k8s_utils.calculate_age(rs.metadata.creation_timestamp),
                labels=rs.metadata.labels or {},
                annotations=rs.metadata.annotations or {},
                is_current=(rs.status.replicas or 0) > 0,  # 简单判断是否为当前版本
            )

            replicasets.append(rs_info)

        # 按创建时间排序，最新的在前
        replicasets.sort(key=lambda x: x.creation_timestamp, reverse=True)

        logger.info(
            "[Deployment详情][%s]成功获取%d个ReplicaSet: %s/%s",
            cluster_name,
            len(replicasets),
            namespace,
            deployment_name,
        )

        return replicasets

    except Exception as e:
        logger.error(
            "[Deployment详情][%s]获取ReplicaSet信息失败: %s/%s, 错误: %s",
            cluster_name,
            namespace,
            deployment_name,
            str(e),
        )
        return []


def analyze_rollout_status(
    deployment_data: Dict[str, Any], cluster_name: str = "current"
) -> RolloutStatus:
    """
    分析Deployment滚动更新状态

    Args:
        deployment_data: Deployment原始数据
        cluster_name: 集群名称

    Returns:
        RolloutStatus: 滚动更新状态
    """
    logger = logging.getLogger("cloudpilot.deployment_api")

    try:
        status = deployment_data.get("status", {})
        metadata = deployment_data.get("metadata", {})

        # 提取基本状态信息
        observed_generation = status.get("observedGeneration", 0)
        collision_count = status.get("collisionCount")

        # 提取版本信息
        annotations = metadata.get("annotations", {})
        current_revision = annotations.get("deployment.kubernetes.io/revision")

        # 提取条件信息
        conditions = []
        k8s_utils = K8sUtils(None)  # 临时创建，仅用于时间格式化

        for condition in status.get("conditions", []):
            deploy_condition = DeploymentCondition(
                type=condition.get("type", ""),
                status=condition.get("status", ""),
                last_transition_time=k8s_utils.format_timestamp(
                    condition.get("lastTransitionTime")
                ),
                last_update_time=k8s_utils.format_timestamp(
                    condition.get("lastUpdateTime")
                ),
                reason=condition.get("reason"),
                message=condition.get("message"),
            )
            conditions.append(deploy_condition)

        rollout_status = RolloutStatus(
            observed_generation=observed_generation,
            current_revision=current_revision,
            update_revision=current_revision,  # 简化处理
            collision_count=collision_count,
            conditions=conditions,
        )

        logger.debug(
            "[Deployment详情][%s]分析滚动更新状态完成，观察代数: %d",
            cluster_name,
            observed_generation,
        )

        return rollout_status

    except Exception as e:
        logger.error(
            "[Deployment详情][%s]分析滚动更新状态失败: %s", cluster_name, str(e)
        )
        return RolloutStatus(
            observed_generation=0,
            conditions=[],
        )


def calculate_deployment_health_score(
    deployment_data: Dict[str, Any], replicasets: List[ReplicaSetInfo]
) -> float:
    """
    计算Deployment健康分数供LLM分析

    Args:
        deployment_data: Deployment原始数据
        replicasets: ReplicaSet信息列表

    Returns:
        float: 健康分数 (0-100)
    """
    logger = logging.getLogger("cloudpilot.deployment_api")

    try:
        score = 100.0
        status = deployment_data.get("status", {})

        # 检查副本状态
        desired_replicas = status.get("replicas", 0)
        available_replicas = status.get("availableReplicas", 0)
        ready_replicas = status.get("readyReplicas", 0)
        updated_replicas = status.get("updatedReplicas", 0)

        if desired_replicas > 0:
            # 可用性检查
            availability_ratio = available_replicas / desired_replicas
            if availability_ratio < 0.5:
                score -= 50
            elif availability_ratio < 0.8:
                score -= 30
            elif availability_ratio < 1.0:
                score -= 10

            # 就绪性检查
            readiness_ratio = ready_replicas / desired_replicas
            if readiness_ratio < 0.5:
                score -= 30
            elif readiness_ratio < 0.8:
                score -= 20
            elif readiness_ratio < 1.0:
                score -= 10

            # 更新状态检查
            update_ratio = updated_replicas / desired_replicas
            if update_ratio < 1.0:
                score -= 15  # 正在更新中

        # 检查部署条件
        conditions = status.get("conditions", [])
        for condition in conditions:
            if (
                condition.get("type") == "Available"
                and condition.get("status") != "True"
            ):
                score -= 25
            elif condition.get("type") == "Progressing":
                if condition.get("status") != "True":
                    score -= 20
                elif condition.get("reason") == "ProgressDeadlineExceeded":
                    score -= 40

        # 检查ReplicaSet状态
        if replicasets:
            current_rs = next((rs for rs in replicasets if rs.is_current), None)
            if current_rs and current_rs.desired != current_rs.ready:
                score -= 15

        # 确保分数在0-100范围内
        score = max(0.0, min(100.0, score))

        return score

    except Exception as e:
        logger.error("计算Deployment健康分数失败: %s", str(e))
        return 0.0


def get_deployment_details(
    dynamic_client, namespace: str, deployment_name: str, cluster_name: str = "current"
) -> Optional[DeploymentDetail]:
    """
    提取Deployment详细信息

    Args:
        dynamic_client: Kubernetes动态客户端
        namespace: 命名空间
        deployment_name: Deployment名称
        cluster_name: 集群名称

    Returns:
        Optional[DeploymentDetail]: Deployment详细信息，如果不存在则返回None
    """
    logger = logging.getLogger("cloudpilot.deployment_api")

    try:
        logger.info(
            "[Deployment详情][%s]开始提取Deployment信息: %s/%s",
            cluster_name,
            namespace,
            deployment_name,
        )

        # 获取Deployment信息
        apps_v1 = client.AppsV1Api(dynamic_client.client)
        deployment = apps_v1.read_namespaced_deployment(
            name=deployment_name, namespace=namespace
        )

        # 初始化工具类
        k8s_utils = K8sUtils(dynamic_client)
        resource_parser = ResourceParser()

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
            unavailable=status.unavailable_replicas or 0,
        )

        # 提取部署策略
        strategy_spec = spec.strategy
        strategy = DeploymentStrategy(
            type=strategy_spec.type if strategy_spec else "RollingUpdate",
            max_surge=(
                str(strategy_spec.rolling_update.max_surge)
                if strategy_spec and strategy_spec.rolling_update
                else None
            ),
            max_unavailable=(
                str(strategy_spec.rolling_update.max_unavailable)
                if strategy_spec and strategy_spec.rolling_update
                else None
            ),
        )

        # 分析滚动更新状态
        rollout_status = analyze_rollout_status(deployment.to_dict(), cluster_name)

        # 获取关联的ReplicaSet
        replicasets = get_replicaset_info(
            apps_v1, namespace, deployment_name, cluster_name
        )

        # 计算健康分数和错误指示器
        deployment_dict = deployment.to_dict()
        health_score = calculate_deployment_health_score(deployment_dict, replicasets)
        error_indicators = resource_parser.extract_error_indicators(
            {
                "kind": "Deployment",
                "name": deployment_name,
                "namespace": namespace,
                "status": (
                    "Running" if replicas.available == replicas.desired else "Degraded"
                ),
                "desired_replicas": replicas.desired,
                "available_replicas": replicas.available,
                "ready_replicas": replicas.ready,
            }
        )

        # 构建DeploymentDetail对象
        deployment_detail = DeploymentDetail(
            name=metadata.name,
            namespace=metadata.namespace,
            uid=metadata.uid,
            generation=metadata.generation or 0,
            creation_timestamp=k8s_utils.format_timestamp(metadata.creation_timestamp),
            age=k8s_utils.calculate_age(metadata.creation_timestamp),
            labels=metadata.labels or {},
            annotations=metadata.annotations or {},
            selector=spec.selector.to_dict() if spec.selector else {},
            replicas=replicas,
            strategy=strategy,
            rollout_status=rollout_status,
            replicasets=replicasets,
            template_spec=spec.template.to_dict() if spec.template else {},
            health_score=health_score,
            error_indicators=error_indicators,
            scaling_history=[],  # 暂时为空，后续可以通过事件获取
        )

        logger.info(
            "[Deployment详情][%s]成功提取Deployment信息: %s/%s",
            cluster_name,
            namespace,
            deployment_name,
        )
        return deployment_detail

    except client.ApiException as e:
        if e.status == 404:
            logger.warning(
                "[Deployment详情][%s]Deployment不存在: %s/%s",
                cluster_name,
                namespace,
                deployment_name,
            )
            return None
        logger.error(
            "[Deployment详情][%s]API错误: %s/%s, 状态码: %d",
            cluster_name,
            namespace,
            deployment_name,
            e.status,
        )
        raise
    except Exception as e:
        logger.error(
            "[Deployment详情][%s]提取Deployment详情失败: %s/%s, 错误: %s",
            cluster_name,
            namespace,
            deployment_name,
            str(e),
        )
        raise


def create_server_deployment_router(server_mode_instance) -> APIRouter:
    """创建Server模式的Deployment API路由"""
    router = APIRouter(
        prefix="/k8s/resources/deployments", tags=["K8s Deployment Resources - Server"]
    )

    @router.post("/list", response_model=DeploymentListResponse)
    async def list_deployments(request: DeploymentRequest):
        """获取Deployment列表"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # 获取资源缓存
            cache = get_resource_cache()

            # 尝试从缓存获取数据
            if not request.force_refresh:
                cached_data = await cache.get(
                    cluster_name=cluster_name,
                    resource_type="deployment",
                    operation="list",
                    namespace=request.namespace,
                )
                if cached_data:
                    server_mode_instance.logger.info(
                        "[Deployment列表][%s]使用缓存数据，命名空间: %s",
                        cluster_name,
                        request.namespace or "所有",
                    )
                    return cached_data

            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[Deployment列表][%s]开始获取Deployment列表，命名空间: %s",
                cluster_name,
                request.namespace or "所有",
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取Deployment列表
            apps_v1 = client.AppsV1Api(dynamic_client.client)

            if request.namespace:
                deployment_list = apps_v1.list_namespaced_deployment(
                    namespace=request.namespace
                )
            else:
                deployment_list = apps_v1.list_deployment_for_all_namespaces()

            deployments = []
            k8s_utils = K8sUtils(dynamic_client)
            for deployment in deployment_list.items:
                # 提取基本Deployment信息
                deployment_info = {
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                    "desired_replicas": deployment.spec.replicas or 0,
                    "current_replicas": deployment.status.replicas or 0,
                    "available_replicas": deployment.status.available_replicas or 0,
                    "ready_replicas": deployment.status.ready_replicas or 0,
                    "updated_replicas": deployment.status.updated_replicas or 0,
                    "unavailable_replicas": deployment.status.unavailable_replicas or 0,
                    "creation_timestamp": k8s_utils.format_timestamp(
                        deployment.metadata.creation_timestamp
                    ),
                    "age": k8s_utils.calculate_age(
                        deployment.metadata.creation_timestamp
                    ),
                    "strategy_type": (
                        deployment.spec.strategy.type
                        if deployment.spec.strategy
                        else "RollingUpdate"
                    ),
                    "labels": deployment.metadata.labels or {},
                    "selector": (
                        deployment.spec.selector.to_dict()
                        if deployment.spec.selector
                        else {}
                    ),
                }
                deployments.append(deployment_info)

            server_mode_instance.logger.info(
                "[Deployment列表][%s]成功获取%d个Deployment",
                cluster_name,
                len(deployments),
            )

            response_data = {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "namespace": request.namespace,
                    "deployments": deployments,
                    "count": len(deployments),
                },
            }

            # 缓存响应数据
            await cache.set(
                cluster_name=cluster_name,
                resource_type="deployment",
                operation="list",
                data=response_data,
                namespace=request.namespace,
            )

            return response_data

        except Exception as e:
            server_mode_instance.logger.error(
                "[Deployment列表][%s]获取Deployment列表失败: %s", cluster_name, str(e)
            )
            return {"code": 500, "message": f"获取Deployment列表失败: {str(e)}"}

    @router.post("/detail", response_model=DeploymentDetailResponse)
    async def get_deployment_detail(request: DeploymentRequest):
        """获取Deployment详细信息"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        if not request.deployment_name:
            return {"code": 400, "message": "deployment_name参数必需"}

        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[Deployment详情][%s]开始获取Deployment详情: %s/%s",
                cluster_name,
                request.namespace,
                request.deployment_name,
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取Deployment详情
            deployment_detail = get_deployment_details(
                dynamic_client,
                request.namespace,
                request.deployment_name,
                cluster_name,
            )

            if not deployment_detail:
                return {
                    "code": 404,
                    "message": f"Deployment {request.namespace}/{request.deployment_name} 不存在",
                }

            server_mode_instance.logger.info(
                "[Deployment详情][%s]成功获取Deployment详情: %s/%s",
                cluster_name,
                request.namespace,
                request.deployment_name,
            )

            return {"code": 200, "data": deployment_detail}

        except Exception as e:
            server_mode_instance.logger.error(
                "[Deployment详情][%s]获取Deployment详情失败: %s/%s, 错误: %s",
                cluster_name,
                request.namespace,
                request.deployment_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Deployment详情失败: {str(e)}"}

    @router.post("/scaling", response_model=ScalingHistoryResponse)
    async def get_scaling_history(request: DeploymentRequest):
        """获取Deployment扩缩容历史"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        if not request.deployment_name:
            return {"code": 400, "message": "deployment_name参数必需"}

        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[Deployment详情][%s]开始获取扩缩容历史: %s/%s",
                cluster_name,
                request.namespace,
                request.deployment_name,
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取扩缩容相关事件, 最近20次
            k8s_utils = K8sUtils(dynamic_client)
            events = await k8s_utils.get_resource_events(
                "Deployment", request.deployment_name, request.namespace, limit=20
            )

            # 过滤扩缩容相关事件
            scaling_events = []
            for event in events:
                if any(
                    keyword in event.get("reason", "").lower()
                    for keyword in ["scaled", "scaling", "replica"]
                ):
                    scaling_events.append(
                        {
                            "timestamp": event.get("last_timestamp"),
                            "type": event.get("type"),
                            "reason": event.get("reason"),
                            "message": event.get("message"),
                            "count": event.get("count", 1),
                        }
                    )

            server_mode_instance.logger.info(
                "[Deployment详情][%s]成功获取%d个扩缩容事件: %s/%s",
                cluster_name,
                len(scaling_events),
                request.namespace,
                request.deployment_name,
            )

            return {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "namespace": request.namespace,
                    "deployment_name": request.deployment_name,
                    "scaling_events": scaling_events,
                    "count": len(scaling_events),
                },
            }

        except Exception as e:
            server_mode_instance.logger.error(
                "[Deployment详情][%s]获取扩缩容历史失败: %s/%s, 错误: %s",
                cluster_name,
                request.namespace,
                request.deployment_name,
                str(e),
            )
            return {"code": 500, "message": f"获取扩缩容历史失败: {str(e)}"}

    return router


def create_instant_deployment_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的Deployment API路由"""
    router = APIRouter(
        prefix="/k8s/resources/deployments", tags=["K8s Deployment Resources - Instant"]
    )

    @router.post("/list", response_model=DeploymentListResponse)
    async def list_deployments(request: DeploymentRequest):
        """获取Deployment列表"""
        try:
            instant_mode_instance.logger.info(
                "[Deployment列表][当前集群]开始获取Deployment列表，命名空间: %s",
                request.namespace or "所有",
            )

            # 获取Deployment列表
            apps_v1 = client.AppsV1Api(instant_mode_instance.k8s_client)

            if request.namespace:
                deployment_list = apps_v1.list_namespaced_deployment(
                    namespace=request.namespace
                )
            else:
                deployment_list = apps_v1.list_deployment_for_all_namespaces()

            deployments = []
            k8s_utils = K8sUtils(instant_mode_instance.dynamic_client)
            for deployment in deployment_list.items:
                # 提取基本Deployment信息
                deployment_info = {
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                    "desired_replicas": deployment.spec.replicas or 0,
                    "current_replicas": deployment.status.replicas or 0,
                    "available_replicas": deployment.status.available_replicas or 0,
                    "ready_replicas": deployment.status.ready_replicas or 0,
                    "updated_replicas": deployment.status.updated_replicas or 0,
                    "unavailable_replicas": deployment.status.unavailable_replicas or 0,
                    "creation_timestamp": k8s_utils.format_timestamp(
                        deployment.metadata.creation_timestamp
                    ),
                    "age": k8s_utils.calculate_age(
                        deployment.metadata.creation_timestamp
                    ),
                    "strategy_type": (
                        deployment.spec.strategy.type
                        if deployment.spec.strategy
                        else "RollingUpdate"
                    ),
                    "labels": deployment.metadata.labels or {},
                    "selector": (
                        deployment.spec.selector.to_dict()
                        if deployment.spec.selector
                        else {}
                    ),
                }
                deployments.append(deployment_info)

            instant_mode_instance.logger.info(
                "[Deployment列表][当前集群]成功获取%d个Deployment", len(deployments)
            )

            return {
                "code": 200,
                "data": {
                    "namespace": request.namespace,
                    "deployments": deployments,
                    "count": len(deployments),
                },
            }

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Deployment列表][当前集群]获取Deployment列表失败: %s", str(e)
            )
            return {"code": 500, "message": f"获取Deployment列表失败: {str(e)}"}

    @router.post("/detail", response_model=DeploymentDetailResponse)
    async def get_deployment_detail(request: DeploymentRequest):
        """获取Deployment详细信息"""
        if not request.deployment_name:
            return {"code": 400, "message": "deployment_name参数必需"}

        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        try:
            instant_mode_instance.logger.info(
                "[Deployment详情][当前集群]开始获取Deployment详情: %s/%s",
                request.namespace,
                request.deployment_name,
            )

            # 获取Deployment详情
            deployment_detail = get_deployment_details(
                instant_mode_instance.dynamic_client,
                request.namespace,
                request.deployment_name,
                "当前集群",
            )

            if not deployment_detail:
                return {
                    "code": 404,
                    "message": f"Deployment {request.namespace}/{request.deployment_name} 不存在",
                }

            instant_mode_instance.logger.info(
                "[Deployment详情][当前集群]成功获取Deployment详情: %s/%s",
                request.namespace,
                request.deployment_name,
            )

            return {"code": 200, "data": deployment_detail}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Deployment详情][当前集群]获取Deployment详情失败: %s/%s, 错误: %s",
                request.namespace,
                request.deployment_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Deployment详情失败: {str(e)}"}

    @router.post("/scaling", response_model=ScalingHistoryResponse)
    async def get_scaling_history(request: DeploymentRequest):
        """获取Deployment扩缩容历史"""
        if not request.deployment_name:
            return {"code": 400, "message": "deployment_name参数必需"}

        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        try:
            instant_mode_instance.logger.info(
                "[Deployment详情][当前集群]开始获取扩缩容历史: %s/%s",
                request.namespace,
                request.deployment_name,
            )

            # 获取扩缩容相关事件
            k8s_utils = K8sUtils(instant_mode_instance.dynamic_client)
            events = await k8s_utils.get_resource_events(
                "Deployment", request.deployment_name, request.namespace, limit=50
            )

            # 过滤扩缩容相关事件
            scaling_events = []
            for event in events:
                if any(
                    keyword in event.get("reason", "").lower()
                    for keyword in ["scaled", "scaling", "replica"]
                ):
                    scaling_events.append(
                        {
                            "timestamp": event.get("last_timestamp"),
                            "type": event.get("type"),
                            "reason": event.get("reason"),
                            "message": event.get("message"),
                            "count": event.get("count", 1),
                        }
                    )

            instant_mode_instance.logger.info(
                "[Deployment详情][当前集群]成功获取%d个扩缩容事件: %s/%s",
                len(scaling_events),
                request.namespace,
                request.deployment_name,
            )

            return {
                "code": 200,
                "data": {
                    "namespace": request.namespace,
                    "deployment_name": request.deployment_name,
                    "scaling_events": scaling_events,
                    "count": len(scaling_events),
                },
            }

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Deployment详情][当前集群]获取扩缩容历史失败: %s/%s, 错误: %s",
                request.namespace,
                request.deployment_name,
                str(e),
            )
            return {"code": 500, "message": f"获取扩缩容历史失败: {str(e)}"}

    return router
