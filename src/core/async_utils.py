# -*- coding: utf-8 -*-
"""
异步操作优化工具
提供并发处理、批量操作和性能优化功能
"""

import asyncio
import logging
import time
from typing import List, Dict, Any, Optional, Callable, Awaitable, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
import threading


class AsyncBatchProcessor:
    """异步批处理器"""

    def __init__(self, max_concurrent: int = 10, batch_size: int = 50):
        """
        初始化批处理器

        Args:
            max_concurrent: 最大并发数
            batch_size: 批处理大小
        """
        self.max_concurrent = max_concurrent
        self.batch_size = batch_size
        self.logger = logging.getLogger("cloudpilot.AsyncBatchProcessor")
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def process_batch(
        self,
        items: List[Any],
        processor_func: Callable[[Any], Awaitable[Any]],
        error_handler: Optional[Callable[[Any, Exception], Any]] = None,
    ) -> List[Any]:
        """
        批量处理项目

        Args:
            items: 要处理的项目列表
            processor_func: 处理函数
            error_handler: 错误处理函数

        Returns:
            List[Any]: 处理结果列表
        """
        if not items:
            return []

        start_time = time.time()
        self.logger.info("开始批量处理 %d 个项目", len(items))

        # 分批处理
        results = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]
            batch_results = await self._process_single_batch(
                batch, processor_func, error_handler
            )
            results.extend(batch_results)

        elapsed_time = time.time() - start_time
        self.logger.info(
            "批量处理完成，处理 %d 个项目，耗时 %.2f 秒", len(items), elapsed_time
        )

        return results

    async def _process_single_batch(
        self,
        batch: List[Any],
        processor_func: Callable[[Any], Awaitable[Any]],
        error_handler: Optional[Callable[[Any, Exception], Any]],
    ) -> List[Any]:
        """处理单个批次"""

        async def process_with_semaphore(item):
            async with self._semaphore:
                try:
                    return await processor_func(item)
                except Exception as e:
                    if error_handler:
                        return error_handler(item, e)
                    self.logger.error("处理项目失败: %s", str(e))
                    return None

        tasks = [process_with_semaphore(item) for item in batch]
        return await asyncio.gather(*tasks, return_exceptions=False)


class ConcurrentResourceFetcher:
    """并发资源获取器"""

    def __init__(self, max_workers: int = 5):
        """
        初始化并发获取器

        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self.logger = logging.getLogger("cloudpilot.ConcurrentResourceFetcher")
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    async def fetch_multiple_resources(
        self, fetch_configs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        并发获取多个资源

        Args:
            fetch_configs: 获取配置列表，每个配置包含:
                - name: 资源名称
                - func: 获取函数
                - args: 函数参数
                - kwargs: 函数关键字参数

        Returns:
            Dict[str, Any]: 资源名称到结果的映射
        """
        if not fetch_configs:
            return {}

        start_time = time.time()
        self.logger.info("开始并发获取 %d 个资源", len(fetch_configs))

        # 创建任务
        tasks = []
        for config in fetch_configs:
            task = asyncio.create_task(
                self._fetch_single_resource(config), name=config.get("name", "unknown")
            )
            tasks.append(task)

        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 整理结果
        resource_results = {}
        for i, (config, result) in enumerate(zip(fetch_configs, results)):
            resource_name = config.get("name", f"resource_{i}")

            if isinstance(result, Exception):
                self.logger.error("获取资源 %s 失败: %s", resource_name, str(result))
                resource_results[resource_name] = None
            else:
                resource_results[resource_name] = result

        elapsed_time = time.time() - start_time
        self.logger.info(
            "并发获取完成，获取 %d 个资源，耗时 %.2f 秒",
            len(fetch_configs),
            elapsed_time,
        )

        return resource_results

    async def _fetch_single_resource(self, config: Dict[str, Any]) -> Any:
        """获取单个资源"""
        func = config.get("func")
        args = config.get("args", [])
        kwargs = config.get("kwargs", {})

        if not func:
            raise ValueError("获取函数不能为空")

        # 如果是协程函数，直接调用
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)

        # 如果是普通函数，在线程池中执行
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, lambda: func(*args, **kwargs))

    def __del__(self):
        """清理资源"""
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=False)


