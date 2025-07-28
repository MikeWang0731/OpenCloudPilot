# -*- coding: utf-8 -*-
"""
Istio异步操作优化工具
提供并发操作优化、请求批处理和性能监控功能
"""

import asyncio
import logging
import time
from typing import Any, List, Dict, Optional, Callable, Awaitable, Union
from dataclasses import dataclass
from collections import defaultdict
from functools import wraps

from src.core.async_utils import (
    async_timeout,
    monitor_performance,
    get_performance_monitor,
)


@dataclass
class BatchRequest:
    """批处理请求"""

    resource_type: str
    operation: str
    params: Dict[str, Any]
    callback: Optional[Callable] = None


@dataclass
class BatchResult:
    """批处理结果"""

    success: bool
    data: Any
    error: Optional[Exception] = None
    execution_time: float = 0.0


@dataclass
class PerformanceMetrics:
    """性能指标"""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    max_response_time: float = 0.0
    min_response_time: float = float("inf")
    concurrent_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


class RequestBatcher:
    """请求批处理器"""

    def __init__(self, batch_size: int = 10, batch_timeout: float = 1.0):
        """
        初始化请求批处理器

        Args:
            batch_size: 批处理大小
            batch_timeout: 批处理超时时间（秒）
        """
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.pending_requests: Dict[str, List[BatchRequest]] = defaultdict(list)
        self.batch_timers: Dict[str, asyncio.Task] = {}
        self.logger = logging.getLogger("cloudpilot.istio_async_optimizer")

    async def add_request(self, request: BatchRequest) -> BatchResult:
        """
        添加请求到批处理队列

        Args:
            request: 批处理请求

        Returns:
            BatchResult: 批处理结果
        """
        batch_key = f"{request.resource_type}:{request.operation}"

        # 添加到待处理队列
        self.pending_requests[batch_key].append(request)

        # 如果达到批处理大小，立即处理
        if len(self.pending_requests[batch_key]) >= self.batch_size:
            return await self._process_batch(batch_key)

        # 设置批处理定时器
        if batch_key not in self.batch_timers:
            self.batch_timers[batch_key] = asyncio.create_task(
                self._batch_timer(batch_key)
            )

        # 等待批处理完成
        return await self._wait_for_batch_completion(batch_key, request)

    async def _batch_timer(self, batch_key: str):
        """批处理定时器"""
        try:
            await asyncio.sleep(self.batch_timeout)
            if batch_key in self.pending_requests and self.pending_requests[batch_key]:
                await self._process_batch(batch_key)
        except asyncio.CancelledError:
            pass

    async def _process_batch(self, batch_key: str) -> BatchResult:
        """
        处理批处理请求

        Args:
            batch_key: 批处理键

        Returns:
            BatchResult: 批处理结果
        """
        if batch_key not in self.pending_requests:
            return BatchResult(
                success=False, data=None, error=Exception("Batch not found")
            )

        requests = self.pending_requests[batch_key]
        if not requests:
            return BatchResult(success=False, data=None, error=Exception("Empty batch"))

        # 清除待处理队列和定时器
        del self.pending_requests[batch_key]
        if batch_key in self.batch_timers:
            self.batch_timers[batch_key].cancel()
            del self.batch_timers[batch_key]

        start_time = time.time()

        try:
            # 并发执行所有请求
            tasks = []
            for request in requests:
                if request.callback:
                    task = asyncio.create_task(request.callback(request.params))
                    tasks.append(task)

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                execution_time = time.time() - start_time

                # 处理结果
                successful_results = []
                for result in results:
                    if isinstance(result, Exception):
                        self.logger.error(f"批处理请求失败: {str(result)}")
                    else:
                        successful_results.append(result)

                return BatchResult(
                    success=len(successful_results) > 0,
                    data=successful_results,
                    execution_time=execution_time,
                )
            else:
                return BatchResult(
                    success=False, data=None, error=Exception("No callbacks provided")
                )

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"批处理执行失败: {str(e)}")
            return BatchResult(
                success=False, data=None, error=e, execution_time=execution_time
            )

    async def _wait_for_batch_completion(
        self, batch_key: str, request: BatchRequest
    ) -> BatchResult:
        """等待批处理完成"""
        # 简化实现：直接执行单个请求
        if request.callback:
            start_time = time.time()
            try:
                result = await request.callback(request.params)
                execution_time = time.time() - start_time
                return BatchResult(
                    success=True, data=result, execution_time=execution_time
                )
            except Exception as e:
                execution_time = time.time() - start_time
                return BatchResult(
                    success=False, data=None, error=e, execution_time=execution_time
                )
        else:
            return BatchResult(
                success=False, data=None, error=Exception("No callback provided")
            )


