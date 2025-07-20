# -*- coding: utf-8 -*-
"""
K8s工具模块
提供通用的K8s操作和时间戳处理功能
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Union
import logging
import re

from kubernetes import client
from kubernetes.dynamic import DynamicClient


class K8sUtils:
    """K8s工具类，提供通用操作和时间戳处理"""

    def __init__(self, dynamic_client: DynamicClient):
        """
        初始化K8s工具类

        Args:
            dynamic_client: Kubernetes动态客户端
        """
        self.dynamic_client = dynamic_client
        self.logger = logging.getLogger("cloudpilot.K8sUtils")

        # 初始化API客户端
        self.v1 = client.CoreV1Api(self.dynamic_client.client)
        self.apps_v1 = client.AppsV1Api(self.dynamic_client.client)

    async def get_resource_events(
        self,
        resource_type: str,
        resource_name: str,
        namespace: Optional[str] = None,
        since_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取指定资源的事件

        Args:
            resource_type: 资源类型 (Pod, Deployment, Service等)
            resource_name: 资源名称
            namespace: 命名空间，None表示集群级别
            since_time: 开始时间
            limit: 事件数量限制

        Returns:
            List[Dict]: 事件列表
        """
        try:
            events = []

            if namespace:
                # 命名空间级别事件
                event_list = self.v1.list_namespaced_event(
                    namespace=namespace, limit=limit
                )
            else:
                # 集群级别事件
                event_list = self.v1.list_event_for_all_namespaces(limit=limit)

            for event in event_list.items:
                # 过滤指定资源的事件
                if (
                    event.involved_object.kind.lower() == resource_type.lower()
                    and event.involved_object.name == resource_name
                ):

                    event_time = event.first_timestamp or event.event_time

                    # 时间过滤
                    if since_time and event_time and event_time < since_time:
                        continue

                    event_data = {
                        "type": event.type,
                        "reason": event.reason,
                        "message": event.message,
                        "count": event.count or 1,
                        "first_timestamp": self.format_timestamp(event.first_timestamp),
                        "last_timestamp": self.format_timestamp(event.last_timestamp),
                        "source": {
                            "component": (
                                event.source.component if event.source else None
                            ),
                            "host": event.source.host if event.source else None,
                        },
                        "involved_object": {
                            "kind": event.involved_object.kind,
                            "name": event.involved_object.name,
                            "namespace": event.involved_object.namespace,
                            "uid": event.involved_object.uid,
                        },
                    }

                    events.append(event_data)

            # 按时间倒序排列
            events.sort(
                key=lambda x: x["last_timestamp"] or x["first_timestamp"], reverse=True
            )

            return events

        except Exception as e:
            self.logger.error(f"获取资源事件失败: {e}")
            return []

    async def get_namespace_events(
        self,
        namespace: str,
        since_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取命名空间级别的事件

        Args:
            namespace: 命名空间
            since_time: 开始时间
            event_types: 事件类型过滤 (Normal, Warning)
            limit: 事件数量限制

        Returns:
            List[Dict]: 事件列表
        """
        try:
            event_list = self.v1.list_namespaced_event(namespace=namespace, limit=limit)

            events = []
            for event in event_list.items:
                event_time = event.first_timestamp or event.event_time

                # 时间过滤
                if since_time and event_time and event_time < since_time:
                    continue

                # 事件类型过滤
                if event_types and event.type not in event_types:
                    continue

                event_data = {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "count": event.count or 1,
                    "first_timestamp": self.format_timestamp(event.first_timestamp),
                    "last_timestamp": self.format_timestamp(event.last_timestamp),
                    "source": {
                        "component": event.source.component if event.source else None,
                        "host": event.source.host if event.source else None,
                    },
                    "involved_object": {
                        "kind": event.involved_object.kind,
                        "name": event.involved_object.name,
                        "namespace": event.involved_object.namespace,
                        "uid": event.involved_object.uid,
                    },
                }

                events.append(event_data)

            # 按时间倒序排列
            events.sort(
                key=lambda x: x["last_timestamp"] or x["first_timestamp"], reverse=True
            )

            return events

        except Exception as e:
            self.logger.error(f"获取命名空间事件失败: {e}")
            return []

    async def get_cluster_events(
        self,
        since_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取集群级别的事件

        Args:
            since_time: 开始时间
            event_types: 事件类型过滤
            limit: 事件数量限制

        Returns:
            List[Dict]: 事件列表
        """
        try:
            event_list = self.v1.list_event_for_all_namespaces(limit=limit)

            events = []
            for event in event_list.items:
                event_time = event.first_timestamp or event.event_time

                # 时间过滤
                if since_time and event_time and event_time < since_time:
                    continue

                # 事件类型过滤
                if event_types and event.type not in event_types:
                    continue

                event_data = {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "count": event.count or 1,
                    "first_timestamp": self.format_timestamp(event.first_timestamp),
                    "last_timestamp": self.format_timestamp(event.last_timestamp),
                    "source": {
                        "component": event.source.component if event.source else None,
                        "host": event.source.host if event.source else None,
                    },
                    "involved_object": {
                        "kind": event.involved_object.kind,
                        "name": event.involved_object.name,
                        "namespace": event.involved_object.namespace,
                        "uid": event.involved_object.uid,
                    },
                }

                events.append(event_data)

            # 按时间倒序排列
            events.sort(
                key=lambda x: x["last_timestamp"] or x["first_timestamp"], reverse=True
            )

            return events

        except Exception as e:
            self.logger.error(f"获取集群事件失败: {e}")
            return []

    def format_timestamp(self, timestamp: Optional[datetime]) -> Optional[str]:
        """
        格式化时间戳为标准ISO格式

        Args:
            timestamp: 时间戳对象

        Returns:
            str: ISO格式的时间字符串，如果输入为None则返回None
        """
        if timestamp is None:
            return None

        try:
            # 确保时间戳有时区信息
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            return timestamp.isoformat()
        except Exception as e:
            self.logger.warning(f"格式化时间戳失败: {e}")
            return None

    def parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """
        解析时间戳字符串为datetime对象

        Args:
            timestamp_str: 时间戳字符串

        Returns:
            datetime: 解析后的时间对象
        """
        if not timestamp_str:
            return None

        try:
            # 尝试解析ISO格式
            if "T" in timestamp_str:
                return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                # 尝试其他常见格式
                return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            self.logger.warning(f"解析时间戳失败: {timestamp_str}, 错误: {e}")
            return None

    def calculate_age(self, creation_timestamp: Optional[datetime]) -> str:
        """
        计算资源年龄

        Args:
            creation_timestamp: 创建时间戳

        Returns:
            str: 年龄描述，如 "2d", "3h", "45m"
        """
        if not creation_timestamp:
            return "Unknown"

        try:
            # 确保时间戳有时区信息
            if creation_timestamp.tzinfo is None:
                creation_timestamp = creation_timestamp.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            age = now - creation_timestamp

            days = age.days
            hours, remainder = divmod(age.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            if days > 0:
                return f"{days}d"
            elif hours > 0:
                return f"{hours}h"
            elif minutes > 0:
                return f"{minutes}m"
            else:
                return "< 1m"

        except Exception as e:
            self.logger.warning(f"计算年龄失败: {e}")
            return "Unknown"

    def build_resource_relationships(
        self, resource: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        构建资源关系映射

        Args:
            resource: 资源对象

        Returns:
            Dict: 资源关系映射
        """
        relationships = {"owns": [], "owned_by": [], "selects": [], "selected_by": []}

        try:
            # 处理所有者引用
            owner_refs = resource.get("metadata", {}).get("ownerReferences", [])
            for owner in owner_refs:
                relationships["owned_by"].append(
                    f"{owner.get('kind')}/{owner.get('name')}"
                )

            # 处理标签选择器
            spec = resource.get("spec", {})
            if "selector" in spec:
                selector = spec["selector"]
                if "matchLabels" in selector:
                    relationships["selects"].append("通过标签选择器关联的资源")

            # 处理服务选择器
            if resource.get("kind") == "Service" and "selector" in spec:
                relationships["selects"].append("匹配标签的Pod")

        except Exception as e:
            self.logger.warning(f"构建资源关系失败: {e}")

        return relationships

    async def check_resource_health(
        self, resource_type: str, resource_name: str, namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        检查资源健康状态

        Args:
            resource_type: 资源类型
            resource_name: 资源名称
            namespace: 命名空间

        Returns:
            Dict: 健康状态信息
        """
        health_info = {
            "healthy": True,
            "issues": [],
            "warnings": [],
            "score": 100.0,  # 健康分数 0-100
        }

        try:
            # 获取最近的事件
            events = await self.get_resource_events(
                resource_type,
                resource_name,
                namespace,
                since_time=datetime.now(timezone.utc) - timedelta(hours=1),
            )

            # 分析事件
            warning_events = [e for e in events if e["type"] == "Warning"]
            error_patterns = ["Failed", "Error", "Unhealthy", "BackOff"]

            for event in warning_events:
                health_info["healthy"] = False
                health_info["issues"].append(f"{event['reason']}: {event['message']}")

                # 根据事件严重程度扣分
                if any(pattern in event["reason"] for pattern in error_patterns):
                    health_info["score"] -= 20
                else:
                    health_info["score"] -= 10

            # 确保分数不低于0
            health_info["score"] = max(0, health_info["score"])

        except Exception as e:
            self.logger.error(f"检查资源健康状态失败: {e}")
            health_info["issues"].append(f"健康检查失败: {e}")
            health_info["healthy"] = False
            health_info["score"] = 0

        return health_info

    def extract_labels_and_annotations(
        self, resource: Dict[str, Any]
    ) -> Dict[str, Dict[str, str]]:
        """
        提取资源的标签和注解

        Args:
            resource: 资源对象

        Returns:
            Dict: 包含labels和annotations的字典
        """
        metadata = resource.get("metadata", {})

        return {
            "labels": metadata.get("labels", {}),
            "annotations": metadata.get("annotations", {}),
        }

    def filter_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        过滤敏感数据

        Args:
            data: 原始数据

        Returns:
            Dict: 过滤后的数据
        """
        sensitive_keys = [
            "password",
            "token",
            "key",
            "secret",
            "cert",
            "certificate",
            "private",
            "auth",
            "credential",
            "api_key",
            "access_key",
        ]

        def filter_dict(obj):
            if isinstance(obj, dict):
                filtered = {}
                for k, v in obj.items():
                    key_lower = k.lower()
                    if any(sensitive in key_lower for sensitive in sensitive_keys):
                        filtered[k] = "[REDACTED]"
                    else:
                        filtered[k] = filter_dict(v)
                return filtered
            elif isinstance(obj, list):
                return [filter_dict(item) for item in obj]
            else:
                return obj

        return filter_dict(data)

    def validate_resource_name(self, name: str) -> bool:
        """
        验证K8s资源名称是否符合规范

        Args:
            name: 资源名称

        Returns:
            bool: 是否有效
        """
        if not name:
            return False

        # K8s资源名称规则：
        # - 长度不超过253个字符
        # - 只能包含小写字母、数字、连字符和点
        # - 必须以字母或数字开头和结尾
        pattern = r"^[a-z0-9]([a-z0-9\-\.]*[a-z0-9])?$"

        return len(name) <= 253 and bool(re.match(pattern, name))

    def validate_namespace_name(self, namespace: str) -> bool:
        """
        验证命名空间名称是否符合规范

        Args:
            namespace: 命名空间名称

        Returns:
            bool: 是否有效
        """
        if not namespace:
            return False

        # 命名空间名称规则更严格：
        # - 长度不超过63个字符
        # - 只能包含小写字母、数字和连字符
        # - 必须以字母或数字开头和结尾
        pattern = r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$"

        return len(namespace) <= 63 and bool(re.match(pattern, namespace))

    async def get_resource_logs(
        self,
        pod_name: str,
        namespace: str,
        container_name: Optional[str] = None,
        since_time: Optional[datetime] = None,
        tail_lines: Optional[int] = None,
        previous: bool = False,
    ) -> Dict[str, Any]:
        """
        获取Pod日志

        Args:
            pod_name: Pod名称
            namespace: 命名空间
            container_name: 容器名称
            since_time: 开始时间
            tail_lines: 尾部行数
            previous: 是否获取前一个容器实例的日志

        Returns:
            Dict: 日志信息
        """
        try:
            kwargs = {
                "name": pod_name,
                "namespace": namespace,
                "timestamps": True,
                "previous": previous,
            }

            if container_name:
                kwargs["container"] = container_name

            if since_time:
                kwargs["since_seconds"] = int(
                    (datetime.now(timezone.utc) - since_time).total_seconds()
                )

            if tail_lines:
                kwargs["tail_lines"] = tail_lines

            log_content = self.v1.read_namespaced_pod_log(**kwargs)

            return {
                "success": True,
                "logs": log_content,
                "pod_name": pod_name,
                "namespace": namespace,
                "container_name": container_name,
                "previous": previous,
                "timestamp": self.format_timestamp(datetime.now(timezone.utc)),
            }

        except Exception as e:
            self.logger.error(f"获取Pod日志失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "pod_name": pod_name,
                "namespace": namespace,
                "container_name": container_name,
                "previous": previous,
            }
