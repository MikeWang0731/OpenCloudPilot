# -*- coding: utf-8 -*-
"""
日志获取API
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from kubernetes import client

from src.core.k8s_utils import K8sUtils
from src.core.resource_parser import ResourceParser
from src.core.pagination import TimeWindowRequest, LimitRequest, get_paginator


class LogRequest(BaseModel):
    """日志请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: str = Field(..., description="命名空间")
    pod_name: str = Field(..., description="Pod名称")
    container_name: Optional[str] = Field(
        None, description="容器名称，为空则获取第一个容器的日志"
    )
    since_time: Optional[datetime] = Field(None, description="开始时间")
    until_time: Optional[datetime] = Field(None, description="结束时间")
    last_hours: Optional[int] = Field(
        None, ge=1, le=168, description="最近N小时，最大7天"
    )
    last_minutes: Optional[int] = Field(
        None, ge=1, le=1440, description="最近N分钟，最大24小时"
    )
    tail_lines: Optional[int] = Field(
        100, ge=1, le=10000, description="获取最后N行日志，默认100行，最大10000行"
    )
    max_lines: Optional[int] = Field(
        1000, ge=1, le=10000, description="最大返回行数，默认1000行"
    )
    previous: Optional[bool] = Field(False, description="是否获取前一个容器实例的日志")
    follow: Optional[bool] = Field(False, description="是否持续跟踪日志")
    timestamps: Optional[bool] = Field(True, description="是否包含时间戳")
    include_error_only: Optional[bool] = Field(False, description="是否只包含错误日志")


class LogEntry(BaseModel):
    """日志条目模型"""

    timestamp: Optional[str] = Field(None, description="时间戳")
    container_name: str = Field(..., description="容器名称")
    message: str = Field(..., description="日志消息")
    level: Optional[str] = Field(None, description="日志级别")
    severity: Optional[str] = Field(None, description="严重程度")
    is_error: bool = Field(False, description="是否为错误日志")
    line_number: int = Field(..., description="行号")


class LogResponse(BaseModel):
    """日志响应模型"""

    pod_name: str = Field(..., description="Pod名称")
    namespace: str = Field(..., description="命名空间")
    container_name: str = Field(..., description="容器名称")
    total_lines: int = Field(..., description="总行数")
    entries: List[LogEntry] = Field(default_factory=list, description="日志条目列表")
    error_count: int = Field(0, description="错误日志数量")
    warning_count: int = Field(0, description="警告日志数量")
    has_more: bool = Field(False, description="是否还有更多日志")
    query_info: Dict[str, Any] = Field(default_factory=dict, description="查询信息")