class ConcurrentResourceFetcher:
    """并发资源获取器"""

    def __init__(self, max_concurrent: int = 10, rate_limit_delay: float = 0.1):
        """
        初始化并发资源获取器

        Args:
            max_concurrent: 最大并发数
            rate_limit_delay: 速率限制延迟（秒）
        """
        self.max_concurrent = max_concurrent
        self.rate_limit_delay = rate_limit_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.logger = logging.getLogger("cloudpilot.istio_concurrent_fetcher")
        self.metrics = PerformanceMetrics()

    async def fetch_resources(
        self, fetch_functions: List[Callable[[], Awaitable[Any]]], timeout: float = 30.0
    ) -> List[Any]:
        """
        并发获取多个资源

        Args:
            fetch_functions: 获取函数列表
            timeout: 超时时间

        Returns:
            List[Any]: 获取结果列表
        """
        start_time = time.time()
        self.metrics.total_requests += len(fetch_functions)

        try:
            # 创建并发任务
            tasks = []
            for fetch_func in fetch_functions:
                task = asyncio.create_task(self._fetch_with_semaphore(fetch_func))
                tasks.append(task)

            # 等待所有任务完成
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=timeout
            )

            # 处理结果
            successful_results = []
            for result in results:
                if isinstance(result, Exception):
                    self.metrics.failed_requests += 1
                    self.logger.error(f"资源获取失败: {str(result)}")
                else:
                    self.metrics.successful_requests += 1
                    successful_results.append(result)

            # 更新性能指标
            execution_time = time.time() - start_time
            self._update_metrics(execution_time)

            return successful_results

        except asyncio.TimeoutError:
            self.logger.error(f"并发资源获取超时: {timeout}秒")
            self.metrics.failed_requests += len(fetch_functions)
            return []
        except Exception as e:
            self.logger.error(f"并发资源获取失败: {str(e)}")
            self.metrics.failed_requests += len(fetch_functions)
            return []

    async def _fetch_with_semaphore(
        self, fetch_func: Callable[[], Awaitable[Any]]
    ) -> Any:
        """使用信号量控制并发的资源获取"""
        async with self.semaphore:
            self.metrics.concurrent_requests += 1
            try:
                # 添加速率限制延迟
                if self.rate_limit_delay > 0:
                    await asyncio.sleep(self.rate_limit_delay)

                result = await fetch_func()
                return result
            finally:
                self.metrics.concurrent_requests -= 1

    def _update_metrics(self, execution_time: float):
        """更新性能指标"""
        if execution_time > self.metrics.max_response_time:
            self.metrics.max_response_time = execution_time

        if execution_time < self.metrics.min_response_time:
            self.metrics.min_response_time = execution_time

        # 更新平均响应时间
        total_successful = self.metrics.successful_requests
        if total_successful > 0:
            self.metrics.average_response_time = (
                self.metrics.average_response_time * (total_successful - 1)
                + execution_time
            ) / total_successful

    def get_metrics(self) -> PerformanceMetrics:
        """获取性能指标"""
        return self.metrics

    def reset_metrics(self):
        """重置性能指标"""
        self.metrics = PerformanceMetrics()


