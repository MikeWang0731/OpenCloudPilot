# -*- coding: utf-8 -*-
"""
资源缓存管理器
提供针对不同K8s资源类型的专用缓存功能
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import logging
import hashlib
import json


@dataclass
class CacheConfig:
    """缓存配置"""

    # 不同资源类型的TTL配置（秒）
    pod_list_ttl: int = 30
    pod_detail_ttl: int = 60
    deployment_list_ttl: int = 60
    deployment_detail_ttl: int = 90
    service_list_ttl: int = 60
    service_detail_ttl: int = 90
    node_list_ttl: int = 120
    node_detail_ttl: int = 180
    logs_ttl: int = 30
    events_ttl: int = 60

    # 缓存大小限制
    max_cache_entries: int = 1000

    # 是否启用缓存
    enable_caching: bool = True


@dataclass
class CacheEntry:
    """缓存条目"""

    data: Any
    timestamp: datetime
    ttl: int
    access_count: int = 0
    last_access: Optional[datetime] = None

    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now() - self.timestamp > timedelta(seconds=self.ttl)

    def touch(self):
        """更新访问时间和计数"""
        self.access_count += 1
        self.last_access = datetime.now()


class ResourceCache:
    """资源缓存管理器"""

    def __init__(self, config: Optional[CacheConfig] = None):
        """
        初始化资源缓存管理器

        Args:
            config: 缓存配置，如果为None则使用默认配置
        """
        self.config = config or CacheConfig()
        self.logger = logging.getLogger("cloudpilot.ResourceCache")

        # 缓存存储 - 使用嵌套字典结构: {cluster_name: {cache_key: CacheEntry}}
        self._cache: Dict[str, Dict[str, CacheEntry]] = {}

        # 缓存统计
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "total_entries": 0}

        # 锁用于并发控制
        self._lock = asyncio.Lock()

    def _generate_cache_key(self, resource_type: str, operation: str, **kwargs) -> str:
        """
        生成缓存键

        Args:
            resource_type: 资源类型 (pod, deployment, service, node, logs, events)
            operation: 操作类型 (list, detail, logs, events)
            **kwargs: 其他参数

        Returns:
            str: 缓存键
        """
        # 创建一个包含所有参数的字典
        params = {"resource_type": resource_type, "operation": operation, **kwargs}

        # 排序参数以确保一致性
        sorted_params = json.dumps(params, sort_keys=True, default=str)

        # 生成哈希
        return hashlib.md5(sorted_params.encode()).hexdigest()

    def _get_ttl_for_operation(self, resource_type: str, operation: str) -> int:
        """
        获取指定操作的TTL

        Args:
            resource_type: 资源类型
            operation: 操作类型

        Returns:
            int: TTL秒数
        """
        ttl_map = {
            ("pod", "list"): self.config.pod_list_ttl,
            ("pod", "detail"): self.config.pod_detail_ttl,
            ("deployment", "list"): self.config.deployment_list_ttl,
            ("deployment", "detail"): self.config.deployment_detail_ttl,
            ("service", "list"): self.config.service_list_ttl,
            ("service", "detail"): self.config.service_detail_ttl,
            ("node", "list"): self.config.node_list_ttl,
            ("node", "detail"): self.config.node_detail_ttl,
            ("logs", "retrieve"): self.config.logs_ttl,
            ("events", "retrieve"): self.config.events_ttl,
        }

        return ttl_map.get((resource_type, operation), 60)  # 默认60秒

    async def get(
        self, cluster_name: str, resource_type: str, operation: str, **kwargs
    ) -> Optional[Any]:
        """
        从缓存获取数据

        Args:
            cluster_name: 集群名称
            resource_type: 资源类型
            operation: 操作类型
            **kwargs: 其他参数

        Returns:
            Optional[Any]: 缓存的数据，如果不存在或过期则返回None
        """
        if not self.config.enable_caching:
            return None

        cache_key = self._generate_cache_key(resource_type, operation, **kwargs)

        async with self._lock:
            cluster_cache = self._cache.get(cluster_name, {})
            entry = cluster_cache.get(cache_key)

            if entry is None:
                self._stats["misses"] += 1
                return None

            if entry.is_expired():
                # 删除过期条目
                del cluster_cache[cache_key]
                if not cluster_cache:
                    del self._cache[cluster_name]
                self._stats["misses"] += 1
                self._stats["evictions"] += 1
                self.logger.debug(
                    "[资源缓存][%s]缓存条目已过期: %s/%s",
                    cluster_name,
                    resource_type,
                    operation,
                )
                return None

            # 更新访问信息
            entry.touch()
            self._stats["hits"] += 1

            self.logger.debug(
                "[资源缓存][%s]缓存命中: %s/%s", cluster_name, resource_type, operation
            )
            return entry.data

    async def set(
        self, cluster_name: str, resource_type: str, operation: str, data: Any, **kwargs
    ):
        """
        设置缓存数据

        Args:
            cluster_name: 集群名称
            resource_type: 资源类型
            operation: 操作类型
            data: 要缓存的数据
            **kwargs: 其他参数
        """
        if not self.config.enable_caching:
            return

        cache_key = self._generate_cache_key(resource_type, operation, **kwargs)
        ttl = self._get_ttl_for_operation(resource_type, operation)

        async with self._lock:
            # 确保集群缓存存在
            if cluster_name not in self._cache:
                self._cache[cluster_name] = {}

            cluster_cache = self._cache[cluster_name]

            # 检查缓存大小限制
            total_entries = sum(len(cache) for cache in self._cache.values())
            if total_entries >= self.config.max_cache_entries:
                await self._evict_lru_entries()

            # 创建缓存条目
            entry = CacheEntry(data=data, timestamp=datetime.now(), ttl=ttl)

            cluster_cache[cache_key] = entry
            self._stats["total_entries"] = sum(
                len(cache) for cache in self._cache.values()
            )

            self.logger.debug(
                "[资源缓存][%s]缓存已设置: %s/%s (TTL: %ds)",
                cluster_name,
                resource_type,
                operation,
                ttl,
            )

    async def invalidate(
        self,
        cluster_name: str,
        resource_type: Optional[str] = None,
        operation: Optional[str] = None,
    ):
        """
        使缓存失效

        Args:
            cluster_name: 集群名称
            resource_type: 资源类型，如果为None则清除该集群的所有缓存
            operation: 操作类型，如果为None则清除该资源类型的所有缓存
        """
        async with self._lock:
            if cluster_name not in self._cache:
                return

            cluster_cache = self._cache[cluster_name]

            if resource_type is None:
                # 清除整个集群的缓存
                cluster_cache.clear()
                self.logger.info("[资源缓存][%s]已清除所有缓存", cluster_name)
            else:
                # 清除特定资源类型的缓存
                keys_to_remove = []
                for cache_key, entry in cluster_cache.items():
                    # 这里需要解析缓存键来判断资源类型
                    # 简化处理：如果缓存键包含资源类型则删除
                    if resource_type in cache_key:
                        if operation is None or operation in cache_key:
                            keys_to_remove.append(cache_key)

                for key in keys_to_remove:
                    del cluster_cache[key]

                self.logger.info(
                    "[资源缓存][%s]已清除 %s 相关缓存 (%d 个条目)",
                    cluster_name,
                    resource_type,
                    len(keys_to_remove),
                )

            # 如果集群缓存为空，删除集群条目
            if not cluster_cache:
                del self._cache[cluster_name]

            self._stats["total_entries"] = sum(
                len(cache) for cache in self._cache.values()
            )

    async def _evict_lru_entries(self):
        """驱逐最少使用的缓存条目"""
        # 收集所有条目及其访问信息
        all_entries = []
        for cluster_name, cluster_cache in self._cache.items():
            for cache_key, entry in cluster_cache.items():
                all_entries.append((cluster_name, cache_key, entry))

        # 按访问时间排序（最少访问的在前）
        all_entries.sort(key=lambda x: (x[2].last_access or x[2].timestamp))

        # 删除最少使用的10%条目
        entries_to_remove = max(1, len(all_entries) // 10)

        for i in range(entries_to_remove):
            cluster_name, cache_key, _ = all_entries[i]
            if cluster_name in self._cache and cache_key in self._cache[cluster_name]:
                del self._cache[cluster_name][cache_key]
                if not self._cache[cluster_name]:
                    del self._cache[cluster_name]
                self._stats["evictions"] += 1

        self.logger.info("[资源缓存]已驱逐 %d 个LRU缓存条目", entries_to_remove)

    async def cleanup_expired(self):
        """清理过期的缓存条目"""
        async with self._lock:
            expired_count = 0
            clusters_to_remove = []

            for cluster_name, cluster_cache in self._cache.items():
                keys_to_remove = []

                for cache_key, entry in cluster_cache.items():
                    if entry.is_expired():
                        keys_to_remove.append(cache_key)

                for key in keys_to_remove:
                    del cluster_cache[key]
                    expired_count += 1

                if not cluster_cache:
                    clusters_to_remove.append(cluster_name)

            for cluster_name in clusters_to_remove:
                del self._cache[cluster_name]

            self._stats["total_entries"] = sum(
                len(cache) for cache in self._cache.values()
            )

            if expired_count > 0:
                self.logger.info("[资源缓存]已清理 %d 个过期缓存条目", expired_count)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            Dict[str, Any]: 缓存统计信息
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0

        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": round(hit_rate * 100, 2),
            "evictions": self._stats["evictions"],
            "total_entries": self._stats["total_entries"],
            "clusters_cached": len(self._cache),
            "config": {
                "max_cache_entries": self.config.max_cache_entries,
                "enable_caching": self.config.enable_caching,
                "ttl_config": {
                    "pod_list": self.config.pod_list_ttl,
                    "pod_detail": self.config.pod_detail_ttl,
                    "deployment_list": self.config.deployment_list_ttl,
                    "deployment_detail": self.config.deployment_detail_ttl,
                    "service_list": self.config.service_list_ttl,
                    "service_detail": self.config.service_detail_ttl,
                    "node_list": self.config.node_list_ttl,
                    "node_detail": self.config.node_detail_ttl,
                    "logs": self.config.logs_ttl,
                    "events": self.config.events_ttl,
                },
            },
        }

    async def clear_all(self):
        """清除所有缓存"""
        async with self._lock:
            self._cache.clear()
            self._stats = {"hits": 0, "misses": 0, "evictions": 0, "total_entries": 0}
            self.logger.info("[资源缓存]已清除所有缓存")


# 全局缓存实例
_global_cache: Optional[ResourceCache] = None


def get_resource_cache() -> ResourceCache:
    """
    获取全局资源缓存实例

    Returns:
        ResourceCache: 全局缓存实例
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = ResourceCache()
    return _global_cache


def init_resource_cache(config: Optional[CacheConfig] = None):
    """
    初始化全局资源缓存

    Args:
        config: 缓存配置
    """
    global _global_cache
    _global_cache = ResourceCache(config)
