# -*- coding: utf-8 -*-
"""
Istio缓存管理器
提供统一的缓存管理、监控和优化功能
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.core.resource_cache import get_resource_cache, CacheConfig
from src.modes.istio.utils.cache_utils import (
    invalidate_istio_cache,
    get_istio_cache_stats,
    warm_istio_cache,
    optimize_cache_performance,
    cascade_invalidate_cache,
    smart_cache_refresh,
)


@dataclass
class CacheHealthMetrics:
    """缓存健康指标"""

    hit_rate: float
    miss_rate: float
    total_entries: int
    expired_entries: int
    memory_usage_mb: float
    avg_response_time_ms: float
    error_rate: float
    last_cleanup_time: Optional[datetime] = None


@dataclass
class CacheOperationResult:
    """缓存操作结果"""

    success: bool
    operation: str
    cluster_name: str
    resource_type: str
    execution_time_ms: float
    error_message: Optional[str] = None
    cache_hit: bool = False


class IstioCacheManager:
    """Istio缓存管理器"""

    def __init__(self, config: Optional[CacheConfig] = None):
        """
        初始化Istio缓存管理器

        Args:
            config: 缓存配置
        """
        self.config = config or CacheConfig()
        self.logger = logging.getLogger("cloudpilot.istio_cache_manager")
        self.cache = get_resource_cache()

        # 操作统计
        self.operation_stats: Dict[str, List[CacheOperationResult]] = {}

        # 后台任务
        self.background_tasks: Dict[str, asyncio.Task] = {}

        # 缓存健康监控
        self.health_check_interval = 300  # 5分钟
        self.cleanup_interval = 600  # 10分钟

    async def start_background_tasks(self):
        """启动后台任务"""
        try:
            # 启动健康检查任务
            if "health_check" not in self.background_tasks:
                self.background_tasks["health_check"] = asyncio.create_task(
                    self._health_check_loop()
                )

            # 启动清理任务
            if "cleanup" not in self.background_tasks:
                self.background_tasks["cleanup"] = asyncio.create_task(
                    self._cleanup_loop()
                )

            self.logger.info("[Istio缓存管理器]后台任务已启动")

        except Exception as e:
            self.logger.error("[Istio缓存管理器]启动后台任务失败: %s", str(e))

    async def stop_background_tasks(self):
        """停止后台任务"""
        try:
            for task_name, task in self.background_tasks.items():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            self.background_tasks.clear()
            self.logger.info("[Istio缓存管理器]后台任务已停止")

        except Exception as e:
            self.logger.error("[Istio缓存管理器]停止后台任务失败: %s", str(e))

    async def get_cache_health(self, cluster_name: str) -> CacheHealthMetrics:
        """
        获取缓存健康指标

        Args:
            cluster_name: 集群名称

        Returns:
            CacheHealthMetrics: 缓存健康指标
        """
        try:
            stats = await get_istio_cache_stats(cluster_name)

            # 计算指标
            total_requests = stats.get("total_hits", 0) + stats.get("total_misses", 0)
            hit_rate = stats.get("hit_rate", 0.0)
            miss_rate = 100.0 - hit_rate if total_requests > 0 else 0.0

            # 估算内存使用（简化计算）
            total_entries = stats.get("total_entries", 0)
            estimated_memory_mb = total_entries * 0.001  # 假设每个条目1KB

            # 计算平均响应时间（从操作统计中获取）
            avg_response_time = self._calculate_avg_response_time(cluster_name)

            # 计算错误率
            error_rate = self._calculate_error_rate(cluster_name)

            return CacheHealthMetrics(
                hit_rate=hit_rate,
                miss_rate=miss_rate,
                total_entries=total_entries,
                expired_entries=0,  # 需要从缓存系统获取
                memory_usage_mb=estimated_memory_mb,
                avg_response_time_ms=avg_response_time,
                error_rate=error_rate,
                last_cleanup_time=datetime.now(),
            )

        except Exception as e:
            self.logger.error(
                "[Istio缓存管理器][%s]获取缓存健康指标失败: %s",
                cluster_name,
                str(e),
            )
            return CacheHealthMetrics(
                hit_rate=0.0,
                miss_rate=100.0,
                total_entries=0,
                expired_entries=0,
                memory_usage_mb=0.0,
                avg_response_time_ms=0.0,
                error_rate=100.0,
            )

    async def warm_cluster_cache(
        self,
        cluster_name: str,
        resource_types: Optional[List[str]] = None,
        namespaces: Optional[List[str]] = None,
        priority_resources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        预热集群缓存

        Args:
            cluster_name: 集群名称
            resource_types: 资源类型列表
            namespaces: 命名空间列表
            priority_resources: 优先预热的资源类型

        Returns:
            Dict[str, Any]: 预热结果
        """
        start_time = datetime.now()

        try:
            self.logger.info("[Istio缓存管理器][%s]开始预热缓存", cluster_name)

            # 优先预热重要资源
            if priority_resources:
                priority_result = await warm_istio_cache(
                    cluster_name, priority_resources, namespaces
                )
                self.logger.info(
                    "[Istio缓存管理器][%s]优先资源预热完成: %s",
                    cluster_name,
                    priority_result,
                )

            # 预热其他资源
            main_result = await warm_istio_cache(
                cluster_name, resource_types, namespaces
            )

            execution_time = (datetime.now() - start_time).total_seconds()

            result = {
                "cluster_name": cluster_name,
                "execution_time_seconds": execution_time,
                "priority_warm_result": priority_result if priority_resources else None,
                "main_warm_result": main_result,
                "total_resources_warmed": main_result.get("successful_warm", 0),
                "failed_resources": main_result.get("failed_warm", 0),
            }

            self.logger.info(
                "[Istio缓存管理器][%s]缓存预热完成，耗时: %.2f秒",
                cluster_name,
                execution_time,
            )

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            self.logger.error(
                "[Istio缓存管理器][%s]缓存预热失败，耗时: %.2f秒, 错误: %s",
                cluster_name,
                execution_time,
                str(e),
            )
            return {
                "cluster_name": cluster_name,
                "execution_time_seconds": execution_time,
                "error": str(e),
                "total_resources_warmed": 0,
                "failed_resources": 0,
            }

    async def invalidate_cluster_cache(
        self,
        cluster_name: str,
        resource_type: Optional[str] = None,
        cascade: bool = True,
    ) -> Dict[str, Any]:
        """
        失效集群缓存

        Args:
            cluster_name: 集群名称
            resource_type: 资源类型，为None则清除所有缓存
            cascade: 是否级联失效相关资源

        Returns:
            Dict[str, Any]: 失效结果
        """
        start_time = datetime.now()

        try:
            self.logger.info(
                "[Istio缓存管理器][%s]开始失效缓存，资源类型: %s, 级联: %s",
                cluster_name,
                resource_type or "all",
                cascade,
            )

            # 失效指定资源缓存
            await invalidate_istio_cache(cluster_name, resource_type)

            # 级联失效相关资源
            if cascade and resource_type:
                await cascade_invalidate_cache(cluster_name, resource_type)

            execution_time = (datetime.now() - start_time).total_seconds()

            result = {
                "cluster_name": cluster_name,
                "resource_type": resource_type or "all",
                "cascade": cascade,
                "execution_time_seconds": execution_time,
                "success": True,
            }

            self.logger.info(
                "[Istio缓存管理器][%s]缓存失效完成，耗时: %.2f秒",
                cluster_name,
                execution_time,
            )

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            self.logger.error(
                "[Istio缓存管理器][%s]缓存失效失败，耗时: %.2f秒, 错误: %s",
                cluster_name,
                execution_time,
                str(e),
            )
            return {
                "cluster_name": cluster_name,
                "resource_type": resource_type or "all",
                "cascade": cascade,
                "execution_time_seconds": execution_time,
                "success": False,
                "error": str(e),
            }

    async def optimize_cluster_cache(self, cluster_name: str) -> Dict[str, Any]:
        """
        优化集群缓存性能

        Args:
            cluster_name: 集群名称

        Returns:
            Dict[str, Any]: 优化结果
        """
        try:
            self.logger.info("[Istio缓存管理器][%s]开始优化缓存性能", cluster_name)

            # 执行缓存优化
            optimization_result = await optimize_cache_performance(cluster_name)

            # 获取优化后的健康指标
            health_metrics = await self.get_cache_health(cluster_name)

            result = {
                "cluster_name": cluster_name,
                "optimization_result": optimization_result,
                "health_metrics": health_metrics,
                "timestamp": datetime.now().isoformat(),
            }

            self.logger.info(
                "[Istio缓存管理器][%s]缓存性能优化完成，命中率: %.2f%%",
                cluster_name,
                health_metrics.hit_rate,
            )

            return result

        except Exception as e:
            self.logger.error(
                "[Istio缓存管理器][%s]缓存性能优化失败: %s",
                cluster_name,
                str(e),
            )
            return {
                "cluster_name": cluster_name,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def record_operation(self, result: CacheOperationResult):
        """
        记录缓存操作结果

        Args:
            result: 缓存操作结果
        """
        try:
            key = f"{result.cluster_name}:{result.resource_type}:{result.operation}"

            if key not in self.operation_stats:
                self.operation_stats[key] = []

            self.operation_stats[key].append(result)

            # 保持最近1000条记录
            if len(self.operation_stats[key]) > 1000:
                self.operation_stats[key] = self.operation_stats[key][-1000:]

        except Exception as e:
            self.logger.error("[Istio缓存管理器]记录操作统计失败: %s", str(e))

    def _calculate_avg_response_time(self, cluster_name: str) -> float:
        """计算平均响应时间"""
        try:
            total_time = 0.0
            total_count = 0

            for key, results in self.operation_stats.items():
                if cluster_name in key:
                    for result in results[-100:]:  # 最近100条记录
                        total_time += result.execution_time_ms
                        total_count += 1

            return total_time / total_count if total_count > 0 else 0.0

        except Exception:
            return 0.0

    def _calculate_error_rate(self, cluster_name: str) -> float:
        """计算错误率"""
        try:
            total_count = 0
            error_count = 0

            for key, results in self.operation_stats.items():
                if cluster_name in key:
                    for result in results[-100:]:  # 最近100条记录
                        total_count += 1
                        if not result.success:
                            error_count += 1

            return (error_count / total_count * 100) if total_count > 0 else 0.0

        except Exception:
            return 0.0

    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)

                # 这里可以添加健康检查逻辑
                # 例如检查缓存命中率、响应时间等
                self.logger.debug("[Istio缓存管理器]执行健康检查")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("[Istio缓存管理器]健康检查失败: %s", str(e))

    async def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)

                # 清理过期缓存
                await self.cache.cleanup_expired()

                # 清理旧的操作统计
                self._cleanup_old_stats()

                self.logger.debug("[Istio缓存管理器]执行清理任务")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("[Istio缓存管理器]清理任务失败: %s", str(e))

    def _cleanup_old_stats(self):
        """清理旧的操作统计"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)

            for key in list(self.operation_stats.keys()):
                # 保留最近24小时的统计
                self.operation_stats[key] = [
                    result
                    for result in self.operation_stats[key]
                    if datetime.now() - timedelta(milliseconds=result.execution_time_ms)
                    > cutoff_time
                ]

                # 如果没有记录，删除键
                if not self.operation_stats[key]:
                    del self.operation_stats[key]

        except Exception as e:
            self.logger.error("[Istio缓存管理器]清理统计数据失败: %s", str(e))


# 全局缓存管理器实例
_global_cache_manager: Optional[IstioCacheManager] = None


def get_istio_cache_manager() -> IstioCacheManager:
    """
    获取全局Istio缓存管理器实例

    Returns:
        IstioCacheManager: 全局缓存管理器实例
    """
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = IstioCacheManager()
    return _global_cache_manager


async def init_istio_cache_manager(config: Optional[CacheConfig] = None):
    """
    初始化Istio缓存管理器

    Args:
        config: 缓存配置
    """
    global _global_cache_manager
    _global_cache_manager = IstioCacheManager(config)
    await _global_cache_manager.start_background_tasks()


async def shutdown_istio_cache_manager():
    """关闭Istio缓存管理器"""
    global _global_cache_manager
    if _global_cache_manager:
        await _global_cache_manager.stop_background_tasks()
        _global_cache_manager = None