class LogListResponse(BaseModel):
    """日志列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[LogResponse] = Field(None, description="日志数据")


# 日志处理函数


def detect_error_patterns(log_message: str) -> Dict[str, Any]:
    """
    检测日志中的错误模式

    Args:
        log_message: 日志消息

    Returns:
        Dict[str, Any]: 错误检测结果
    """
    logger = logging.getLogger("cloudpilot.logs_api")

    try:
        # 错误关键词模式
        error_patterns = [
            (r"\b(error|err|exception|fail|failed|failure)\b", "error"),
            (r"\b(warn|warning|deprecated)\b", "warning"),
            (r"\b(fatal|critical|panic)\b", "fatal"),
            (r"\b(debug|trace)\b", "debug"),
            (r"\b(info|information)\b", "info"),
        ]

        # HTTP状态码模式
        http_error_patterns = [
            (r"\b[45]\d{2}\b", "http_error"),  # 4xx, 5xx状态码
        ]

        # 异常堆栈模式
        stack_trace_patterns = [
            (r"at\s+[\w\.]+\(.*:\d+\)", "stack_trace"),
            (r"Traceback\s*\(most recent call last\)", "python_traceback"),
            (r"Exception in thread", "java_exception"),
        ]

        result = {
            "level": "info",
            "severity": "normal",
            "is_error": False,
            "patterns_found": [],
        }

        message_lower = log_message.lower()

        # 检测日志级别
        for pattern, level in error_patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                result["level"] = level
                result["patterns_found"].append(level)
                if level in ["error", "fatal"]:
                    result["is_error"] = True
                    result["severity"] = "high" if level == "fatal" else "medium"
                elif level == "warning":
                    result["severity"] = "low"
                break

        # 检测HTTP错误
        for pattern, error_type in http_error_patterns:
            if re.search(pattern, log_message):
                result["patterns_found"].append(error_type)
                result["is_error"] = True
                result["severity"] = "medium"

        # 检测异常堆栈
        for pattern, trace_type in stack_trace_patterns:
            if re.search(pattern, log_message):
                result["patterns_found"].append(trace_type)
                result["is_error"] = True
                result["severity"] = "high"

        return result

    except Exception as e:
        logger.error("检测错误模式失败: %s", str(e))
        return {
            "level": "info",
            "severity": "normal",
            "is_error": False,
            "patterns_found": [],
        }


def parse_log_entries(
    raw_logs: str, container_name: str, include_timestamps: bool = True
) -> List[LogEntry]:
    """
    解析原始日志为结构化条目

    Args:
        raw_logs: 原始日志字符串
        container_name: 容器名称
        include_timestamps: 是否包含时间戳

    Returns:
        List[LogEntry]: 日志条目列表
    """
    logger = logging.getLogger("cloudpilot.logs_api")

    try:
        if not raw_logs:
            return []

        lines = raw_logs.strip().split("\n")
        entries = []

        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue

            # 尝试提取时间戳
            timestamp = None
            message = line

            if include_timestamps:
                # 匹配常见的时间戳格式
                timestamp_patterns = [
                    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+(.*)$",  # ISO格式
                    r"^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.*)$",  # 标准格式
                    r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(.*)$",  # syslog格式
                ]

                for pattern in timestamp_patterns:
                    match = re.match(pattern, line)
                    if match:
                        timestamp = match.group(1)
                        message = match.group(2)
                        break

            # 检测错误模式
            error_info = detect_error_patterns(message)

            # 创建日志条目
            entry = LogEntry(
                timestamp=timestamp,
                container_name=container_name,
                message=message,
                level=error_info["level"],
                severity=error_info["severity"],
                is_error=error_info["is_error"],
                line_number=line_num,
            )

            entries.append(entry)

        logger.debug("成功解析%d行日志", len(entries))
        return entries

    except Exception as e:
        logger.error("解析日志条目失败: %s", str(e))
        return []


def get_pod_logs(
    k8s_client,
    namespace: str,
    pod_name: str,
    container_name: Optional[str] = None,
    since_time: Optional[datetime] = None,
    until_time: Optional[datetime] = None,
    tail_lines: Optional[int] = 50,
    previous: bool = False,
    timestamps: bool = True,
    cluster_name: str = "current",
) -> Optional[LogResponse]:
    """
    获取Pod日志

    Args:
        k8s_client: Kubernetes客户端
        namespace: 命名空间
        pod_name: Pod名称
        container_name: 容器名称
        since_time: 开始时间
        until_time: 结束时间
        tail_lines: 获取行数
        previous: 是否获取前一个实例
        timestamps: 是否包含时间戳
        cluster_name: 集群名称

    Returns:
        Optional[LogResponse]: 日志响应，如果失败则返回None
    """
    logger = logging.getLogger("cloudpilot.logs_api")

    try:
        logger.info(
            "[日志获取][%s]开始获取Pod日志: %s/%s, 容器: %s",
            cluster_name,
            namespace,
            pod_name,
            container_name or "默认",
        )

        # 获取Pod信息以确定容器
        v1 = client.CoreV1Api(k8s_client)

        try:
            pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        except client.ApiException as e:
            if e.status == 404:
                logger.warning(
                    "[日志获取][%s]Pod不存在: %s/%s", cluster_name, namespace, pod_name
                )
                return None
            raise

        # 确定容器名称
        if not container_name:
            if pod.spec.containers:
                container_name = pod.spec.containers[0].name
            else:
                logger.error(
                    "[日志获取][%s]Pod没有容器: %s/%s",
                    cluster_name,
                    namespace,
                    pod_name,
                )
                return None

        # 验证容器是否存在
        container_names = [c.name for c in pod.spec.containers]
        if container_name not in container_names:
            logger.error(
                "[日志获取][%s]容器不存在: %s/%s, 容器: %s, 可用容器: %s",
                cluster_name,
                namespace,
                pod_name,
                container_name,
                container_names,
            )
            return None

        # 构建日志查询参数
        log_params = {
            "name": pod_name,
            "namespace": namespace,
            "container": container_name,
            "timestamps": timestamps,
            "previous": previous,
        }

        # 添加时间过滤
        if since_time:
            log_params["since_seconds"] = int(
                (datetime.now(timezone.utc) - since_time).total_seconds()
            )

        # 添加行数限制
        if tail_lines and tail_lines > 0:
            log_params["tail_lines"] = min(tail_lines, 1000)  # 最大1000行

        # 获取日志
        try:
            raw_logs = v1.read_namespaced_pod_log(**log_params)
        except client.ApiException as e:
            logger.error(
                "[日志获取][%s]获取日志失败: %s/%s, 容器: %s, 状态码: %d",
                cluster_name,
                namespace,
                pod_name,
                container_name,
                e.status,
            )
            return None

        # 解析日志条目
        entries = parse_log_entries(raw_logs, container_name, timestamps)

        # 时间过滤（如果指定了until_time）
        if until_time and entries:
            filtered_entries = []
            for entry in entries:
                if entry.timestamp:
                    try:
                        # 尝试解析时间戳
                        entry_time = datetime.fromisoformat(
                            entry.timestamp.replace("Z", "+00:00")
                        )
                        if entry_time <= until_time:
                            filtered_entries.append(entry)
                    except:
                        # 如果时间戳解析失败，保留条目
                        filtered_entries.append(entry)
                else:
                    filtered_entries.append(entry)
            entries = filtered_entries

        # 统计错误和警告
        error_count = sum(1 for entry in entries if entry.is_error)
        warning_count = sum(1 for entry in entries if entry.level == "warning")

        # 构建响应
        log_response = LogResponse(
            pod_name=pod_name,
            namespace=namespace,
            container_name=container_name,
            total_lines=len(entries),
            entries=entries,
            error_count=error_count,
            warning_count=warning_count,
            has_more=len(entries) == (tail_lines or 100),
            query_info={
                "since_time": since_time.isoformat() if since_time else None,
                "until_time": until_time.isoformat() if until_time else None,
                "tail_lines": tail_lines,
                "previous": previous,
                "timestamps": timestamps,
            },
        )

        logger.info(
            "[日志获取][%s]成功获取Pod日志: %s/%s, 容器: %s, 行数: %d, 错误: %d",
            cluster_name,
            namespace,
            pod_name,
            container_name,
            len(entries),
            error_count,
        )

        return log_response

    except Exception as e:
        logger.error(
            "[日志获取][%s]获取Pod日志失败: %s/%s, 容器: %s, 错误: %s",
            cluster_name,
            namespace,
            pod_name,
            container_name,
            str(e),
        )
        return None


def create_server_logs_router(server_mode_instance) -> APIRouter:
    """创建Server模式的日志API路由"""
    router = APIRouter(
        prefix="/k8s/resources/logs", tags=["K8s Logs Resources - Server"]
    )

    @router.post("/pod", response_model=LogListResponse)
    async def get_pod_logs_endpoint(request: LogRequest):
        """获取Pod日志"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[日志获取][%s]开始获取Pod日志: %s/%s",
                cluster_name,
                request.namespace,
                request.pod_name,
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取日志
            log_response = get_pod_logs(
                dynamic_client.client,
                request.namespace,
                request.pod_name,
                request.container_name,
                request.since_time,
                request.until_time,
                request.tail_lines,
                request.previous,
                request.timestamps,
                cluster_name,
            )

            if not log_response:
                return {
                    "code": 404,
                    "message": f"无法获取Pod日志: {request.namespace}/{request.pod_name}",
                }

            server_mode_instance.logger.info(
                "[日志获取][%s]成功获取Pod日志: %s/%s, 行数: %d",
                cluster_name,
                request.namespace,
                request.pod_name,
                log_response.total_lines,
            )

            return {"code": 200, "data": log_response}

        except Exception as e:
            server_mode_instance.logger.error(
                "[日志获取][%s]获取Pod日志失败: %s/%s, 错误: %s",
                cluster_name,
                request.namespace,
                request.pod_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Pod日志失败: {str(e)}"}

    @router.post("/container", response_model=LogListResponse)
    async def get_container_logs_endpoint(request: LogRequest):
        """获取特定容器日志"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        if not request.container_name:
            return {"code": 400, "message": "container_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[日志获取][%s]开始获取容器日志: %s/%s, 容器: %s",
                cluster_name,
                request.namespace,
                request.pod_name,
                request.container_name,
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取日志
            log_response = get_pod_logs(
                dynamic_client.client,
                request.namespace,
                request.pod_name,
                request.container_name,
                request.since_time,
                request.until_time,
                request.tail_lines,
                request.previous,
                request.timestamps,
                cluster_name,
            )

            if not log_response:
                return {
                    "code": 404,
                    "message": f"无法获取容器日志: {request.namespace}/{request.pod_name}/{request.container_name}",
                }

            server_mode_instance.logger.info(
                "[日志获取][%s]成功获取容器日志: %s/%s, 容器: %s, 行数: %d",
                cluster_name,
                request.namespace,
                request.pod_name,
                request.container_name,
                log_response.total_lines,
            )

            return {"code": 200, "data": log_response}

        except Exception as e:
            server_mode_instance.logger.error(
                "[日志获取][%s]获取容器日志失败: %s/%s, 容器: %s, 错误: %s",
                cluster_name,
                request.namespace,
                request.pod_name,
                request.container_name,
                str(e),
            )
            return {"code": 500, "message": f"获取容器日志失败: {str(e)}"}

    return router


def create_instant_logs_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的日志API路由"""
    router = APIRouter(
        prefix="/k8s/resources/logs", tags=["K8s Logs Resources - Instant"]
    )

    @router.post("/pod", response_model=LogListResponse)
    async def get_pod_logs_endpoint(request: LogRequest):
        """获取Pod日志"""
        try:
            instant_mode_instance.logger.info(
                "[日志获取][当前集群]开始获取Pod日志: %s/%s",
                request.namespace,
                request.pod_name,
            )

            # 获取日志
            log_response = get_pod_logs(
                instant_mode_instance.k8s_client,
                request.namespace,
                request.pod_name,
                request.container_name,
                request.since_time,
                request.until_time,
                request.tail_lines,
                request.previous,
                request.timestamps,
                "当前集群",
            )

            if not log_response:
                return {
                    "code": 404,
                    "message": f"无法获取Pod日志: {request.namespace}/{request.pod_name}",
                }

            instant_mode_instance.logger.info(
                "[日志获取][当前集群]成功获取Pod日志: %s/%s, 行数: %d",
                request.namespace,
                request.pod_name,
                log_response.total_lines,
            )

            return {"code": 200, "data": log_response}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[日志获取][当前集群]获取Pod日志失败: %s/%s, 错误: %s",
                request.namespace,
                request.pod_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Pod日志失败: {str(e)}"}

    @router.post("/container", response_model=LogListResponse)
    async def get_container_logs_endpoint(request: LogRequest):
        """获取特定容器日志"""
        if not request.container_name:
            return {"code": 400, "message": "container_name参数必需"}

        try:
            instant_mode_instance.logger.info(
                "[日志获取][当前集群]开始获取容器日志: %s/%s, 容器: %s",
                request.namespace,
                request.pod_name,
                request.container_name,
            )

            # 获取日志
            log_response = get_pod_logs(
                instant_mode_instance.k8s_client,
                request.namespace,
                request.pod_name,
                request.container_name,
                request.since_time,
                request.until_time,
                request.tail_lines,
                request.previous,
                request.timestamps,
                "当前集群",
            )

            if not log_response:
                return {
                    "code": 404,
                    "message": f"无法获取容器日志: {request.namespace}/{request.pod_name}/{request.container_name}",
                }

            instant_mode_instance.logger.info(
                "[日志获取][当前集群]成功获取容器日志: %s/%s, 容器: %s, 行数: %d",
                request.namespace,
                request.pod_name,
                request.container_name,
                log_response.total_lines,
            )

            return {"code": 200, "data": log_response}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[日志获取][当前集群]获取容器日志失败: %s/%s, 容器: %s, 错误: %s",
                request.namespace,
                request.pod_name,
                request.container_name,
                str(e),
            )
            return {"code": 500, "message": f"获取容器日志失败: {str(e)}"}

    return router
