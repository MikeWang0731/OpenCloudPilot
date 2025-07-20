# -*- coding: utf-8 -*-
"""
Events API单元测试
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.modes.k8s.resources.events_api import (
    categorize_events,
    analyze_event_patterns,
    get_resource_events,
    create_server_events_router,
    create_instant_events_router,
    EventRequest,
    EventDetail,
    EventResponse,
    EventSummary,
)


class TestEventsAPI(unittest.TestCase):
    """Events API测试类"""

    def setUp(self):
        """测试初始化"""
        self.mock_logger = Mock()

    def test_categorize_events_scheduling(self):
        """测试调度相关事件分类"""
        events = [
            {"reason": "FailedScheduling", "message": "No nodes available"},
            {"reason": "Scheduled", "message": "Successfully assigned"},
            {"reason": "Preempted", "message": "Pod preempted"},
            {"reason": "Created", "message": "Pod created"},
        ]

        result = categorize_events(events)

        self.assertEqual(len(result["scheduling"]), 3)
        self.assertEqual(len(result["lifecycle"]), 1)
        self.assertIn("FailedScheduling", [e["reason"] for e in result["scheduling"]])
        self.assertIn("Scheduled", [e["reason"] for e in result["scheduling"]])
        self.assertIn("Preempted", [e["reason"] for e in result["scheduling"]])

    def test_categorize_events_resource(self):
        """测试资源相关事件分类"""
        events = [
            {"reason": "FailedMount", "message": "Mount failed"},
            {"reason": "OutOfMemory", "message": "Container killed"},
            {"reason": "Evicted", "message": "Pod evicted"},
            {"reason": "VolumeMount", "message": "Volume mounted"},
        ]

        result = categorize_events(events)

        self.assertEqual(len(result["resource"]), 4)
        resource_reasons = [e["reason"] for e in result["resource"]]
        self.assertIn("FailedMount", resource_reasons)
        self.assertIn("OutOfMemory", resource_reasons)
        self.assertIn("Evicted", resource_reasons)
        self.assertIn("VolumeMount", resource_reasons)

    def test_categorize_events_general(self):
        """测试一般事件分类"""
        events = [
            {"reason": "CustomReason", "message": "Custom event"},
            {"reason": "UnknownEvent", "message": "Unknown event type"},
        ]

        result = categorize_events(events)

        self.assertEqual(len(result["general"]), 2)
        self.assertEqual(len(result["scheduling"]), 0)
        self.assertEqual(len(result["resource"]), 0)

    def test_analyze_event_patterns_recurring(self):
        """测试重复事件模式分析"""
        events = [
            {"reason": "FailedScheduling", "count": 15, "message": "No nodes"},
            {"reason": "FailedScheduling", "count": 8, "message": "No nodes"},
            {"reason": "ImagePullBackOff", "count": 5, "message": "Pull failed"},
            {"reason": "Created", "count": 1, "message": "Pod created"},
        ]

        result = analyze_event_patterns(events)

        self.assertEqual(len(result["recurring_events"]), 1)
        recurring = result["recurring_events"][0]
        self.assertEqual(recurring["reason"], "FailedScheduling")
        self.assertEqual(recurring["total_count"], 23)  # 15 + 8
        self.assertEqual(recurring["event_count"], 2)

    def test_analyze_event_patterns_errors(self):
        """测试错误模式分析"""
        events = [
            {"reason": "Failed", "message": "Operation failed", "type": "Warning"},
            {"reason": "Error", "message": "System error", "type": "Warning"},
            {"reason": "Timeout", "message": "Request timeout", "type": "Warning"},
            {"reason": "Created", "message": "Pod created", "type": "Normal"},
        ]

        result = analyze_event_patterns(events)

        self.assertEqual(len(result["error_patterns"]), 3)
        error_reasons = [e["reason"] for e in result["error_patterns"]]
        self.assertIn("Failed", error_reasons)
        self.assertIn("Error", error_reasons)
        self.assertIn("Timeout", error_reasons)

    def test_analyze_event_patterns_resource_issues(self):
        """测试资源问题模式分析"""
        events = [
            {
                "reason": "OutOfMemory",
                "message": "Container killed",
                "involvedObject": {"name": "test-pod", "kind": "Pod"},
            },
            {
                "reason": "Evicted",
                "message": "Pod evicted",
                "involvedObject": {"name": "test-pod2", "kind": "Pod"},
            },
            {
                "reason": "DiskPressure",
                "message": "Disk pressure",
                "involvedObject": {"name": "node1", "kind": "Node"},
            },
        ]

        result = analyze_event_patterns(events)

        self.assertEqual(len(result["resource_issues"]), 3)
        resource_reasons = [e["reason"] for e in result["resource_issues"]]
        self.assertIn("OutOfMemory", resource_reasons)
        self.assertIn("Evicted", resource_reasons)
        self.assertIn("DiskPressure", resource_reasons)

    @patch("src.modes.k8s.resources.events_api.client.CoreV1Api")
    @patch("src.modes.k8s.resources.events_api.K8sUtils")
    def test_get_resource_events_success(self, mock_k8s_utils, mock_v1_api):
        """测试成功获取资源事件"""
        # 模拟K8s API响应
        mock_event = Mock()
        mock_event.metadata.name = "test-event"
        mock_event.metadata.namespace = "default"
        mock_event.metadata.uid = "event-uid"
        mock_event.metadata.creation_timestamp = datetime.now(timezone.utc)
        mock_event.type = "Warning"
        mock_event.reason = "FailedScheduling"
        mock_event.message = "No nodes available"
        mock_event.source.component = "default-scheduler"
        mock_event.source.host = "master-node"
        mock_event.involved_object.kind = "Pod"
        mock_event.involved_object.name = "test-pod"
        mock_event.involved_object.namespace = "default"
        mock_event.involved_object.uid = "pod-uid"
        mock_event.involved_object.api_version = "v1"
        mock_event.involved_object.resource_version = "12345"
        mock_event.first_timestamp = datetime.now(timezone.utc)
        mock_event.last_timestamp = datetime.now(timezone.utc)
        mock_event.count = 5
        mock_event.to_dict.return_value = {
            "reason": "FailedScheduling",
            "count": 5,
            "type": "Warning",
        }

        mock_event_list = Mock()
        mock_event_list.items = [mock_event]

        mock_v1_instance = Mock()
        mock_v1_instance.list_namespaced_event.return_value = mock_event_list
        mock_v1_api.return_value = mock_v1_instance

        mock_k8s_utils_instance = Mock()
        mock_k8s_utils_instance.format_timestamp.return_value = "2023-01-01T00:00:00Z"
        mock_k8s_utils_instance.calculate_age.return_value = "1h"
        mock_k8s_utils.return_value = mock_k8s_utils_instance

        # 模拟客户端
        mock_k8s_client = Mock()

        # 调用函数
        result = get_resource_events(
            mock_k8s_client,
            namespace="default",
            resource_type="Pod",
            resource_name="test-pod",
            limit=100,
            cluster_name="test-cluster",
        )

        # 验证结果
        self.assertIsInstance(result, EventResponse)
        self.assertEqual(result.namespace, "default")
        self.assertEqual(result.resource_type, "Pod")
        self.assertEqual(result.resource_name, "test-pod")
        self.assertEqual(len(result.events), 1)

        event = result.events[0]
        self.assertEqual(event.name, "test-event")
        self.assertEqual(event.type, "Warning")
        self.assertEqual(event.reason, "FailedScheduling")
        self.assertEqual(event.count, 5)
        self.assertTrue(event.is_recurring)

        # 验证摘要
        self.assertEqual(result.summary.total_events, 1)
        self.assertEqual(result.summary.warning_events, 1)
        self.assertEqual(result.summary.error_events, 1)

    @patch("src.modes.k8s.resources.events_api.client.CoreV1Api")
    @patch("src.modes.k8s.resources.events_api.K8sUtils")
    def test_get_resource_events_all_namespaces(self, mock_k8s_utils, mock_v1_api):
        """测试获取所有命名空间的事件"""
        mock_event_list = Mock()
        mock_event_list.items = []

        mock_v1_instance = Mock()
        mock_v1_instance.list_event_for_all_namespaces.return_value = mock_event_list
        mock_v1_api.return_value = mock_v1_instance

        mock_k8s_utils_instance = Mock()
        mock_k8s_utils.return_value = mock_k8s_utils_instance

        mock_k8s_client = Mock()

        # 调用函数 (不指定命名空间)
        result = get_resource_events(
            mock_k8s_client, namespace=None, cluster_name="test-cluster"
        )

        # 验证调用了正确的API方法
        mock_v1_instance.list_event_for_all_namespaces.assert_called_once()
        mock_v1_instance.list_namespaced_event.assert_not_called()

        self.assertIsInstance(result, EventResponse)
        self.assertIsNone(result.namespace)

    @patch("src.modes.k8s.resources.events_api.client.CoreV1Api")
    @patch("src.modes.k8s.resources.events_api.K8sUtils")
    def test_get_resource_events_with_filters(self, mock_k8s_utils, mock_v1_api):
        """测试带过滤条件的事件获取"""
        # 创建多个模拟事件
        mock_event1 = Mock()
        mock_event1.metadata.name = "event1"
        mock_event1.metadata.namespace = "default"
        mock_event1.metadata.uid = "uid1"
        mock_event1.metadata.creation_timestamp = datetime.now(timezone.utc)
        mock_event1.type = "Warning"
        mock_event1.reason = "FailedScheduling"
        mock_event1.message = "No nodes"
        mock_event1.source = None
        mock_event1.involved_object.kind = "Pod"
        mock_event1.involved_object.name = "test-pod"
        mock_event1.involved_object.namespace = "default"
        mock_event1.involved_object.uid = "pod-uid"
        mock_event1.involved_object.api_version = "v1"
        mock_event1.involved_object.resource_version = "123"
        mock_event1.first_timestamp = datetime.now(timezone.utc)
        mock_event1.last_timestamp = datetime.now(timezone.utc)
        mock_event1.count = 1

        mock_event2 = Mock()
        mock_event2.metadata.name = "event2"
        mock_event2.metadata.namespace = "default"
        mock_event2.metadata.uid = "uid2"
        mock_event2.metadata.creation_timestamp = datetime.now(timezone.utc)
        mock_event2.type = "Normal"
        mock_event2.reason = "Created"
        mock_event2.message = "Pod created"
        mock_event2.source = None
        mock_event2.involved_object.kind = "Deployment"  # 不同的资源类型
        mock_event2.involved_object.name = "test-deployment"
        mock_event2.involved_object.namespace = "default"
        mock_event2.involved_object.uid = "deploy-uid"
        mock_event2.involved_object.api_version = "apps/v1"
        mock_event2.involved_object.resource_version = "456"
        mock_event2.first_timestamp = datetime.now(timezone.utc)
        mock_event2.last_timestamp = datetime.now(timezone.utc)
        mock_event2.count = 1

        mock_event_list = Mock()
        mock_event_list.items = [mock_event1, mock_event2]

        mock_v1_instance = Mock()
        mock_v1_instance.list_namespaced_event.return_value = mock_event_list
        mock_v1_api.return_value = mock_v1_instance

        mock_k8s_utils_instance = Mock()
        mock_k8s_utils_instance.format_timestamp.return_value = "2023-01-01T00:00:00Z"
        mock_k8s_utils_instance.calculate_age.return_value = "1h"
        mock_k8s_utils.return_value = mock_k8s_utils_instance

        mock_k8s_client = Mock()

        # 测试资源类型过滤
        result = get_resource_events(
            mock_k8s_client,
            namespace="default",
            resource_type="Pod",  # 只获取Pod事件
            cluster_name="test-cluster",
        )

        # 应该只返回Pod相关的事件
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.events[0].involved_object["kind"], "Pod")

        # 测试事件类型过滤
        result = get_resource_events(
            mock_k8s_client,
            namespace="default",
            event_type="Warning",  # 只获取Warning事件
            cluster_name="test-cluster",
        )

        # 应该只返回Warning事件
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.events[0].type, "Warning")

    def test_event_request_validation(self):
        """测试事件请求模型验证"""
        # 测试有效请求
        request = EventRequest(
            cluster_name="test-cluster",
            namespace="default",
            resource_type="Pod",
            resource_name="test-pod",
            since_time=datetime.now(timezone.utc),
            limit=50,
            event_type="Warning",
        )

        self.assertEqual(request.cluster_name, "test-cluster")
        self.assertEqual(request.namespace, "default")
        self.assertEqual(request.resource_type, "Pod")
        self.assertEqual(request.resource_name, "test-pod")
        self.assertEqual(request.limit, 50)
        self.assertEqual(request.event_type, "Warning")

        # 测试默认值
        request_minimal = EventRequest()
        self.assertIsNone(request_minimal.cluster_name)
        self.assertIsNone(request_minimal.namespace)
        self.assertIsNone(request_minimal.resource_type)
        self.assertEqual(request_minimal.limit, 100)

    def test_event_detail_model(self):
        """测试事件详情模型"""
        event_detail = EventDetail(
            name="test-event",
            namespace="default",
            uid="event-uid",
            type="Warning",
            reason="FailedScheduling",
            message="No nodes available",
            source_component="scheduler",
            involved_object={
                "kind": "Pod",
                "name": "test-pod",
                "namespace": "default",
                "uid": "pod-uid",
            },
            count=5,
            creation_timestamp="2023-01-01T00:00:00Z",
            age="1h",
            severity="high",
            category="scheduling",
            is_recurring=True,
        )

        self.assertEqual(event_detail.name, "test-event")
        self.assertEqual(event_detail.type, "Warning")
        self.assertEqual(event_detail.reason, "FailedScheduling")
        self.assertEqual(event_detail.count, 5)
        self.assertTrue(event_detail.is_recurring)
        self.assertEqual(event_detail.severity, "high")
        self.assertEqual(event_detail.category, "scheduling")

    def test_event_summary_model(self):
        """测试事件摘要模型"""
        summary = EventSummary(
            total_events=10,
            warning_events=3,
            normal_events=7,
            error_events=3,
            recurring_events=2,
            recent_events=5,
            categories={"scheduling": 2, "resource": 1, "general": 7},
            top_reasons=[
                {"reason": "FailedScheduling", "count": 5},
                {"reason": "Created", "count": 3},
            ],
        )

        self.assertEqual(summary.total_events, 10)
        self.assertEqual(summary.warning_events, 3)
        self.assertEqual(summary.normal_events, 7)
        self.assertEqual(summary.recurring_events, 2)
        self.assertEqual(len(summary.top_reasons), 2)
        self.assertEqual(summary.categories["scheduling"], 2)


if __name__ == "__main__":
    unittest.main()
