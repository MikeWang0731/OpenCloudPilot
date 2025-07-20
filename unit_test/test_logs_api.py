# -*- coding: utf-8 -*-
"""
日志API单元测试
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.modes.k8s.resources.logs_api import (
    detect_error_patterns,
    parse_log_entries,
    get_pod_logs,
    create_server_logs_router,
    create_instant_logs_router,
    LogRequest,
    LogEntry,
    LogResponse,
)


class TestLogsAPI(unittest.TestCase):
    """日志API测试类"""

    def setUp(self):
        """测试初始化"""
        self.mock_logger = Mock()

    def test_detect_error_patterns_basic(self):
        """测试基本错误模式检测"""
        # 测试错误日志
        result = detect_error_patterns("ERROR: Connection failed")
        self.assertEqual(result["level"], "error")
        self.assertTrue(result["is_error"])
        self.assertEqual(result["severity"], "medium")

        # 测试警告日志
        result = detect_error_patterns("WARN: Deprecated API")
        self.assertEqual(result["level"], "warning")
        self.assertFalse(result["is_error"])
        self.assertEqual(result["severity"], "low")

        # 测试信息日志
        result = detect_error_patterns("INFO: Application started")
        self.assertEqual(result["level"], "info")
        self.assertFalse(result["is_error"])
        self.assertEqual(result["severity"], "normal")

    def test_detect_error_patterns_http_error(self):
        """测试HTTP错误检测"""
        result = detect_error_patterns("HTTP 500 Internal Server Error")
        self.assertTrue(result["is_error"])
        self.assertEqual(result["severity"], "medium")
        self.assertIn("http_error", result["patterns_found"])

    def test_detect_error_patterns_stack_trace(self):
        """测试堆栈跟踪检测"""
        python_traceback = """Traceback (most recent call last):
  File "test.py", line 10, in <module>
    raise Exception("Test error")
Exception: Test error"""

        result = detect_error_patterns(python_traceback)
        self.assertTrue(result["is_error"])
        self.assertEqual(result["severity"], "high")
        self.assertIn("python_traceback", result["patterns_found"])

    def test_parse_log_entries_with_timestamps(self):
        """测试带时间戳的日志解析"""
        raw_logs = """2024-01-15T10:30:00.123Z INFO Application started
2024-01-15T10:30:01.456Z ERROR Connection failed
2024-01-15T10:30:02.789Z WARN Deprecated API used"""

        entries = parse_log_entries(raw_logs, "test-container", True)

        self.assertEqual(len(entries), 3)

        # 检查第一条日志
        self.assertEqual(entries[0].timestamp, "2024-01-15T10:30:00.123Z")
        self.assertEqual(entries[0].message, "INFO Application started")
        self.assertEqual(entries[0].level, "info")
        self.assertFalse(entries[0].is_error)

        # 检查第二条日志（错误）
        self.assertEqual(entries[1].timestamp, "2024-01-15T10:30:01.456Z")
        self.assertEqual(entries[1].message, "ERROR Connection failed")
        self.assertEqual(entries[1].level, "error")
        self.assertTrue(entries[1].is_error)

    def test_parse_log_entries_without_timestamps(self):
        """测试不带时间戳的日志解析"""
        raw_logs = """Application started
Connection failed
Service ready"""

        entries = parse_log_entries(raw_logs, "test-container", False)

        self.assertEqual(len(entries), 3)
        for entry in entries:
            self.assertIsNone(entry.timestamp)
            self.assertEqual(entry.container_name, "test-container")

    def test_parse_log_entries_empty(self):
        """测试空日志解析"""
        entries = parse_log_entries("", "test-container", True)
        self.assertEqual(len(entries), 0)

        entries = parse_log_entries(None, "test-container", True)
        self.assertEqual(len(entries), 0)

    def test_log_request_model(self):
        """测试LogRequest模型"""
        request = LogRequest(
            cluster_name="test-cluster",
            namespace="default",
            pod_name="test-pod",
            container_name="test-container",
            tail_lines=50,
            previous=True,
        )

        self.assertEqual(request.cluster_name, "test-cluster")
        self.assertEqual(request.namespace, "default")
        self.assertEqual(request.pod_name, "test-pod")
        self.assertEqual(request.container_name, "test-container")
        self.assertEqual(request.tail_lines, 50)
        self.assertTrue(request.previous)

    def test_log_entry_model(self):
        """测试LogEntry模型"""
        entry = LogEntry(
            timestamp="2024-01-15T10:30:00.123Z",
            container_name="test-container",
            message="Test log message",
            level="info",
            severity="normal",
            is_error=False,
            line_number=1,
        )

        self.assertEqual(entry.timestamp, "2024-01-15T10:30:00.123Z")
        self.assertEqual(entry.container_name, "test-container")
        self.assertEqual(entry.message, "Test log message")
        self.assertEqual(entry.level, "info")
        self.assertEqual(entry.severity, "normal")
        self.assertFalse(entry.is_error)
        self.assertEqual(entry.line_number, 1)

    def test_log_response_model(self):
        """测试LogResponse模型"""
        entries = [
            LogEntry(
                container_name="test-container", message="Test message", line_number=1
            )
        ]

        response = LogResponse(
            pod_name="test-pod",
            namespace="default",
            container_name="test-container",
            total_lines=1,
            entries=entries,
            error_count=0,
            warning_count=0,
            has_more=False,
        )

        self.assertEqual(response.pod_name, "test-pod")
        self.assertEqual(response.namespace, "default")
        self.assertEqual(response.container_name, "test-container")
        self.assertEqual(response.total_lines, 1)
        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.error_count, 0)
        self.assertEqual(response.warning_count, 0)
        self.assertFalse(response.has_more)


class TestLogsAPIRouters(unittest.TestCase):
    """日志API路由测试类"""

    def setUp(self):
        """测试初始化"""
        self.mock_server_instance = Mock()
        self.mock_instant_instance = Mock()

    def test_create_server_logs_router(self):
        """测试创建Server模式日志路由"""
        router = create_server_logs_router(self.mock_server_instance)

        self.assertIsNotNone(router)
        self.assertEqual(router.prefix, "/k8s/resources/logs")
        self.assertIn("K8s Logs Resources - Server", router.tags)

    def test_create_instant_logs_router(self):
        """测试创建Instant模式日志路由"""
        router = create_instant_logs_router(self.mock_instant_instance)

        self.assertIsNotNone(router)
        self.assertEqual(router.prefix, "/k8s/resources/logs")
        self.assertIn("K8s Logs Resources - Instant", router.tags)


if __name__ == "__main__":
    unittest.main()
