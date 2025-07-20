# -*- coding: utf-8 -*-
"""
Deployment API单元测试
"""

import unittest
from unittest.mock import Mock
from datetime import datetime, timezone

from src.modes.k8s.resources.deployment_api import (
    calculate_deployment_health_score,
    DeploymentRequest,
    ReplicaInfo,
    DeploymentStrategy,
    RolloutStatus,
)


class TestDeploymentAPI(unittest.TestCase):
    """Deployment API测试类"""

    def setUp(self):
        """测试初始化"""
        self.namespace = "test-namespace"
        self.deployment_name = "test-deployment"
        self.cluster_name = "test-cluster"

    def test_deployment_request_model(self):
        """测试DeploymentRequest模型"""
        request = DeploymentRequest(
            cluster_name="test-cluster",
            namespace="test-namespace",
            deployment_name="test-deployment",
            force_refresh=True,
        )

        self.assertEqual(request.cluster_name, "test-cluster")
        self.assertEqual(request.namespace, "test-namespace")
        self.assertEqual(request.deployment_name, "test-deployment")
        self.assertTrue(request.force_refresh)

    def test_replica_info_model(self):
        """测试ReplicaInfo模型"""
        replica_info = ReplicaInfo(
            desired=3, current=3, available=2, ready=2, updated=3, unavailable=1
        )

        self.assertEqual(replica_info.desired, 3)
        self.assertEqual(replica_info.current, 3)
        self.assertEqual(replica_info.available, 2)
        self.assertEqual(replica_info.ready, 2)
        self.assertEqual(replica_info.updated, 3)
        self.assertEqual(replica_info.unavailable, 1)

    def test_deployment_strategy_model(self):
        """测试DeploymentStrategy模型"""
        strategy = DeploymentStrategy(
            type="RollingUpdate", max_surge="25%", max_unavailable="25%"
        )

        self.assertEqual(strategy.type, "RollingUpdate")
        self.assertEqual(strategy.max_surge, "25%")
        self.assertEqual(strategy.max_unavailable, "25%")

    def test_rollout_status_model(self):
        """测试RolloutStatus模型"""
        rollout_status = RolloutStatus(
            observed_generation=2,
            current_revision="2",
            update_revision="2",
            collision_count=0,
            conditions=[],
        )

        self.assertEqual(rollout_status.observed_generation, 2)
        self.assertEqual(rollout_status.current_revision, "2")
        self.assertEqual(rollout_status.update_revision, "2")
        self.assertEqual(rollout_status.collision_count, 0)
        self.assertEqual(len(rollout_status.conditions), 0)

    def test_calculate_deployment_health_score_healthy(self):
        """测试计算健康的Deployment健康分数"""
        deployment_data = {
            "status": {
                "replicas": 3,
                "availableReplicas": 3,
                "readyReplicas": 3,
                "updatedReplicas": 3,
                "conditions": [
                    {"type": "Available", "status": "True"},
                    {
                        "type": "Progressing",
                        "status": "True",
                        "reason": "NewReplicaSetAvailable",
                    },
                ],
            }
        }

        replicasets = []
        result = calculate_deployment_health_score(deployment_data, replicasets)

        self.assertEqual(result, 100.0)

    def test_calculate_deployment_health_score_degraded(self):
        """测试计算降级的Deployment健康分数"""
        deployment_data = {
            "status": {
                "replicas": 3,
                "availableReplicas": 1,  # 只有1个可用
                "readyReplicas": 1,  # 只有1个就绪
                "updatedReplicas": 2,  # 2个已更新
                "conditions": [
                    {"type": "Available", "status": "False"},  # 不可用
                    {"type": "Progressing", "status": "False"},  # 进度停滞
                ],
            }
        }

        replicasets = []
        result = calculate_deployment_health_score(deployment_data, replicasets)

        # 应该扣分：可用性不足50%(-50), 就绪性不足50%(-30), 不可用(-25), 进度停滞(-20), 更新未完成(-15)
        # 但分数不会低于0
        self.assertLess(result, 100.0)
        self.assertGreaterEqual(result, 0.0)

    def test_basic_functionality(self):
        """测试基本功能"""
        # 测试模型创建
        request = DeploymentRequest(
            cluster_name="test-cluster",
            namespace="test-namespace",
            deployment_name="test-deployment",
        )

        self.assertEqual(request.cluster_name, "test-cluster")
        self.assertEqual(request.namespace, "test-namespace")
        self.assertEqual(request.deployment_name, "test-deployment")

        # 测试健康分数计算
        deployment_data = {
            "status": {
                "replicas": 3,
                "availableReplicas": 3,
                "readyReplicas": 3,
                "updatedReplicas": 3,
                "conditions": [
                    {"type": "Available", "status": "True"},
                    {"type": "Progressing", "status": "True"},
                ],
            }
        }

        score = calculate_deployment_health_score(deployment_data, [])
        self.assertEqual(score, 100.0)


if __name__ == "__main__":
    unittest.main()
