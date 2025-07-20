# -*- coding: utf-8 -*-
"""
Service API单元测试
"""

import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from src.modes.k8s.resources.service_api import (
    analyze_service_health,
    ServiceRequest,
    ServicePort,
    EndpointInfo,
    EndpointSubset,
    ExternalAccess,
    ServiceDetail,
)


class TestServiceAPI(unittest.TestCase):
    """Service API测试类"""

    def setUp(self):
        """测试初始化"""
        self.namespace = "test-namespace"
        self.service_name = "test-service"
        self.cluster_name = "test-cluster"

    def test_service_request_model(self):
        """测试ServiceRequest模型"""
        request = ServiceRequest(
            cluster_name="test-cluster",
            namespace="test-namespace",
            service_name="test-service",
            force_refresh=True,
        )

        self.assertEqual(request.cluster_name, "test-cluster")
        self.assertEqual(request.namespace, "test-namespace")
        self.assertEqual(request.service_name, "test-service")
        self.assertTrue(request.force_refresh)

    def test_service_port_model(self):
        """测试ServicePort模型"""
        port = ServicePort(
            name="http",
            port=80,
            target_port="8080",
            protocol="TCP",
            node_port=30080,
        )

        self.assertEqual(port.name, "http")
        self.assertEqual(port.port, 80)
        self.assertEqual(port.target_port, "8080")
        self.assertEqual(port.protocol, "TCP")
        self.assertEqual(port.node_port, 30080)

    def test_endpoint_subset_model(self):
        """测试EndpointSubset模型"""
        subset = EndpointSubset(
            addresses=[{"ip": "10.0.0.1", "hostname": "pod-1"}],
            not_ready_addresses=[{"ip": "10.0.0.2", "hostname": "pod-2"}],
            ports=[{"name": "http", "port": 8080, "protocol": "TCP"}],
        )

        self.assertEqual(len(subset.addresses), 1)
        self.assertEqual(len(subset.not_ready_addresses), 1)
        self.assertEqual(len(subset.ports), 1)
        self.assertEqual(subset.addresses[0]["ip"], "10.0.0.1")

    def test_endpoint_info_model(self):
        """测试EndpointInfo模型"""
        endpoint_info = EndpointInfo(
            name="test-service",
            namespace="test-namespace",
            subsets=[],
            ready_addresses_count=2,
            not_ready_addresses_count=1,
            total_addresses_count=3,
        )

        self.assertEqual(endpoint_info.name, "test-service")
        self.assertEqual(endpoint_info.namespace, "test-namespace")
        self.assertEqual(endpoint_info.ready_addresses_count, 2)
        self.assertEqual(endpoint_info.not_ready_addresses_count, 1)
        self.assertEqual(endpoint_info.total_addresses_count, 3)

    def test_external_access_model(self):
        """测试ExternalAccess模型"""
        external_access = ExternalAccess(
            type="LoadBalancer",
            external_ips=["203.0.113.1"],
            load_balancer_ip="203.0.113.2",
            load_balancer_ingress=[{"ip": "203.0.113.2", "hostname": None}],
        )

        self.assertEqual(external_access.type, "LoadBalancer")
        self.assertEqual(len(external_access.external_ips), 1)
        self.assertEqual(external_access.load_balancer_ip, "203.0.113.2")
        self.assertEqual(len(external_access.load_balancer_ingress), 1)

    def test_service_detail_model(self):
        """测试ServiceDetail模型"""
        service_detail = ServiceDetail(
            name="test-service",
            namespace="test-namespace",
            uid="test-uid",
            service_type="ClusterIP",
            cluster_ip="10.96.0.1",
            creation_timestamp="2023-01-01T00:00:00Z",
            age="1d",
            labels={"app": "test"},
            annotations={},
            selector={"app": "test"},
            ports=[],
            health_score=100.0,
            error_indicators=[],
            connectivity_status="Healthy",
        )

        self.assertEqual(service_detail.name, "test-service")
        self.assertEqual(service_detail.namespace, "test-namespace")
        self.assertEqual(service_detail.service_type, "ClusterIP")
        self.assertEqual(service_detail.cluster_ip, "10.96.0.1")
        self.assertEqual(service_detail.health_score, 100.0)
        self.assertEqual(service_detail.connectivity_status, "Healthy")

    def test_analyze_service_health_healthy(self):
        """测试分析健康的Service健康状态"""
        service_data = {
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": "test"},
                "ports": [{"port": 80, "targetPort": 8080}],
            }
        }

        endpoint_info = EndpointInfo(
            name="test-service",
            namespace="test-namespace",
            subsets=[],
            ready_addresses_count=3,
            not_ready_addresses_count=0,
            total_addresses_count=3,
        )

        score, status, indicators = analyze_service_health(service_data, endpoint_info)

        self.assertEqual(score, 100.0)
        self.assertEqual(status, "Healthy")
        self.assertEqual(len(indicators), 0)

    def test_analyze_service_health_no_endpoints(self):
        """测试分析没有端点的Service健康状态"""
        service_data = {
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": "test"},
                "ports": [{"port": 80, "targetPort": 8080}],
            }
        }

        endpoint_info = EndpointInfo(
            name="test-service",
            namespace="test-namespace",
            subsets=[],
            ready_addresses_count=0,
            not_ready_addresses_count=0,
            total_addresses_count=0,
        )

        score, status, indicators = analyze_service_health(service_data, endpoint_info)

        self.assertLess(score, 100.0)
        self.assertEqual(status, "Unhealthy")
        self.assertIn("没有可用的端点", indicators)

    def test_analyze_service_health_no_selector(self):
        """测试分析没有选择器的Service健康状态"""
        service_data = {
            "spec": {
                "type": "ClusterIP",
                "selector": {},  # 空选择器
                "ports": [{"port": 80, "targetPort": 8080}],
            }
        }

        endpoint_info = None

        score, status, indicators = analyze_service_health(service_data, endpoint_info)

        self.assertLess(score, 100.0)
        self.assertEqual(status, "Warning")
        self.assertIn("缺少Pod选择器", indicators)

    def test_analyze_service_health_not_ready_endpoints(self):
        """测试分析有未就绪端点的Service健康状态"""
        service_data = {
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": "test"},
                "ports": [{"port": 80, "targetPort": 8080}],
            }
        }

        endpoint_info = EndpointInfo(
            name="test-service",
            namespace="test-namespace",
            subsets=[],
            ready_addresses_count=2,
            not_ready_addresses_count=1,
            total_addresses_count=3,
        )

        score, status, indicators = analyze_service_health(service_data, endpoint_info)

        self.assertLess(score, 100.0)
        self.assertEqual(status, "Warning")
        self.assertIn("有1个端点未就绪", indicators)

    def test_analyze_service_health_loadbalancer_no_ingress(self):
        """测试分析LoadBalancer类型但没有外部IP的Service"""
        service_data = {
            "spec": {
                "type": "LoadBalancer",
                "selector": {"app": "test"},
                "ports": [{"port": 80, "targetPort": 8080}],
            },
            "status": {"loadBalancer": {"ingress": []}},  # 没有外部IP
        }

        endpoint_info = EndpointInfo(
            name="test-service",
            namespace="test-namespace",
            subsets=[],
            ready_addresses_count=2,
            not_ready_addresses_count=0,
            total_addresses_count=2,
        )

        score, status, indicators = analyze_service_health(service_data, endpoint_info)

        self.assertLess(score, 100.0)
        self.assertEqual(status, "Warning")
        self.assertIn("LoadBalancer未分配外部IP", indicators)

    def test_analyze_service_health_external_name_missing(self):
        """测试分析ExternalName类型但缺少外部名称的Service"""
        service_data = {
            "spec": {
                "type": "ExternalName",
                # 缺少externalName
            }
        }

        endpoint_info = None

        score, status, indicators = analyze_service_health(service_data, endpoint_info)

        self.assertLess(score, 100.0)
        self.assertEqual(status, "Warning")
        self.assertIn("ExternalName类型缺少外部名称", indicators)

    def test_analyze_service_health_no_ports(self):
        """测试分析没有端口配置的Service"""
        service_data = {
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": "test"},
                "ports": [],  # 没有端口
            }
        }

        endpoint_info = EndpointInfo(
            name="test-service",
            namespace="test-namespace",
            subsets=[],
            ready_addresses_count=2,
            not_ready_addresses_count=0,
            total_addresses_count=2,
        )

        score, status, indicators = analyze_service_health(service_data, endpoint_info)

        self.assertLess(score, 100.0)
        self.assertEqual(status, "Warning")
        self.assertIn("未配置服务端口", indicators)

    def test_basic_functionality(self):
        """测试基本功能"""
        # 测试模型创建
        request = ServiceRequest(
            cluster_name="test-cluster",
            namespace="test-namespace",
            service_name="test-service",
        )

        self.assertEqual(request.cluster_name, "test-cluster")
        self.assertEqual(request.namespace, "test-namespace")
        self.assertEqual(request.service_name, "test-service")

        # 测试健康状态分析
        service_data = {
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": "test"},
                "ports": [{"port": 80, "targetPort": 8080}],
            }
        }

        endpoint_info = EndpointInfo(
            name="test-service",
            namespace="test-namespace",
            subsets=[],
            ready_addresses_count=3,
            not_ready_addresses_count=0,
            total_addresses_count=3,
        )

        score, status, indicators = analyze_service_health(service_data, endpoint_info)
        self.assertEqual(score, 100.0)
        self.assertEqual(status, "Healthy")
        self.assertEqual(len(indicators), 0)


if __name__ == "__main__":
    unittest.main()
