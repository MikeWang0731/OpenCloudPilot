# -*- coding: utf-8 -*-
"""
统一错误处理模块
为K8s资源管理API提供一致的错误响应格式
"""

import logging
from typing import Optional, Dict, Any
from enum import Enum
from fastapi import HTTPException
from pydantic import BaseModel
from kubernetes.client.exceptions import ApiException
import asyncio


class ErrorType(str, Enum):
    """错误类型枚举"""

    CONNECTION_ERROR = "connection_error"
    AUTH_ERROR = "auth_error"
    NOT_FOUND = "not_found"
    PROCESSING_ERROR = "processing_error"
    TIMEOUT_ERROR = "timeout_error"
    VALIDATION_ERROR = "validation_error"


class ErrorDetails(BaseModel):
    """错误详情模型"""

    cluster_name: Optional[str] = None
    resource_type: Optional[str] = None
    operation: Optional[str] = None
    namespace: Optional[str] = None
    resource_name: Optional[str] = None


class ErrorResponse(BaseModel):
    """统一错误响应模型"""

    code: int
    message: str
    error_type: ErrorType
    details: ErrorDetails


class ResourceErrorHandler:
    """资源API错误处理器"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def handle_k8s_exception(
        self,
        e: Exception,
        cluster_name: Optional[str] = None,
        resource_type: Optional[str] = None,
        operation: Optional[str] = None,
        namespace: Optional[str] = None,
        resource_name: Optional[str] = None,
    ) -> HTTPException:
        """处理Kubernetes API异常"""

        details = ErrorDetails(
            cluster_name=cluster_name,
            resource_type=resource_type,
            operation=operation,
            namespace=namespace,
            resource_name=resource_name,
        )

        # 记录错误日志
        log_prefix = (
            f"[{resource_type or '资源'}{'详情' if operation == 'detail' else '操作'}]"
        )
        if cluster_name:
            log_prefix += f"[{cluster_name}]"

        if isinstance(e, ApiException):
            # Kubernetes API异常
            if e.status == 401:
                error_type = ErrorType.AUTH_ERROR
                message = f"集群认证失败: {e.reason}"
                status_code = 401
            elif e.status == 403:
                error_type = ErrorType.AUTH_ERROR
                message = f"权限不足: {e.reason}"
                status_code = 403
            elif e.status == 404:
                error_type = ErrorType.NOT_FOUND
                message = f"资源不存在: {e.reason}"
                status_code = 404
            elif e.status >= 500:
                error_type = ErrorType.CONNECTION_ERROR
                message = f"集群连接错误: {e.reason}"
                status_code = 502
            else:
                error_type = ErrorType.PROCESSING_ERROR
                message = f"API调用失败: {e.reason}"
                status_code = 400

            self.logger.error(
                f"{log_prefix}Kubernetes API错误 (状态码: {e.status}): {e.reason}"
            )

        elif isinstance(e, asyncio.TimeoutError):
            # 超时错误
            error_type = ErrorType.TIMEOUT_ERROR
            message = "操作超时"
            status_code = 408
            self.logger.error(f"{log_prefix}操作超时")

        elif isinstance(e, ConnectionError):
            # 连接错误
            error_type = ErrorType.CONNECTION_ERROR
            message = f"连接失败: {str(e)}"
            status_code = 502
            self.logger.error(f"{log_prefix}连接错误: {str(e)}")

        else:
            # 其他处理错误
            error_type = ErrorType.PROCESSING_ERROR
            message = f"处理失败: {str(e)}"
            status_code = 500
            self.logger.error(f"{log_prefix}处理错误: {str(e)}")

        # 构建错误响应
        error_response = ErrorResponse(
            code=status_code, message=message, error_type=error_type, details=details
        )

        return HTTPException(status_code=status_code, detail=error_response.dict())

    def handle_validation_error(
        self,
        message: str,
        cluster_name: Optional[str] = None,
        resource_type: Optional[str] = None,
        operation: Optional[str] = None,
    ) -> HTTPException:
        """处理验证错误"""

        details = ErrorDetails(
            cluster_name=cluster_name, resource_type=resource_type, operation=operation
        )

        log_prefix = (
            f"[{resource_type or '资源'}{'详情' if operation == 'detail' else '操作'}]"
        )
        if cluster_name:
            log_prefix += f"[{cluster_name}]"

        self.logger.warning(f"{log_prefix}验证错误: {message}")

        error_response = ErrorResponse(
            code=400,
            message=message,
            error_type=ErrorType.VALIDATION_ERROR,
            details=details,
        )

        return HTTPException(status_code=400, detail=error_response.dict())


def with_timeout(timeout_seconds: int = 30):
    """超时装饰器"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError(f"操作超时 ({timeout_seconds}秒)")

        return wrapper

    return decorator


def create_error_handler(logger: logging.Logger) -> ResourceErrorHandler:
    """创建错误处理器实例"""
    return ResourceErrorHandler(logger)
