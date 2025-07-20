# -*- coding: utf-8 -*-
"""
集群监控模块
提供高效的K8s集群资源监控和概览信息获取功能
支持异步数据收集和缓存机制，减少对apiserver的压力
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

from kubernetes import client
from kubernetes.dynamic import DynamicClient


@dataclass
class ResourceOverview:
    """资源概览数据结构 - 按类别组织"""

    # 节点相关信息
    nodes: Dict[str, Any] = None

    # 工作负载相关信息（包含 pods 和 deployments）
    workloads: Dict[str, Any] = None

    # 服务发现相关信息
    discovery: Dict[str, Any] = None

    # 配置相关信息
    configs: Dict[str, Any] = None

    # 资源使用情况
    resources: Dict[str, Any] = None

    # 元数据
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        """初始化默认值"""
        if self.nodes is None:
            self.nodes = {"total": 0, "ready": 0, "not_ready": 0}

        if self.workloads is None:
            self.workloads = {
                "pods": {
                    "total": 0,
                    "running": 0,
                    "pending": 0,
                    "failed": 0,
                    "succeeded": 0,
                },
                "deployments": 0,
            }

        if self.discovery is None:
            self.discovery = {"services": 0}

        if self.configs is None:
            self.configs = {"configmaps": 0, "secrets": 0, "namespaces": 0}

        if self.resources is None:
            self.resources = {
                "cpu_requests": 0.0,
                "memory_requests": 0.0,
                "cpu_limits": 0.0,
                "memory_limits": 0.0,
            }

        if self.metadata is None:
            self.metadata = {"last_updated": None}


@dataclass
class NamespaceDetail:
    """命名空间详细信息"""

    name: str
    status: str
    pods: int = 0
    deployments: int = 0
    services: int = 0
    created_at: Optional[datetime] = None


@dataclass
class NodeDetail:
    """节点详细信息"""

    name: str
    status: str
    roles: List[str]
    version: str
    os_image: str
    kernel_version: str
    container_runtime: str
    cpu_capacity: str
    memory_capacity: str
    pods_capacity: str
    cpu_allocatable: str
    memory_allocatable: str
    pods_allocatable: str
    created_at: Optional[datetime] = None


class ClusterMonitor:
    """集群监控器"""

    def __init__(self, dynamic_client: DynamicClient, cache_ttl: int = 30):
        """
        初始化集群监控器

        Args:
            dynamic_client: Kubernetes动态客户端
            cache_ttl: 缓存生存时间（秒），默认30秒
        """
        self.dynamic_client = dynamic_client
        self.cache_ttl = cache_ttl
        self.logger = logging.getLogger("cloudpilot.ClusterMonitor")

        # 缓存数据
        self._overview_cache: Optional[ResourceOverview] = None
        self._namespaces_cache: Optional[List[NamespaceDetail]] = None
        self._nodes_cache: Optional[List[NodeDetail]] = None

        # 缓存时间戳
        self._overview_cache_time: Optional[datetime] = None
        self._namespaces_cache_time: Optional[datetime] = None
        self._nodes_cache_time: Optional[datetime] = None

        # API客户端
        self.v1 = client.CoreV1Api(self.dynamic_client.client)
        self.apps_v1 = client.AppsV1Api(self.dynamic_client.client)

    def _is_cache_valid(self, cache_time: Optional[datetime]) -> bool:
        """检查缓存是否有效"""
        if cache_time is None:
            return False
        return datetime.now() - cache_time < timedelta(seconds=self.cache_ttl)

    async def get_resource_overview(
        self, cluster_name: str, force_refresh: bool = False
    ) -> ResourceOverview:
        """
        获取集群资源概览

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            ResourceOverview: 资源概览信息
        """
        if (
            not force_refresh
            and self._is_cache_valid(self._overview_cache_time)
            and self._overview_cache
        ):
            self.logger.debug(
                "[获取集群资源概览][{%s}]使用缓存的资源概览数据", cluster_name
            )
            return self._overview_cache

        self.logger.info(
            "[获取集群资源概览][{%s}]开始收集集群资源概览数据...", cluster_name
        )
        start_time = time.time()

        try:
            # 并发获取各种资源信息
            tasks = [
                self._get_nodes_info(),
                self._get_namespaces_info(),
                self._get_pods_info(),
                self._get_deployments_info(),
                self._get_services_info(),
                self._get_configmaps_info(),
                self._get_secrets_info(),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            nodes_info = results[0] if not isinstance(results[0], Exception) else {}
            namespaces_count = (
                results[1] if not isinstance(results[1], Exception) else 0
            )
            pods_info = results[2] if not isinstance(results[2], Exception) else {}
            deployments_count = (
                results[3] if not isinstance(results[3], Exception) else 0
            )
            services_count = results[4] if not isinstance(results[4], Exception) else 0
            configmaps_count = (
                results[5] if not isinstance(results[5], Exception) else 0
            )
            secrets_count = results[6] if not isinstance(results[6], Exception) else 0

            # 构建概览数据 - 按类别组织
            overview = ResourceOverview(
                nodes={
                    "total": nodes_info.get("total", 0),
                    "ready": nodes_info.get("ready", 0),
                    "not_ready": nodes_info.get("not_ready", 0),
                },
                workloads={
                    "pods": {
                        "total": pods_info.get("total", 0),
                        "running": pods_info.get("running", 0),
                        "pending": pods_info.get("pending", 0),
                        "failed": pods_info.get("failed", 0),
                        "succeeded": pods_info.get("succeeded", 0),
                    },
                    "deployments": deployments_count,
                },
                discovery={
                    "services": services_count,
                },
                configs={
                    "configmaps": configmaps_count,
                    "secrets": secrets_count,
                    "namespaces": namespaces_count,
                },
                resources={
                    "cpu_requests": pods_info.get("cpu_requests", 0.0),
                    "memory_requests": pods_info.get("memory_requests", 0.0),
                    "cpu_limits": pods_info.get("cpu_limits", 0.0),
                    "memory_limits": pods_info.get("memory_limits", 0.0),
                },
                metadata={"last_updated": datetime.now()},
            )

            # 更新缓存
            self._overview_cache = overview
            self._overview_cache_time = datetime.now()

            elapsed_time = time.time() - start_time
            self.logger.info(
                "[获取集群资源概览][{%s}]资源概览数据收集完成，耗时: %.2f秒",
                cluster_name,
                elapsed_time,
            )

            return overview

        except Exception as e:
            self.logger.error(
                "[获取集群资源概览][{%s}]获取资源概览失败: %s", cluster_name, e
            )
            # 如果有缓存数据，返回缓存
            if self._overview_cache:
                self.logger.warning(
                    "[获取集群资源概览][{%s}]使用过期的缓存数据", cluster_name
                )
                return self._overview_cache
            raise

    async def _get_nodes_info(self) -> Dict[str, int]:
        """获取节点信息"""
        try:
            nodes = self.v1.list_node()
            total = len(nodes.items)
            ready = 0

            for node in nodes.items:
                if node.status.conditions:
                    for condition in node.status.conditions:
                        if condition.type == "Ready" and condition.status == "True":
                            ready += 1
                            break

            return {"total": total, "ready": ready, "not_ready": total - ready}
        except Exception as e:
            self.logger.error("获取节点信息失败: %s", e)
            return {}

    async def _get_namespaces_info(self) -> int:
        """获取命名空间数量"""
        try:
            namespaces = self.v1.list_namespace()
            return len(namespaces.items)
        except Exception as e:
            self.logger.error("获取命名空间信息失败: %s", e)
            return 0

    async def _get_pods_info(self) -> Dict[str, Any]:
        """获取Pod信息和资源统计"""
        try:
            pods = self.v1.list_pod_for_all_namespaces()
            total = len(pods.items)

            # 状态统计
            status_count = {"running": 0, "pending": 0, "failed": 0, "succeeded": 0}

            # 资源统计
            cpu_requests = 0.0
            memory_requests = 0.0
            cpu_limits = 0.0
            memory_limits = 0.0

            for pod in pods.items:
                # 统计状态
                phase = pod.status.phase.lower() if pod.status.phase else "unknown"
                if phase in status_count:
                    status_count[phase] += 1

                # 统计资源请求和限制
                if pod.spec.containers:
                    for container in pod.spec.containers:
                        if container.resources:
                            # CPU请求
                            if (
                                container.resources.requests
                                and "cpu" in container.resources.requests
                            ):
                                cpu_requests += self._parse_cpu(
                                    container.resources.requests["cpu"]
                                )

                            # 内存请求
                            if (
                                container.resources.requests
                                and "memory" in container.resources.requests
                            ):
                                memory_requests += self._parse_memory(
                                    container.resources.requests["memory"]
                                )

                            # CPU限制
                            if (
                                container.resources.limits
                                and "cpu" in container.resources.limits
                            ):
                                cpu_limits += self._parse_cpu(
                                    container.resources.limits["cpu"]
                                )

                            # 内存限制
                            if (
                                container.resources.limits
                                and "memory" in container.resources.limits
                            ):
                                memory_limits += self._parse_memory(
                                    container.resources.limits["memory"]
                                )

            return {
                "total": total,
                **status_count,
                "cpu_requests": cpu_requests,
                "memory_requests": memory_requests,
                "cpu_limits": cpu_limits,
                "memory_limits": memory_limits,
            }
        except Exception as e:
            self.logger.error("获取Pod信息失败: %s", e)
            return {}

    async def _get_deployments_info(self) -> int:
        """获取Deployment数量"""
        try:
            deployments = self.apps_v1.list_deployment_for_all_namespaces()
            return len(deployments.items)
        except Exception as e:
            self.logger.error("获取Deployment信息失败: %s", e)
            return 0

    async def _get_services_info(self) -> int:
        """获取Service数量"""
        try:
            services = self.v1.list_service_for_all_namespaces()
            return len(services.items)
        except Exception as e:
            self.logger.error("获取Service信息失败: %s", e)
            return 0

    async def _get_configmaps_info(self) -> int:
        """获取ConfigMap数量"""
        try:
            configmaps = self.v1.list_config_map_for_all_namespaces()
            return len(configmaps.items)
        except Exception as e:
            self.logger.error("获取ConfigMap信息失败: %s", e)
            return 0

    async def _get_secrets_info(self) -> int:
        """获取Secret数量"""
        try:
            secrets = self.v1.list_secret_for_all_namespaces()
            return len(secrets.items)
        except Exception as e:
            self.logger.error("获取Secret信息失败: %s", e)
            return 0

    def _parse_cpu(self, cpu_str: str) -> float:
        """解析CPU资源字符串为核心数"""
        try:
            if cpu_str.endswith("m"):
                return float(cpu_str[:-1]) / 1000
            else:
                return float(cpu_str)
        except:
            return 0.0

    def _parse_memory(self, memory_str: str) -> float:
        """解析内存资源字符串为GB"""
        try:
            memory_str = memory_str.upper()
            if memory_str.endswith("KI"):
                return float(memory_str[:-2]) / (1024 * 1024)
            elif memory_str.endswith("MI"):
                return float(memory_str[:-2]) / 1024
            elif memory_str.endswith("GI"):
                return float(memory_str[:-2])
            elif memory_str.endswith("K"):
                return float(memory_str[:-1]) / (1000 * 1000)
            elif memory_str.endswith("M"):
                return float(memory_str[:-1]) / 1000
            elif memory_str.endswith("G"):
                return float(memory_str[:-1])
            else:
                return float(memory_str) / (1024 * 1024 * 1024)
        except Exception:
            return 0.0

    async def get_namespaces_detail(
        self, force_refresh: bool = False
    ) -> List[NamespaceDetail]:
        """
        获取命名空间详细信息

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            List[NamespaceDetail]: 命名空间详细信息列表
        """
        if (
            not force_refresh
            and self._is_cache_valid(self._namespaces_cache_time)
            and self._namespaces_cache
        ):
            self.logger.debug("使用缓存的命名空间数据")
            return self._namespaces_cache

        self.logger.info("开始收集命名空间详细信息...")

        try:
            # 获取所有命名空间
            namespaces = self.v1.list_namespace()
            namespace_details = []

            # 并发获取每个命名空间的详细信息
            tasks = []
            for ns in namespaces.items:
                tasks.append(self._get_namespace_detail(ns))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if not isinstance(result, Exception) and result:
                    namespace_details.append(result)

            # 更新缓存
            self._namespaces_cache = namespace_details
            self._namespaces_cache_time = datetime.now()

            self.logger.info(
                "命名空间详细信息收集完成，共 %d 个命名空间", len(namespace_details)
            )
            return namespace_details

        except Exception as e:
            self.logger.error("获取命名空间详细信息失败: %s", e)
            if self._namespaces_cache:
                return self._namespaces_cache
            raise

    async def _get_namespace_detail(self, namespace) -> Optional[NamespaceDetail]:
        """获取单个命名空间的详细信息"""
        try:
            ns_name = namespace.metadata.name

            # 并发获取该命名空间下的资源
            tasks = [
                self._count_pods_in_namespace(ns_name),
                self._count_deployments_in_namespace(ns_name),
                self._count_services_in_namespace(ns_name),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            pods_count = results[0] if not isinstance(results[0], Exception) else 0
            deployments_count = (
                results[1] if not isinstance(results[1], Exception) else 0
            )
            services_count = results[2] if not isinstance(results[2], Exception) else 0

            return NamespaceDetail(
                name=ns_name,
                status=namespace.status.phase if namespace.status.phase else "Unknown",
                pods=pods_count,
                deployments=deployments_count,
                services=services_count,
                created_at=namespace.metadata.creation_timestamp,
            )

        except Exception as e:
            self.logger.error(
                "获取命名空间 %s 详细信息失败: %s", namespace.metadata.name, e
            )
            return None

    async def _count_pods_in_namespace(self, namespace: str) -> int:
        """统计指定命名空间中的Pod数量"""
        try:
            pods = self.v1.list_namespaced_pod(namespace=namespace)
            return len(pods.items)
        except:
            return 0

    async def _count_deployments_in_namespace(self, namespace: str) -> int:
        """统计指定命名空间中的Deployment数量"""
        try:
            deployments = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            return len(deployments.items)
        except:
            return 0

    async def _count_services_in_namespace(self, namespace: str) -> int:
        """统计指定命名空间中的Service数量"""
        try:
            services = self.v1.list_namespaced_service(namespace=namespace)
            return len(services.items)
        except:
            return 0

    async def get_nodes_detail(self, force_refresh: bool = False) -> List[NodeDetail]:
        """
        获取节点详细信息

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            List[NodeDetail]: 节点详细信息列表
        """
        if (
            not force_refresh
            and self._is_cache_valid(self._nodes_cache_time)
            and self._nodes_cache
        ):
            self.logger.debug("使用缓存的节点数据")
            return self._nodes_cache

        self.logger.info("开始收集节点详细信息...")

        try:
            nodes = self.v1.list_node()
            node_details = []

            for node in nodes.items:
                try:
                    # 获取节点状态
                    status = "NotReady"
                    if node.status.conditions:
                        for condition in node.status.conditions:
                            if condition.type == "Ready" and condition.status == "True":
                                status = "Ready"
                                break

                    # 获取节点角色
                    roles = []
                    if node.metadata.labels:
                        for label_key in node.metadata.labels:
                            if label_key.startswith("node-role.kubernetes.io/"):
                                role = label_key.split("/")[-1]
                                if role:
                                    roles.append(role)

                    if not roles:
                        roles = ["worker"]

                    # 获取节点信息
                    node_info = node.status.node_info

                    # 获取资源容量和可分配量
                    capacity = node.status.capacity or {}
                    allocatable = node.status.allocatable or {}

                    node_detail = NodeDetail(
                        name=node.metadata.name,
                        status=status,
                        roles=roles,
                        version=node_info.kubelet_version if node_info else "Unknown",
                        os_image=node_info.os_image if node_info else "Unknown",
                        kernel_version=(
                            node_info.kernel_version if node_info else "Unknown"
                        ),
                        container_runtime=(
                            node_info.container_runtime_version
                            if node_info
                            else "Unknown"
                        ),
                        cpu_capacity=capacity.get("cpu", "Unknown"),
                        memory_capacity=capacity.get("memory", "Unknown"),
                        pods_capacity=capacity.get("pods", "Unknown"),
                        cpu_allocatable=allocatable.get("cpu", "Unknown"),
                        memory_allocatable=allocatable.get("memory", "Unknown"),
                        pods_allocatable=allocatable.get("pods", "Unknown"),
                        created_at=node.metadata.creation_timestamp,
                    )

                    node_details.append(node_detail)

                except Exception as e:
                    self.logger.error("处理节点 %s 信息失败: %s", node.metadata.name, e)
                    continue

            # 更新缓存
            self._nodes_cache = node_details
            self._nodes_cache_time = datetime.now()

            self.logger.info("节点详细信息收集完成，共 %d 个节点", len(node_details))
            return node_details

        except Exception as e:
            self.logger.error("获取节点详细信息失败: %s", e)
            if self._nodes_cache:
                return self._nodes_cache
            raise

    def to_dict(self, obj) -> Dict:
        """将数据类转换为字典"""
        if hasattr(obj, "__dict__"):
            result = {}
            for key, value in obj.__dict__.items():
                if isinstance(value, datetime):
                    result[key] = value.isoformat() if value else None
                elif isinstance(value, list):
                    result[key] = [
                        self.to_dict(item) if hasattr(item, "__dict__") else item
                        for item in value
                    ]
                else:
                    result[key] = value
            return result
        return obj
