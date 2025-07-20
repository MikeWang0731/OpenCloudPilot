# -*- coding: utf-8 -*-
"""
Node API单元测试
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.modes.k8s.resources.node_api import (
    calculate_resource_utilization,
    analyze_node_conditions,
    calculate_node_health_score,
    get_node_details,
    create_server_node_router,
    create_instant_node_router,
    NodeRequest,
    ResourceCapacity,
    ResourceUsage,
    NodeCondition,
    NodeDetail,
)


class TestNodeAPI(unittest.TestCase):
    """Node API测试类"""

    def setUp(self):
        """测试初始化"""
        self.mock_logger = Mock()

    def test_calculate_resource_utilization_basic(self):
        """测试基本资源利用率计算"""
        capacity = {"cpu": "4", "memory": "8Gi", "pods": "110"}

        allocatable = {"cpu": "3800m", "memory": "7Gi", "pods": "110"}

        pod_count = 50

        with patch("src.modes.k8s.resources.node_api.ResourceParser") as mock_parser:
            mock_parser_instance = Mock()
            mock_parser_instance.parse_resource_usage.side_effect = [
                4.0,  # cpu_capacity
                3.8,  # cpu_allocatable
                8589934592,  # memory_capacity (8Gi in bytes)
                7516192768,  # memory_allocatable (7Gi in bytes)
            ]
            mock_parser.return_value = mock_parser_instance

            result = calculate_resource_utilization(
                capacity, allocatable, pod_count, "test-cluster"
            )

            self.assertIsInstance(result, ResourceUsage)
            self.assertEqual(result.pod_count, 50)
            self.assertAlmostEqual(
                result.pod_percentage, 45.45, places=1
            )  # 50/110 * 100

    def test_analyze_node_conditions_healthy(self):
        """测试健康Node条件分析"""
        conditions = [
            {
                "type": "Ready",
                "status": "True",
                "lastHeartbeatTime": "2023-01-01T00:00:00Z",
                "lastTransitionTime": "2023-01-01T00:00:00Z",
                "reason": "KubeletReady",
                "message": "kubelet is posting ready status",
            },
            {
                "type": "MemoryPressure",
                "status": "False",
                "lastHeartbeatTime": "2023-01-01T00:00:00Z",
                "lastTransitionTime": "2023-01-01T00:00:00Z",
                "reason": "KubeletHasSufficientMemory",
                "message": "kubelet has sufficient memory available",
            },
            {
                "type": "DiskPressure",
                "status": "False",
                "lastHeartbeatTime": "2023-01-01T00:00:00Z",
                "lastTransitionTime": "2023-01-01T00:00:00Z",
                "reason": "KubeletHasNoDiskPressure",
                "message": "kubelet has no disk pressure",
            },
        ]

        with patch("src.modes.k8s.resources.node_api.K8sUtils") as mock_k8s_utils:
            mock_k8s_utils_instance = Mock()
            mock_k8s_utils_instance.format_timestamp.return_value = (
                "2023-01-01T00:00:00Z"
            )
            mock_k8s_utils.return_value = mock_k8s_utils_instance

            node_conditions, error_indicators = analyze_node_conditions(
                conditions, "test-cluster"
            )

            self.assertEqual(len(node_conditions), 3)
            self.assertEqual(len(error_indicators), 0)

            ready_condition = next(c for c in node_conditions if c.type == "Ready")
            self.assertEqual(ready_condition.status, "True")
            self.assertEqual(ready_condition.reason, "KubeletReady")

    def test_analyze_node_conditions_unhealthy(self):
        """测试不健康Node条件分析"""
        conditions = [
            {
                "type": "Ready",
                "status": "False",
                "reason": "KubeletNotReady",
                "message": "kubelet is not ready",
            },
            {
                "type": "MemoryPressure",
                "status": "True",
                "reason": "KubeletHasInsufficientMemory",
                "message": "kubelet has insufficient memory available",
            },
            {
                "type": "DiskPressure",
                "status": "True",
                "reason": "KubeletHasDiskPressure",
                "message": "kubelet has disk pressure",
            },
        ]

        with patch("src.modes.k8s.resources.node_api.K8sUtils") as mock_k8s_utils:
            mock_k8s_utils_instance = Mock()
            mock_k8s_utils_instance.format_timestamp.return_value = (
                "2023-01-01T00:00:00Z"
            )
            mock_k8s_utils.return_value = mock_k8s_utils_instance

            node_conditions, error_indicators = analyze_node_conditions(
                conditions, "test-cluster"
            )

            self.assertEqual(len(node_conditions), 3)
            self.assertEqual(len(error_indicators), 3)
            self.assertIn("节点未就绪", error_indicators)
            self.assertIn("内存压力", error_indicators)
            self.assertIn("磁盘压力", error_indicators)

    def test_calculate_node_health_score_healthy(self):
        """测试健康Node的分数计算"""
        node_data = {
            "spec": {
                "unschedulable": False,
                "taints": [],
            }
        }

        conditions = [
            NodeCondition(
                type="Ready",
                status="True",
                reason="KubeletReady",
                message="kubelet is posting ready status",
            )
        ]

        error_indicators = []

        score = calculate_node_health_score(node_data, conditions, error_indicators)
        self.assertEqual(score, 100.0)

    def test_calculate_node_health_score_unhealthy(self):
        """测试不健康Node的分数计算"""
        node_data = {
            "spec": {
                "unschedulable": True,
                "taints": [
                    {"key": "node.kubernetes.io/not-ready", "effect": "NoSchedule"},
                    {"key": "custom-taint", "effect": "NoExecute"},
                ],
            }
        }

        conditions = [
            NodeCondition(
                type="Ready",
                status="False",
                reason="KubeletNotReady",
                message="kubelet is not ready",
            )
        ]

        error_indicators = ["节点未就绪", "内存压力"]

        score = calculate_node_health_score(node_data, conditions, error_indicators)
        # 应该扣分：不可调度(-20) + 污点2个(-10) + 未就绪(-50) + 内存压力(-30)
        expected_score = 100 - 20 - 10 - 50 - 30
        self.assertEqual(score, max(0.0, expected_score))

    @patch("src.modes.k8s.resources.node_api.client.CoreV1Api")
    @patch("src.modes.k8s.resources.node_api.K8sUtils")
    @patch("src.modes.k8s.resources.node_api.ResourceParser")
    def test_get_node_details_success(self, mock_parser, mock_k8s_utils, mock_v1_api):
        """测试成功获取Node详情"""
        # 模拟K8s API响应
        mock_node = Mock()
        mock_node.metadata.name = "test-node"
        mock_node.metadata.uid = "test-uid"
        mock_node.metadata.creation_timestamp = datetime.now(timezone.utc)
        mock_node.metadata.labels = {
            "node-role.kubernetes.io/control-plane": "",
            "kubernetes.io/hostname": "test-node",
        }
        mock_node.metadata.annotations = {}

        mock_node.spec.unschedulable = False
        mock_node.spec.taints = []

        mock_node.status.capacity = {"cpu": "4", "memory": "8Gi", "pods": "110"}
        mock_node.status.allocatable = {"cpu": "3800m", "memory": "7Gi", "pods": "110"}
        mock_node.status.conditions = [Mock()]
        mock_node.status.conditions[0].type = "Ready"
        mock_node.status.conditions[0].status = "True"
        mock_node.status.conditions[0].to_dict.return_value = {
            "type": "Ready",
            "status": "True",
            "reason": "KubeletReady",
        }

        mock_node.status.addresses = [Mock()]
        mock_node.status.addresses[0].type = "InternalIP"
        mock_node.status.addresses[0].address = "192.168.1.100"

        mock_node.status.node_info = Mock()
        mock_node.status.node_info.machine_id = "test-machine-id"
        mock_node.status.node_info.kernel_version = "5.4.0"
        mock_node.status.node_info.os_image = "Ubuntu 20.04"
        mock_node.status.node_info.container_runtime_version = "containerd://1.4.0"
        mock_node.status.node_info.kubelet_version = "v1.21.0"
        mock_node.status.node_info.kube_proxy_version = "v1.21.0"
        mock_node.status.node_info.operating_system = "linux"
        mock_node.status.node_info.architecture = "amd64"
        mock_node.status.node_info.system_uuid = "test-system-uuid"
        mock_node.status.node_info.boot_id = "test-boot-id"

        mock_node.to_dict.return_value = {"spec": {"unschedulable": False}}

        # 模拟Pod列表
        mock_pod_list = Mock()
        mock_pod_list.items = [Mock(), Mock()]  # 2个Pod

        # 配置模拟对象
        mock_v1_instance = Mock()
        mock_v1_instance.read_node.return_value = mock_node
        mock_v1_instance.list_pod_for_all_namespaces.return_value = mock_pod_list
        mock_v1_api.return_value = mock_v1_instance

        mock_k8s_utils_instance = Mock()
        mock_k8s_utils_instance.format_timestamp.return_value = "2023-01-01T00:00:00Z"
        mock_k8s_utils_instance.calculate_age.return_value = "1d"
        mock_k8s_utils.return_value = mock_k8s_utils_instance

        mock_parser_instance = Mock()
        mock_parser_instance.extract_error_indicators.return_value = []
        mock_parser.return_value = mock_parser_instance

        # 模拟动态客户端
        mock_dynamic_client = Mock()
        mock_dynamic_client.client = Mock()

        # 调用函数
        result = get_node_details(mock_dynamic_client, "test-node", "test-cluster")

        # 验证结果
        self.assertIsInstance(result, NodeDetail)
        self.assertEqual(result.name, "test-node")
        self.assertEqual(result.status, "Ready")
        self.assertIn("control-plane", result.roles)
        self.assertEqual(result.capacity.cpu, "4")
        self.assertEqual(result.allocatable.memory, "7Gi")
        self.assertIsNotNone(result.system_info)
        self.assertEqual(result.system_info.kernel_version, "5.4.0")

    @patch("src.modes.k8s.resources.node_api.client.CoreV1Api")
    def test_get_node_details_not_found(self, mock_v1_api):
        """测试Node不存在的情况"""
        from kubernetes.client.exceptions import ApiException

        mock_v1_instance = Mock()
        mock_v1_instance.read_node.side_effect = ApiException(status=404)
        mock_v1_api.return_value = mock_v1_instance

        mock_dynamic_client = Mock()
        mock_dynamic_client.client = Mock()

        result = get_node_details(
            mock_dynamic_client, "nonexistent-node", "test-cluster"
        )

        self.assertIsNone(result)

    def test_node_request_validation(self):
        """测试Node请求模型验证"""
        # 测试有效请求
        request = NodeRequest(
            cluster_name="test-cluster",
            node_name="test-node",
            force_refresh=True,
        )

        self.assertEqual(request.cluster_name, "test-cluster")
        self.assertEqual(request.node_name, "test-node")
        self.assertTrue(request.force_refresh)

        # 测试默认值
        request_minimal = NodeRequest()
        self.assertIsNone(request_minimal.cluster_name)
        self.assertIsNone(request_minimal.node_name)
        self.assertFalse(request_minimal.force_refresh)

    def test_resource_capacity_model(self):
        """测试资源容量模型"""
        capacity = ResourceCapacity(
            cpu="4", memory="8Gi", storage="100Gi", pods="110", ephemeral_storage="50Gi"
        )

        self.assertEqual(capacity.cpu, "4")
        self.assertEqual(capacity.memory, "8Gi")
        self.assertEqual(capacity.storage, "100Gi")
        self.assertEqual(capacity.pods, "110")
        self.assertEqual(capacity.ephemeral_storage, "50Gi")

    def test_resource_usage_model(self):
        """测试资源使用情况模型"""
        usage = ResourceUsage(
            cpu_usage="2",
            memory_usage="4Gi",
            cpu_percentage=50.0,
            memory_percentage=50.0,
            pod_count=55,
            pod_percentage=50.0,
        )

        self.assertEqual(usage.cpu_usage, "2")
        self.assertEqual(usage.memory_usage, "4Gi")
        self.assertEqual(usage.cpu_percentage, 50.0)
        self.assertEqual(usage.memory_percentage, 50.0)
        self.assertEqual(usage.pod_count, 55)
        self.assertEqual(usage.pod_percentage, 50.0)


if __name__ == "__main__":
    unittest.main()