class MemoryOptimizer:
    """内存优化器"""

    def __init__(self, max_object_size: int = 1024 * 1024):  # 1MB
        """
        初始化内存优化器

        Args:
            max_object_size: 最大对象大小（字节）
        """
        self.max_object_size = max_object_size
        self.logger = logging.getLogger("cloudpilot.istio_memory_optimizer")

    def optimize_large_object(self, obj: Any) -> Any:
        """
        优化大对象

        Args:
            obj: 要优化的对象

        Returns:
            Any: 优化后的对象
        """
        try:
            # 估算对象大小
            obj_size = self._estimate_object_size(obj)

            if obj_size > self.max_object_size:
                self.logger.warning(f"检测到大对象 ({obj_size} 字节)，进行优化")
                return self._compress_object(obj)

            return obj

        except Exception as e:
            self.logger.error(f"对象优化失败: {str(e)}")
            return obj

    def _estimate_object_size(self, obj: Any) -> int:
        """估算对象大小"""
        try:
            import sys

            return sys.getsizeof(obj)
        except Exception:
            return 0

    def _compress_object(self, obj: Any) -> Any:
        """压缩对象"""
        try:
            # 如果是字典，移除不必要的字段
            if isinstance(obj, dict):
                return self._compress_dict(obj)
            elif isinstance(obj, list):
                return self._compress_list(obj)
            else:
                return obj
        except Exception as e:
            self.logger.error(f"对象压缩失败: {str(e)}")
            return obj

    def _compress_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """压缩字典对象，针对Istio配置进行优化"""
        # 移除空值和不必要的字段
        compressed = {}

        # Istio特定的不必要字段
        istio_unnecessary_fields = {
            "managedFields",
            "resourceVersion",
            "generation",
            "selfLink",
            "creationTimestamp",
            "uid",
            "ownerReferences",
            "finalizers",
        }

        for key, value in data.items():
            # 跳过Istio不必要的字段
            if key in istio_unnecessary_fields:
                continue

            if value is not None and value != "" and value != []:
                if isinstance(value, dict):
                    compressed_value = self._compress_dict(value)
                    if compressed_value:
                        compressed[key] = compressed_value
                elif isinstance(value, list):
                    compressed_value = self._compress_list(value)
                    if compressed_value:
                        compressed[key] = compressed_value
                elif isinstance(value, str):
                    # 压缩长字符串
                    if len(value) > 1000:
                        compressed[key] = (
                            value[:500] + "...[truncated]..." + value[-500:]
                        )
                    else:
                        compressed[key] = value
                else:
                    compressed[key] = value

        return compressed

    def _compress_list(self, data: List[Any]) -> List[Any]:
        """压缩列表对象"""
        compressed = []
        for item in data:
            if item is not None:
                if isinstance(item, dict):
                    compressed_item = self._compress_dict(item)
                    if compressed_item:
                        compressed.append(compressed_item)
                elif isinstance(item, list):
                    compressed_item = self._compress_list(item)
                    if compressed_item:
                        compressed.append(compressed_item)
                else:
                    compressed.append(item)

        return compressed


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, slow_threshold: float = 5.0):
        """
        初始化性能监控器

        Args:
            slow_threshold: 慢操作阈值（秒）
        """
        self.slow_threshold = slow_threshold
        self.logger = logging.getLogger("cloudpilot.istio_performance_monitor")
        self.operation_stats: Dict[str, List[float]] = defaultdict(list)

    def monitor_operation(self, operation_name: str):
        """操作性能监控装饰器，支持详细的性能分析"""

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                cluster_name = kwargs.get("cluster_name", "unknown")
                memory_before = self._get_memory_usage()

                try:
                    result = await func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    memory_after = self._get_memory_usage()
                    memory_delta = memory_after - memory_before

                    # 记录操作统计
                    self.operation_stats[operation_name].append(execution_time)

                    # 详细的性能分析
                    performance_info = {
                        "execution_time": execution_time,
                        "memory_delta": memory_delta,
                        "result_size": self._estimate_result_size(result),
                    }

                    # 检查是否为慢操作
                    if execution_time > self.slow_threshold:
                        self.logger.warning(
                            f"[性能监控][{cluster_name}]慢操作检测: {operation_name} "
                            f"耗时 {execution_time:.2f}秒, 内存变化: {memory_delta:.2f}MB, "
                            f"结果大小: {performance_info['result_size']:.2f}KB"
                        )

                        # 生成性能优化建议
                        suggestions = self._generate_performance_suggestions(
                            performance_info
                        )
                        if suggestions:
                            self.logger.info(
                                f"[性能监控][{cluster_name}]优化建议: {operation_name} - {', '.join(suggestions)}"
                            )
                    else:
                        self.logger.debug(
                            f"[性能监控][{cluster_name}]操作完成: {operation_name} "
                            f"耗时 {execution_time:.2f}秒, 内存: {memory_delta:.2f}MB"
                        )

                    return result

                except Exception as e:
                    execution_time = time.time() - start_time
                    memory_after = self._get_memory_usage()
                    memory_delta = memory_after - memory_before

                    self.logger.error(
                        f"[性能监控][{cluster_name}]操作失败: {operation_name} "
                        f"耗时 {execution_time:.2f}秒, 内存变化: {memory_delta:.2f}MB, 错误: {str(e)}"
                    )
                    raise

            return wrapper

        return decorator

    def _get_memory_usage(self) -> float:
        """获取当前内存使用量（MB）"""
        try:
            import psutil

            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0
        except Exception:
            return 0.0

    def _estimate_result_size(self, result: Any) -> float:
        """估算结果大小（KB）"""
        try:
            import sys

            return sys.getsizeof(result) / 1024
        except Exception:
            return 0.0

    def _generate_performance_suggestions(
        self, performance_info: Dict[str, Any]
    ) -> List[str]:
        """生成性能优化建议"""
        suggestions = []

        execution_time = performance_info.get("execution_time", 0)
        memory_delta = performance_info.get("memory_delta", 0)
        result_size = performance_info.get("result_size", 0)

        if execution_time > self.slow_threshold * 2:
            suggestions.append("考虑启用缓存或增加缓存TTL")

        if memory_delta > 50:  # 内存增长超过50MB
            suggestions.append("考虑优化内存使用或分批处理")

        if result_size > 1024:  # 结果大小超过1MB
            suggestions.append("考虑压缩响应数据或分页处理")

        if execution_time > 10:  # 超过10秒
            suggestions.append("考虑异步处理或增加并发限制")

        return suggestions

    def get_operation_stats(self, operation_name: str) -> Dict[str, float]:
        """获取操作统计信息"""
        stats = self.operation_stats.get(operation_name, [])
        if not stats:
            return {}

        return {
            "count": len(stats),
            "average": sum(stats) / len(stats),
            "min": min(stats),
            "max": max(stats),
            "slow_operations": len([t for t in stats if t > self.slow_threshold]),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """获取所有操作统计信息"""
        return {
            operation: self.get_operation_stats(operation)
            for operation in self.operation_stats.keys()
        }


# 全局实例
_request_batcher = None
_concurrent_fetcher = None
_memory_optimizer = None
_performance_monitor = None


def get_request_batcher(
    batch_size: int = 10, batch_timeout: float = 1.0
) -> RequestBatcher:
    """获取全局请求批处理器实例"""
    global _request_batcher
    if _request_batcher is None:
        _request_batcher = RequestBatcher(batch_size, batch_timeout)
    return _request_batcher


def get_concurrent_fetcher(
    max_concurrent: int = 10, rate_limit_delay: float = 0.1
) -> ConcurrentResourceFetcher:
    """获取全局并发资源获取器实例"""
    global _concurrent_fetcher
    if _concurrent_fetcher is None:
        _concurrent_fetcher = ConcurrentResourceFetcher(
            max_concurrent, rate_limit_delay
        )
    return _concurrent_fetcher


def get_memory_optimizer(max_object_size: int = 1024 * 1024) -> MemoryOptimizer:
    """获取全局内存优化器实例"""
    global _memory_optimizer
    if _memory_optimizer is None:
        _memory_optimizer = MemoryOptimizer(max_object_size)
    return _memory_optimizer


def get_istio_performance_monitor(slow_threshold: float = 5.0) -> PerformanceMonitor:
    """获取全局Istio性能监控器实例"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor(slow_threshold)
    return _performance_monitor


# 便捷装饰器
def optimize_concurrent_operation(
    max_concurrent: int = 10, rate_limit_delay: float = 0.1, timeout: float = 30.0
):
    """并发操作优化装饰器"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            fetcher = get_concurrent_fetcher(max_concurrent, rate_limit_delay)

            # 如果参数中包含多个资源请求，进行并发处理
            if "resource_requests" in kwargs:
                resource_requests = kwargs.pop("resource_requests")
                fetch_functions = [
                    lambda req=req: func(*args, **kwargs, **req)
                    for req in resource_requests
                ]
                return await fetcher.fetch_resources(fetch_functions, timeout)
            else:
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def optimize_memory_usage(max_object_size: int = 1024 * 1024):
    """内存使用优化装饰器"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            optimizer = get_memory_optimizer(max_object_size)
            return optimizer.optimize_large_object(result)

        return wrapper

    return decorator


def monitor_istio_performance(operation_name: str, slow_threshold: float = 5.0):
    """Istio性能监控装饰器"""

    def decorator(func):
        monitor = get_istio_performance_monitor(slow_threshold)
        return monitor.monitor_operation(operation_name)(func)

    return decorator


async def batch_fetch_istio_resources(
    cluster_name: str,
    resource_requests: List[Dict[str, Any]],
    max_concurrent: int = 10,
    timeout: float = 30.0,
    enable_rate_limiting: bool = True,
    rate_limit_delay: float = 0.1,
    enable_retry: bool = True,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    批量并发获取Istio资源，支持速率限制、重试和详细统计

    Args:
        cluster_name: 集群名称
        resource_requests: 资源请求列表
        max_concurrent: 最大并发数
        timeout: 超时时间
        enable_rate_limiting: 是否启用速率限制
        rate_limit_delay: 速率限制延迟
        enable_retry: 是否启用重试
        max_retries: 最大重试次数

    Returns:
        Dict[str, Any]: 批量获取结果和统计信息
    """
    logger = logging.getLogger("cloudpilot.istio_batch_fetch")
    start_time = time.time()

    try:
        logger.info(
            f"[批量获取][{cluster_name}]开始批量获取Istio资源，请求数: {len(resource_requests)}, "
            f"最大并发: {max_concurrent}, 超时: {timeout}秒"
        )

        # 创建增强的并发获取器
        fetcher = get_concurrent_fetcher(
            max_concurrent, rate_limit_delay if enable_rate_limiting else 0
        )

        # 统计信息
        stats = {
            "total_requests": len(resource_requests),
            "successful_requests": 0,
            "failed_requests": 0,
            "retried_requests": 0,
            "cache_hits": 0,
            "execution_times": [],
            "resource_type_stats": defaultdict(lambda: {"success": 0, "failed": 0}),
        }

        # 创建获取函数列表
        fetch_functions = []
        for i, request in enumerate(resource_requests):
            resource_type = request.get("resource_type")
            operation = request.get("operation")
            params = request.get("params", {})
            request_id = f"{resource_type}_{operation}_{i}"

            # 创建增强的获取函数
            fetch_func = await _create_enhanced_fetch_function(
                cluster_name,
                resource_type,
                operation,
                params,
                request_id,
                enable_retry,
                max_retries,
                stats,
            )

            if fetch_func:
                fetch_functions.append(fetch_func)
            else:
                logger.warning(
                    f"[批量获取][{cluster_name}]不支持的资源类型: {resource_type}/{operation}"
                )
                stats["failed_requests"] += 1
                stats["resource_type_stats"][resource_type]["failed"] += 1

        # 并发获取资源
        results = await fetcher.fetch_resources(fetch_functions, timeout)

        # 处理结果
        successful_results = []
        for result in results:
            if result is not None and not isinstance(result, Exception):
                successful_results.append(result)
                stats["successful_requests"] += 1
            else:
                stats["failed_requests"] += 1

        # 计算执行时间
        total_execution_time = time.time() - start_time
        avg_execution_time = (
            sum(stats["execution_times"]) / len(stats["execution_times"])
            if stats["execution_times"]
            else 0
        )

        # 获取性能指标
        performance_metrics = fetcher.get_metrics()

        logger.info(
            f"[批量获取][{cluster_name}]批量获取完成，成功: {stats['successful_requests']}/{stats['total_requests']}, "
            f"耗时: {total_execution_time:.2f}秒, 平均: {avg_execution_time:.3f}秒"
        )

        return {
            "cluster_name": cluster_name,
            "results": successful_results,
            "statistics": {
                **stats,
                "total_execution_time": total_execution_time,
                "average_execution_time": avg_execution_time,
                "success_rate": (
                    (stats["successful_requests"] / stats["total_requests"] * 100)
                    if stats["total_requests"] > 0
                    else 0
                ),
            },
            "performance_metrics": {
                "total_requests": performance_metrics.total_requests,
                "successful_requests": performance_metrics.successful_requests,
                "failed_requests": performance_metrics.failed_requests,
                "average_response_time": performance_metrics.average_response_time,
                "max_response_time": performance_metrics.max_response_time,
                "min_response_time": performance_metrics.min_response_time,
                "concurrent_requests": performance_metrics.concurrent_requests,
            },
        }

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(
            f"[批量获取][{cluster_name}]批量获取失败，耗时: {execution_time:.2f}秒, 错误: {str(e)}"
        )
        return {
            "cluster_name": cluster_name,
            "results": [],
            "error": str(e),
            "statistics": {
                "total_requests": len(resource_requests),
                "successful_requests": 0,
                "failed_requests": len(resource_requests),
                "total_execution_time": execution_time,
            },
        }


async def _create_enhanced_fetch_function(
    cluster_name: str,
    resource_type: str,
    operation: str,
    params: Dict[str, Any],
    request_id: str,
    enable_retry: bool,
    max_retries: int,
    stats: Dict[str, Any],
) -> Optional[Callable]:
    """
    创建增强的获取函数，支持重试和统计

    Args:
        cluster_name: 集群名称
        resource_type: 资源类型
        operation: 操作类型
        params: 参数
        request_id: 请求ID
        enable_retry: 是否启用重试
        max_retries: 最大重试次数
        stats: 统计信息

    Returns:
        Optional[Callable]: 获取函数
    """
    logger = logging.getLogger("cloudpilot.istio_enhanced_fetch")

    async def enhanced_fetch_with_retry():
        """带重试的增强获取函数"""
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()

                # 根据资源类型调用相应的获取函数
                result = await _execute_resource_fetch(
                    resource_type, operation, params, cluster_name
                )

                execution_time = time.time() - start_time
                stats["execution_times"].append(execution_time)
                stats["resource_type_stats"][resource_type]["success"] += 1

                if attempt > 0:
                    stats["retried_requests"] += 1
                    logger.info(
                        f"[增强获取][{cluster_name}]重试成功: {request_id}, 尝试次数: {attempt + 1}"
                    )

                return result

            except Exception as e:
                last_error = e
                execution_time = time.time() - start_time
                stats["execution_times"].append(execution_time)

                if attempt < max_retries and enable_retry:
                    retry_delay = min(2**attempt, 10)  # 指数退避，最大10秒
                    logger.warning(
                        f"[增强获取][{cluster_name}]获取失败，将重试: {request_id}, "
                        f"尝试 {attempt + 1}/{max_retries + 1}, 延迟 {retry_delay}秒, 错误: {str(e)}"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"[增强获取][{cluster_name}]获取最终失败: {request_id}, "
                        f"尝试次数: {attempt + 1}, 错误: {str(e)}"
                    )
                    stats["resource_type_stats"][resource_type]["failed"] += 1
                    break

        return last_error

    # 根据资源类型返回对应的获取函数
    if resource_type in [
        "istiod",
        "gateway_workload",
        "gateway",
        "virtualservice",
        "destinationrule",
    ]:
        return enhanced_fetch_with_retry
    else:
        return None


async def _execute_resource_fetch(
    resource_type: str,
    operation: str,
    params: Dict[str, Any],
    cluster_name: str,
) -> Any:
    """
    执行资源获取操作

    Args:
        resource_type: 资源类型
        operation: 操作类型
        params: 参数
        cluster_name: 集群名称

    Returns:
        Any: 获取结果
    """
    if resource_type == "istiod" and operation == "detail":
        from src.modes.istio.workloads.istiod_api import get_istiod_details

        return await get_istiod_details(
            params.get("dynamic_client"),
            params.get("namespace", "istio-system"),
            cluster_name,
        )
    elif resource_type == "gateway_workload" and operation == "detail":
        from src.modes.istio.workloads.gateway_workload_api import (
            get_gateway_workload_details,
        )

        return await get_gateway_workload_details(
            params.get("dynamic_client"),
            params.get("namespace", "istio-system"),
            cluster_name,
        )
    elif resource_type == "gateway" and operation == "list":
        from src.modes.istio.components.gateway_api import get_gateway_list

        return await get_gateway_list(params.get("request"))
    elif resource_type == "virtualservice" and operation == "list":
        from src.modes.istio.components.virtualservice_api import (
            get_virtualservice_list,
        )

        return await get_virtualservice_list(params.get("request"))
    elif resource_type == "destinationrule" and operation == "list":
        from src.modes.istio.components.destinationrule_api import (
            get_destinationrule_list,
        )

        return await get_destinationrule_list(params.get("request"))
    else:
        raise ValueError(f"不支持的资源类型: {resource_type}/{operation}")


async def optimize_istio_api_performance(
    cluster_name: str,
    operation_name: str,
    fetch_func: Callable[[], Awaitable[Any]],
    cache_enabled: bool = True,
    concurrent_enabled: bool = True,
    memory_optimization: bool = True,
) -> Any:
    """
    优化Istio API性能

    Args:
        cluster_name: 集群名称
        operation_name: 操作名称
        fetch_func: 获取函数
        cache_enabled: 是否启用缓存
        concurrent_enabled: 是否启用并发优化
        memory_optimization: 是否启用内存优化

    Returns:
        Any: 优化后的结果
    """
    logger = logging.getLogger("cloudpilot.istio_performance_optimizer")

    start_time = time.time()

    try:
        # 性能监控
        monitor = get_istio_performance_monitor()

        # 内存优化
        if memory_optimization:
            optimizer = get_memory_optimizer()

        # 执行获取函数
        result = await fetch_func()

        # 应用内存优化
        if memory_optimization and result:
            result = optimizer.optimize_large_object(result)

        execution_time = time.time() - start_time

        # 记录性能指标
        monitor.operation_stats[operation_name].append(execution_time)

        logger.debug(
            f"[性能优化][{cluster_name}]{operation_name} 完成，耗时: {execution_time:.2f}秒"
        )

        return result

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(
            f"[性能优化][{cluster_name}]{operation_name} 失败，耗时: {execution_time:.2f}秒，错误: {str(e)}"
        )
        raise


async def parallel_istio_operations(
    cluster_name: str,
    operations: List[Dict[str, Any]],
    max_concurrent: int = 5,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    并行执行多个Istio操作

    Args:
        cluster_name: 集群名称
        operations: 操作列表
        max_concurrent: 最大并发数
        timeout: 超时时间

    Returns:
        Dict[str, Any]: 操作结果字典
    """
    logger = logging.getLogger("cloudpilot.istio_parallel_operations")

    try:
        logger.info(f"[并行操作][{cluster_name}]开始并行执行 {len(operations)} 个操作")

        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_operation(operation: Dict[str, Any]) -> tuple:
            async with semaphore:
                operation_name = operation.get("name", "unknown")
                operation_func = operation.get("func")
                operation_params = operation.get("params", {})

                try:
                    # 添加速率限制
                    await asyncio.sleep(0.1)

                    result = await operation_func(**operation_params)
                    return operation_name, {"success": True, "data": result}

                except Exception as e:
                    logger.error(
                        f"[并行操作][{cluster_name}]操作 {operation_name} 失败: {str(e)}"
                    )
                    return operation_name, {"success": False, "error": str(e)}

        # 创建并发任务
        tasks = [execute_operation(op) for op in operations]

        # 等待所有任务完成
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=timeout
        )

        # 处理结果
        operation_results = {}
        successful_count = 0

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"[并行操作][{cluster_name}]任务异常: {str(result)}")
                continue

            operation_name, operation_result = result
            operation_results[operation_name] = operation_result

            if operation_result.get("success"):
                successful_count += 1

        logger.info(
            f"[并行操作][{cluster_name}]并行操作完成，成功: {successful_count}/{len(operations)}"
        )

        return {
            "total_operations": len(operations),
            "successful_operations": successful_count,
            "failed_operations": len(operations) - successful_count,
            "results": operation_results,
        }

    except asyncio.TimeoutError:
        logger.error(f"[并行操作][{cluster_name}]并行操作超时: {timeout}秒")
        return {
            "total_operations": len(operations),
            "successful_operations": 0,
            "failed_operations": len(operations),
            "error": "操作超时",
            "results": {},
        }
    except Exception as e:
        logger.error(f"[并行操作][{cluster_name}]并行操作失败: {str(e)}")
        return {
            "total_operations": len(operations),
            "successful_operations": 0,
            "failed_operations": len(operations),
            "error": str(e),
            "results": {},
        }
