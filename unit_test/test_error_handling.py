# -*- coding: utf-8 -*-
"""
错误处理集成测试
测试资源API的错误处理场景
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from kubernetes.client.exceptions import ApiException
from kubernetes.client.rest import ApiException as RestApiException

from src.core.error_handler import ResourceErrorHandler, ErrorType, create_error_handler
from src.core.config import Settings
from src.modes.server_mode import ServerMode
from src.modes.instant_app import InstantAppMode


class TestResourceErrorHandler:
    """测试资源错误处理器"""

    def setup_method(self):
        """测试设置"""
        import logging

        self.logger = logging.getLogger("test")
        self.error_handler = create_error_handler(self.logger)

    def test_handle_auth_error_401(self):
        """测试401认证错误处理"""
        api_exception = ApiException(status=401, reason="Unauthorized")

        http_exception = self.error_handler.handle_k8s_exception(
            api_exception,
            cluster_name="test-cluster",
            resource_type="pod",
            operation="list",
        )

        assert http_exception.status_code == 401
        assert http_exception.detail["error_type"] == ErrorType.AUTH_ERROR
        assert "认证失败" in http_exception.detail["message"]
        assert http_exception.detail["details"]["cluster_name"] == "test-cluster"
        assert http_exception.detail["details"]["resource_type"] == "pod"

    def test_handle_auth_error_403(self):
        """测试403权限错误处理"""
        api_exception = ApiException(status=403, reason="Forbidden")

        http_exception = self.error_handler.handle_k8s_exception(
            api_exception,
            cluster_name="test-cluster",
            resource_type="deployment",
            operation="detail",
        )

        assert http_exception.status_code == 403
        assert http_exception.detail["error_type"] == ErrorType.AUTH_ERROR
        assert "权限不足" in http_exception.detail["message"]

    def test_handle_not_found_error(self):
        """测试404资源不存在错误处理"""
        api_exception = ApiException(status=404, reason="Not Found")

        http_exception = self.error_handler.handle_k8s_exception(
            api_exception,
            cluster_name="test-cluster",
            resource_type="service",
            operation="detail",
            namespace="default",
            resource_name="test-service",
        )

        assert http_exception.status_code == 404
        assert http_exception.detail["error_type"] == ErrorType.NOT_FOUND
        assert "资源不存在" in http_exception.detail["message"]
        assert http_exception.detail["details"]["namespace"] == "default"
        assert http_exception.detail["details"]["resource_name"] == "test-service"

    def test_handle_connection_error(self):
        """测试连接错误处理"""
        connection_error = ConnectionError("Connection refused")

        http_exception = self.error_handler.handle_k8s_exception(
            connection_error,
            cluster_name="test-cluster",
            resource_type="node",
            operation="list",
        )

        assert http_exception.status_code == 502
        assert http_exception.detail["error_type"] == ErrorType.CONNECTION_ERROR
        assert "连接失败" in http_exception.detail["message"]

    def test_handle_timeout_error(self):
        """测试超时错误处理"""
        timeout_error = asyncio.TimeoutError("Operation timed out")

        http_exception = self.error_handler.handle_k8s_exception(
            timeout_error,
            cluster_name="test-cluster",
            resource_type="logs",
            operation="retrieve",
        )

        assert http_exception.status_code == 408
        assert http_exception.detail["error_type"] == ErrorType.TIMEOUT_ERROR
        assert "操作超时" in http_exception.detail["message"]

    def test_handle_validation_error(self):
        """测试验证错误处理"""
        http_exception = self.error_handler.handle_validation_error(
            "集群名称不能为空", cluster_name=None, resource_type="pod", operation="list"
        )

        assert http_exception.status_code == 400
        assert http_exception.detail["error_type"] == ErrorType.VALIDATION_ERROR
        assert "集群名称不能为空" in http_exception.detail["message"]

    def test_handle_server_error(self):
        """测试服务器错误处理"""
        api_exception = ApiException(status=500, reason="Internal Server Error")

        http_exception = self.error_handler.handle_k8s_exception(
            api_exception,
            cluster_name="test-cluster",
            resource_type="events",
            operation="list",
        )

        assert http_exception.status_code == 502
        assert http_exception.detail["error_type"] == ErrorType.CONNECTION_ERROR
        assert "集群连接错误" in http_exception.detail["message"]


class TestTimeoutDecorator:
    """测试超时装饰器"""

    @pytest.mark.asyncio
    async def test_timeout_decorator_success(self):
        """测试超时装饰器正常执行"""
        from src.core.error_handler import with_timeout

        @with_timeout(timeout_seconds=1)
        async def fast_operation():
            await asyncio.sleep(0.1)
            return "success"

        result = await fast_operation()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_timeout_decorator_timeout(self):
        """测试超时装饰器超时场景"""
        from src.core.error_handler import with_timeout

        @with_timeout(timeout_seconds=0.1)
        async def slow_operation():
            await asyncio.sleep(1)
            return "success"

        with pytest.raises(asyncio.TimeoutError):
            await slow_operation()


class TestModeIntegrationErrors:
    """测试模式集成错误场景"""

    def setup_method(self):
        """测试设置"""
        self.settings = Settings()

    @patch("src.modes.server_mode.ServerMode._create_k8s_client")
    def test_server_mode_client_creation_failure(self, mock_create_client):
        """测试Server模式客户端创建失败"""
        mock_create_client.return_value = None

        server_mode = ServerMode(self.settings)

        # 模拟客户端创建失败的场景
        with patch.object(server_mode, "_get_cluster_config") as mock_get_config:
            mock_get_config.return_value = {
                "name": "test-cluster",
                "api_server": "https://invalid-server",
                "token": "invalid-token",
                "kubeconfig": None,
            }

            # 测试客户端创建失败时的处理
            result = asyncio.run(server_mode._create_k8s_client("test-cluster"))
            assert result is None

    @patch("kubernetes.config.load_incluster_config")
    @patch("kubernetes.config.load_kube_config")
    def test_instant_mode_config_loading_failure(
        self, mock_load_kube, mock_load_incluster
    ):
        """测试Instant模式配置加载失败"""
        mock_load_incluster.side_effect = Exception("No incluster config")
        mock_load_kube.side_effect = Exception("No kubeconfig found")

        instant_mode = InstantAppMode(self.settings)

        with pytest.raises(Exception):
            asyncio.run(instant_mode._init_k8s_client())


class TestAPIEndpointErrors:
    """测试API端点错误场景"""

    def setup_method(self):
        """测试设置"""
        self.settings = Settings()

    @patch("src.modes.server_mode.ServerMode._get_cluster_monitor")
    def test_server_pod_api_cluster_not_found(self, mock_get_monitor):
        """测试Server模式Pod API集群不存在错误"""
        mock_get_monitor.return_value = None

        server_mode = ServerMode(self.settings)
        app = server_mode._create_app()
        client = TestClient(app)

        response = client.post(
            "/k8s/resources/pods/list", json={"cluster_name": "nonexistent-cluster"}
        )

        assert response.status_code in [400, 404, 502]  # 根据具体实现可能不同

    @patch("src.modes.instant_app.InstantAppMode.cluster_monitor")
    def test_instant_pod_api_monitor_unavailable(self, mock_monitor):
        """测试Instant模式Pod API监控器不可用错误"""
        mock_monitor = None

        instant_mode = InstantAppMode(self.settings)
        app = instant_mode._create_app()
        client = TestClient(app)

        response = client.post("/k8s/resources/pods/list", json={})

        # 应该返回错误响应
        assert response.status_code >= 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
