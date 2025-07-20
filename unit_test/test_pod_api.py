# -*- coding: utf-8 -*-
"""
Pod API单元测试
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.modes.k8s.resources.pod_api import (
    get_container_info,
    calculate_pod_health_score,
    get_pod_details,
    create_server_pod_router,
    create_instant_pod_router,
    PodRequest,
    ContainerInfo,
    PodDetail,
)


class TestPodAPI(unittest.TestCase):
    """Pod API测试类"""

    def setUp(self):
        """测试初始化"""
        self.mock_logger = Mock()

    def test_get_container_info_basic(self):
        """测试基本容器信息提取"""
        container_spec = {
            "name": "test-container",
            "image": "nginx:1.20",
            "imagePullPolicy": "Always",
            "ports": [{"name": "http", "containerPort": 80, "protocol": "TCP"}],
            "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "500m", "memory": "512Mi"},
            },
        }

        container_status = {
            "name": "test-container",
            "ready": True,
            "restartCount": 0,
            "state": {"running": {"startedAt": "2023-01-01T00:00:00Z"}},
        }

        result = get_container_info(container_spec, container_status)

        self.assertIsInstance(result, ContainerInfo)
        self.assertEqual(result.name, "test-container")
        self.assertEqual(result.image, "nginx:1.20")
        self.assertEqual(result.state, "Running")
        self.assertTrue(result.ready)
        self.assertEqual(result.restart_count, 0)
        self.assertEqual(len(result.ports), 1)
        self.assertEqual(result.ports[0].container_port, 80)
        self.assertEqual(result.resources.cpu_request, "100m")
        self.assertEqual(result.resources.memory_limit, "512Mi")

    def test_get_container_info_waiting_state(self):
        """测试等待状态的容器信息"""
        container_spec = {"name": "waiting-container", "image": "nginx:1.20"}

        container_status = {
            "name": "waiting-container",
            "ready": False,
            "restartCount": 1,
            "state": {
                "waiting": {
                    "reason": "ImagePullBackOff",
                    "message": "Back-off pulling image",
                }
            },
        }

        result = get_container_info(container_spec, container_status)

        self.assertEqual(result.state, "Waiting")
        self.assertFalse(result.ready)
        self.assertEqual(result.restart_count, 1)
        self.assertEqual(result.reason, "ImagePullBackOff")
        self.assertEqual(result.message, "Back-off pulling image")

    def test_get_container_info_terminated_state(self):
        """测试终止状态的容器信息"""
        container_spec = {"name": "terminated-container", "image": "nginx:1.20"}

        container_status = {
            "name": "terminated-container",
            "ready": False,
            "restartCount": 2,
            "state": {
                "terminated": {
                    "exitCode": 1,
                    "reason": "Error",
                    "message": "Container failed",
                    "startedAt": "2023-01-01T00:00:00Z",
                    "finishedAt": "2023-01-01T00:01:00Z",
                }
            },
        }

        result = get_container_info(container_spec, container_status)

        self.assertEqual(result.state, "Terminated")
        self.assertFalse(result.ready)
        self.assertEqual(result.restart_count, 2)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.reason, "Error")

    def test_calculate_pod_health_score_healthy(self):
        """测试健康Pod的分数计算"""
        pod_data = {
            "status": {
                "phase": "Running",
                "conditions": [
                    {"type": "Ready", "status": "True"},
                    {"type": "PodScheduled", "status": "True"},
                ],
            }
        }

        containers = [
            ContainerInfo(
                name="container1",
                image="nginx:1.20",
                state="Running",
                ready=True,
                restart_count=0,
            ),
            ContainerInfo(
                name="container2",
                image="redis:6.0",
                state="Running",
                ready=True,
                restart_count=0,
            ),
        ]

        score = calculate_pod_health_score(pod_data, containers)
        self.assertEqual(score, 100.0)

    def test_calculate_pod_health_score_unhealthy(self):
        """测试不健康Pod的分数计算"""
        pod_data = {
            "status": {
                "phase": "Pending",
                "conditions": [{"type": "Ready", "status": "False"}],
            }
        }

        containers = [
            ContainerInfo(
                name="container1",
                image="nginx:1.20",
                state="Waiting",
                ready=False,
                restart_count=3,
            )
        ]

        score = calculate_pod_health_score(pod_data, containers)
        # 应该扣分：Pending(-30) + 不就绪(-20) + 非运行状态(-15) + 重启3次(-15)
        expected_score = 100 - 30 - 20 - 20 - 15 - 15
        self.assertEqual(score, expected_score)

    @patch("src.modes.k8s.resources.pod_api.client.CoreV1Api")
    @patch("src.modes.k8s.resources.pod_api.K8sUtils")
    @patch("src.modes.k8s.resources.pod_api.ResourceParser")
    def test_get_pod_details_success(self, mock_parser, mock_k8s_utils, mock_v1_api):
        """测试成功获取Pod详情"""
        # 模拟K8s API响应
        mock_pod = Mock()
        mock_pod.metadata.name = "test-pod"
        mock_pod.metadata.namespace = "default"
        mock_pod.metadata.uid = "test-uid"
        mock_pod.metadata.creation_timestamp = datetime.now(timezone.utc)
        mock_pod.metadata.labels = {"app": "test"}
        mock_pod.metadata.annotations = {}
        mock_pod.metadata.owner_references = []

        mock_pod.spec.node_name = "node1"
        mock_pod.spec.containers = [Mock()]
        mock_pod.spec.containers[0].name = "test-container"
        mock_pod.spec.containers[0].image = "nginx:1.20"
        mock_pod.spec.containers[0].to_dict.return_value = {
            "name": "test-container",
            "image": "nginx:1.20",
        }
        mock_pod.spec.init_containers = []
        mock_pod.spec.restart_policy = "Always"
        mock_pod.spec.service_account_name = "default"
        mock_pod.spec.priority = None
        mock_pod.spec.priority_class_name = None

        mock_pod.status.phase = "Running"
        mock_pod.status.pod_ip = "10.0.0.1"
        mock_pod.status.host_ip = "192.168.1.1"
        mock_pod.status.start_time = datetime.now(timezone.utc)
        mock_pod.status.container_statuses = [Mock()]
        mock_pod.status.container_statuses[0].name = "test-container"
        mock_pod.status.container_statuses[0].to_dict.return_value = {
            "name": "test-container",
            "ready": True,
            "restartCount": 0,
            "state": {"running": {"startedAt": "2023-01-01T00:00:00Z"}},
        }
        mock_pod.status.init_container_statuses = []
        mock_pod.status.conditions = []
        mock_pod.status.qos_class = "BestEffort"
        mock_pod.to_dict.return_value = {"status": {"phase": "Running"}}

        # 配置模拟对象
        mock_v1_instance = Mock()
        mock_v1_instance.read_namespaced_pod.return_value = mock_pod
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
        result = get_pod_details(
            mock_dynamic_client, "default", "test-pod", "test-cluster"
        )

        # 验证结果
        self.assertIsInstance(result, PodDetail)
        self.assertEqual(result.name, "test-pod")
        self.assertEqual(result.namespace, "default")
        self.assertEqual(result.status, "Running")
        self.assertEqual(result.node_name, "node1")
        self.assertEqual(len(result.containers), 1)

    @patch("src.modes.k8s.resources.pod_api.client.CoreV1Api")
    def test_get_pod_details_not_found(self, mock_v1_api):
        """测试Pod不存在的情况"""
        from kubernetes.client.exceptions import ApiException

        mock_v1_instance = Mock()
        mock_v1_instance.read_namespaced_pod.side_effect = ApiException(status=404)
        mock_v1_api.return_value = mock_v1_instance

        mock_dynamic_client = Mock()
        mock_dynamic_client.client = Mock()

        result = get_pod_details(
            mock_dynamic_client, "default", "nonexistent-pod", "test-cluster"
        )

        self.assertIsNone(result)

    def test_pod_request_validation(self):
        """测试Pod请求模型验证"""
        # 测试有效请求
        request = PodRequest(
            cluster_name="test-cluster",
            namespace="default",
            pod_name="test-pod",
            force_refresh=True,
        )

        self.assertEqual(request.cluster_name, "test-cluster")
        self.assertEqual(request.namespace, "default")
        self.assertEqual(request.pod_name, "test-pod")
        self.assertTrue(request.force_refresh)

        # 测试默认值
        request_minimal = PodRequest()
        self.assertIsNone(request_minimal.cluster_name)
        self.assertIsNone(request_minimal.namespace)
        self.assertIsNone(request_minimal.pod_name)
        self.assertFalse(request_minimal.force_refresh)


if __name__ == "__main__":
    unittest.main()