class AsyncCache:
    """异步缓存"""

    def __init__(self, ttl: int = 300):
        """
        初始化异步缓存

        Args:
            ttl: 缓存生存时间（秒）
        """
        self.ttl = ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self.logger = logging.getLogger("cloudpilot.AsyncCache")

    async def get_or_fetch(
        self,
        key: str,
        fetch_func: Callable[[], Awaitable[Any]],
        force_refresh: bool = False,
    ) -> Any:
        """
        获取缓存或获取新数据

        Args:
            key: 缓存键
            fetch_func: 数据获取函数
            force_refresh: 是否强制刷新

        Returns:
            Any: 缓存或新获取的数据
        """
        async with self._lock:
            # 检查缓存
            if not force_refresh and key in self._cache:
                cache_entry = self._cache[key]
                if time.time() - cache_entry["timestamp"] < self.ttl:
                    self.logger.debug("缓存命中: %s", key)
                    return cache_entry["data"]

            # 获取新数据
            self.logger.debug("获取新数据: %s", key)
            data = await fetch_func()

            # 更新缓存
            self._cache[key] = {"data": data, "timestamp": time.time()}

            return data

    async def invalidate(self, key: Optional[str] = None):
        """
        使缓存失效

        Args:
            key: 要失效的键，为None则清空所有缓存
        """
        async with self._lock:
            if key is None:
                self._cache.clear()
                self.logger.info("清空所有缓存")
            elif key in self._cache:
                del self._cache[key]
                self.logger.info("清除缓存: %s", key)


def async_timeout(timeout_seconds: int):
    """
    异步超时装饰器

    Args:
        timeout_seconds: 超时时间（秒）
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"操作超时 ({timeout_seconds}秒)")

        return wrapper

    return decorator


def async_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    异步重试装饰器

    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 退避倍数
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        raise last_exception

        return wrapper

    return decorator


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.metrics: Dict[str, List[float]] = {}
        self.logger = logging.getLogger("cloudpilot.PerformanceMonitor")
        self._lock = threading.Lock()

    def record_execution_time(self, operation: str, execution_time: float):
        """
        记录执行时间

        Args:
            operation: 操作名称
            execution_time: 执行时间（秒）
        """
        with self._lock:
            if operation not in self.metrics:
                self.metrics[operation] = []
            self.metrics[operation].append(execution_time)

    def get_stats(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """
        获取性能统计

        Args:
            operation: 操作名称，为None则返回所有操作的统计

        Returns:
            Dict[str, Any]: 性能统计信息
        """
        with self._lock:
            if operation:
                if operation not in self.metrics:
                    return {}

                times = self.metrics[operation]
                return self._calculate_stats(operation, times)

            # 返回所有操作的统计
            stats = {}
            for op, times in self.metrics.items():
                stats[op] = self._calculate_stats(op, times)

            return stats

    def _calculate_stats(self, operation: str, times: List[float]) -> Dict[str, Any]:
        """计算统计信息"""
        if not times:
            return {"count": 0}

        return {
            "count": len(times),
            "total_time": sum(times),
            "avg_time": sum(times) / len(times),
            "min_time": min(times),
            "max_time": max(times),
            "last_time": times[-1],
        }


def monitor_performance(
    operation_name: str, monitor: Optional[PerformanceMonitor] = None
):
    """
    性能监控装饰器

    Args:
        operation_name: 操作名称
        monitor: 性能监控器实例
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                execution_time = time.time() - start_time
                if monitor:
                    monitor.record_execution_time(operation_name, execution_time)

        return wrapper

    return decorator


# 全局实例
_global_batch_processor: Optional[AsyncBatchProcessor] = None
_global_resource_fetcher: Optional[ConcurrentResourceFetcher] = None
_global_performance_monitor: Optional[PerformanceMonitor] = None


def get_batch_processor() -> AsyncBatchProcessor:
    """获取全局批处理器"""
    global _global_batch_processor
    if _global_batch_processor is None:
        _global_batch_processor = AsyncBatchProcessor()
    return _global_batch_processor


def get_resource_fetcher() -> ConcurrentResourceFetcher:
    """获取全局资源获取器"""
    global _global_resource_fetcher
    if _global_resource_fetcher is None:
        _global_resource_fetcher = ConcurrentResourceFetcher()
    return _global_resource_fetcher


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    global _global_performance_monitor
    if _global_performance_monitor is None:
        _global_performance_monitor = PerformanceMonitor()
    return _global_performance_monitor
