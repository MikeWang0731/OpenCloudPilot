# -*- coding: utf-8 -*-
"""
异步性能优化测试
"""

import asyncio
import time
from unittest.mock import Mock, AsyncMock
from src.core.async_utils import (
    AsyncBatchProcessor,
    ConcurrentResourceFetcher,
    async_timeout,
    monitor_performance,
    PerformanceMonitor,
)


class TestAsyncBatchProcessor:
    """异步批处理器测试"""

    def setup_method(self):
        """测试前准备"""
        self.processor = AsyncBatchProcessor(max_concurrent=5, batch_size=10)

    async def test_basic_batch_processing(self):
        """测试基本批处理功能"""
        items = list(range(25))  # 25个项目

        async def process_item(item):
            await asyncio.sleep(0.01)  # 模拟处理时间
            return item * 2

        start_time = time.time()
        results = await self.processor.process_batch(items, process_item)
        elapsed_time = time.time() - start_time

        # 验证结果
        assert len(results) == 25
        assert results[0] == 0
        assert results[24] == 48

        # 验证并发处理确实提高了性能（应该比串行快）
        # 串行处理需要 25 * 0.01 = 0.25秒
        # 并发处理应该明显更快
        assert elapsed_time < 0.2

    async def test_error_handling(self):
        """测试错误处理"""
        items = [1, 2, 3, 4, 5]

        async def process_item(item):
            if item == 3:
                raise ValueError("测试错误")
            return item * 2

        def error_handler(item, error):
            return f"error_{item}"

        results = await self.processor.process_batch(items, process_item, error_handler)

        assert len(results) == 5
        assert results[0] == 2
        assert results[1] == 4
        assert results[2] == "error_3"  # 错误处理结果
        assert results[3] == 8
        assert results[4] == 10


class TestConcurrentResourceFetcher:
    """并发资源获取器测试"""

    def setup_method(self):
        """测试前准备"""
        self.fetcher = ConcurrentResourceFetcher(max_workers=3)

    async def test_concurrent_fetch(self):
        """测试并发获取"""

        async def fetch_resource_1():
            await asyncio.sleep(0.05)
            return "resource_1_data"

        async def fetch_resource_2():
            await asyncio.sleep(0.05)
            return "resource_2_data"

        def fetch_resource_3():
            time.sleep(0.05)  # 同步函数
            return "resource_3_data"

        fetch_configs = [
            {"name": "resource1", "func": fetch_resource_1},
            {"name": "resource2", "func": fetch_resource_2},
            {"name": "resource3", "func": fetch_resource_3},
        ]

        start_time = time.time()
        results = await self.fetcher.fetch_multiple_resources(fetch_configs)
        elapsed_time = time.time() - start_time

        # 验证结果
        assert len(results) == 3
        assert results["resource1"] == "resource_1_data"
        assert results["resource2"] == "resource_2_data"
        assert results["resource3"] == "resource_3_data"

        # 验证并发执行（应该比串行快）
        assert elapsed_time < 0.12  # 串行需要0.15秒

    async def test_fetch_with_error(self):
        """测试获取时的错误处理"""

        async def fetch_success():
            return "success_data"

        async def fetch_error():
            raise ValueError("获取失败")

        fetch_configs = [
            {"name": "success", "func": fetch_success},
            {"name": "error", "func": fetch_error},
        ]

        results = await self.fetcher.fetch_multiple_resources(fetch_configs)

        assert results["success"] == "success_data"
        assert results["error"] is None  # 错误时返回None


class TestAsyncDecorators:
    """异步装饰器测试"""

    async def test_timeout_decorator(self):
        """测试超时装饰器"""

        @async_timeout(0.1)
        async def slow_function():
            await asyncio.sleep(0.2)
            return "completed"

        # 应该抛出超时异常
        try:
            await slow_function()
            assert False, "应该抛出超时异常"
        except TimeoutError:
            pass

    async def test_performance_monitor_decorator(self):
        """测试性能监控装饰器"""
        monitor = PerformanceMonitor()

        @monitor_performance("test_operation", monitor)
        async def test_function():
            await asyncio.sleep(0.05)
            return "result"

        # 执行几次
        for _ in range(3):
            result = await test_function()
            assert result == "result"

        # 检查性能统计
        stats = monitor.get_stats("test_operation")
        assert stats["count"] == 3
        assert stats["avg_time"] >= 0.05
        assert stats["min_time"] >= 0.05
        assert stats["max_time"] >= 0.05


class TestPerformanceMonitor:
    """性能监控器测试"""

    def setup_method(self):
        """测试前准备"""
        self.monitor = PerformanceMonitor()

    def test_record_and_stats(self):
        """测试记录和统计"""
        # 记录一些执行时间
        self.monitor.record_execution_time("operation1", 0.1)
        self.monitor.record_execution_time("operation1", 0.2)
        self.monitor.record_execution_time("operation1", 0.15)

        self.monitor.record_execution_time("operation2", 0.05)

        # 获取统计
        stats1 = self.monitor.get_stats("operation1")
        assert stats1["count"] == 3
        assert stats1["total_time"] == 0.45
        assert stats1["avg_time"] == 0.15
        assert stats1["min_time"] == 0.1
        assert stats1["max_time"] == 0.2

        stats2 = self.monitor.get_stats("operation2")
        assert stats2["count"] == 1
        assert stats2["total_time"] == 0.05

        # 获取所有统计
        all_stats = self.monitor.get_stats()
        assert "operation1" in all_stats
        assert "operation2" in all_stats


async def run_performance_comparison():
    """运行性能对比测试"""
    print("运行性能对比测试...")

    # 创建测试数据
    items = list(range(50))

    # 串行处理
    async def serial_process():
        results = []
        for item in items:
            await asyncio.sleep(0.001)  # 模拟处理时间
            results.append(item * 2)
        return results

    # 并发处理
    async def concurrent_process():
        processor = AsyncBatchProcessor(max_concurrent=10, batch_size=10)

        async def process_item(item):
            await asyncio.sleep(0.001)
            return item * 2

        return await processor.process_batch(items, process_item)

    # 测试串行处理
    start_time = time.time()
    serial_results = await serial_process()
    serial_time = time.time() - start_time

    # 测试并发处理
    start_time = time.time()
    concurrent_results = await concurrent_process()
    concurrent_time = time.time() - start_time

    print(f"串行处理时间: {serial_time:.3f}秒")
    print(f"并发处理时间: {concurrent_time:.3f}秒")
    print(f"性能提升: {serial_time / concurrent_time:.2f}倍")

    # 验证结果一致性
    assert serial_results == concurrent_results
    assert concurrent_time < serial_time  # 并发应该更快


if __name__ == "__main__":
    # 运行性能对比测试
    asyncio.run(run_performance_comparison())
