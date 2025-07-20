# -*- coding: utf-8 -*-
"""
事件获取API
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from kubernetes import client

from src.core.k8s_utils import K8sUtils
from src.core.resource_parser import ResourceParser
from src.core.pagination import (
    TimeWindowRequest,
    LimitRequest,
    PaginationRequest,
    get_paginator,
)


class EventRequest(BaseModel):
    """事件请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    resource_type: Optional[str] = Field(
        None, description="资源类型 (Pod, Deployment等)"
    )
    resource_name: Optional[str] = Field(None, description="资源名称")
    since_time: Optional[datetime] = Field(None, description="开始时间")
    until_time: Optional[datetime] = Field(None, description="结束时间")
    last_hours: Optional[int] = Field(
        24, ge=1, le=168, description="最近N小时，默认24小时，最大7天"
    )
    last_minutes: Optional[int] = Field(
        None, ge=1, le=1440, description="最近N分钟，最大24小时"
    )
    limit: Optional[int] = Field(
        200, ge=1, le=5000, description="返回事件数量限制，默认200，最大5000"
    )
    event_type: Optional[str] = Field(
        None, description="事件类型过滤 (Normal, Warning)"
    )

    # 分页参数
    page: int = Field(1, ge=1, description="页码，从1开始")
    page_size: int = Field(50, ge=1, le=500, description="每页大小，最大500")
    sort_by: Optional[str] = Field("first_timestamp", description="排序字段")
    sort_order: Optional[str] = Field("desc", description="排序顺序 (asc/desc)")


class EventDetail(BaseModel):
    """事件详情模型"""

    name: str = Field(..., description="事件名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="事件UID")
    type: str = Field(..., description="事件类型 (Normal, Warning)")
    reason: str = Field(..., description="事件原因")
    message: str = Field(..., description="事件消息")
    source_component: Optional[str] = Field(None, description="来源组件")
    source_host: Optional[str] = Field(None, description="来源主机")
    involved_object: Dict[str, Any] = Field(
        default_factory=dict, description="相关对象信息"
    )
    first_timestamp: Optional[str] = Field(None, description="首次发生时间")
    last_timestamp: Optional[str] = Field(None, description="最后发生时间")
    count: int = Field(1, description="发生次数")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    severity: str = Field("normal", description="严重程度 (low, medium, high)")
    category: str = Field("general", description="事件分类")
    is_recurring: bool = Field(False, description="是否为重复事件")


class EventSummary(BaseModel):
    """事件摘要模型"""

    total_events: int = Field(0, description="总事件数")
    warning_events: int = Field(0, description="警告事件数")
    normal_events: int = Field(0, description="正常事件数")
    error_events: int = Field(0, description="错误事件数")
    recurring_events: int = Field(0, description="重复事件数")
    recent_events: int = Field(0, description="最近事件数")
    categories: Dict[str, int] = Field(default_factory=dict, description="分类统计")
    top_reasons: List[Dict[str, Any]] = Field(
        default_factory=list, description="主要原因统计"
    )


class EventResponse(BaseModel):
    """事件响应模型"""

    namespace: Optional[str] = Field(None, description="命名空间")
    resource_type: Optional[str] = Field(None, description="资源类型")
    resource_name: Optional[str] = Field(None, description="资源名称")
    events: List[EventDetail] = Field(default_factory=list, description="事件列表")
    summary: EventSummary = Field(
        default_factory=EventSummary, description="事件摘要"
    )
    query_info: Dict[str, Any] = Field(default_factory=dict, description="查询信息")


class EventListResponse(BaseModel):
    """事件列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[EventResponse] = Field(None, description="事件数据")


# 事件处理函数


def categorize_events(events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    按类型和严重程度对事件进行分类

    Args:
        events: 事件列表

    Returns:
        Dict[str, List[Dict[str, Any]]]: 分类后的事件
    """
    logger = logging.getLogger("cloudpilot.events_api")

    try:
        categories = {
            "scheduling": [],  # 调度相关
            "resource": [],  # 资源相关
            "network": [],  # 网络相关
            "storage": [],  # 存储相关
            "security": [],  # 安全相关
            "lifecycle": [],  # 生命周期相关
            "general": [],  # 一般事件
        }

        # 分类规则
        category_rules = {
            "scheduling": ["FailedScheduling", "Scheduled", "Preempted"],
            "resource": ["FailedMount", "VolumeMount", "OutOfMemory", "Evicted"],
            "network": ["NetworkNotReady", "DNSConfigForming"],
            "storage": ["FailedAttachVolume", "SuccessfulAttachVolume", "VolumeMount"],
            "security": ["FailedCreatePodSandBox", "SecurityContextDeny"],
            "lifecycle": ["Created", "Started", "Killing", "Pulled", "Failed"],
        }

        for event in events:
            reason = event.get("reason", "")
            categorized = False

            for category, reasons in category_rules.items():
                if any(rule in reason for rule in reasons):
                    categories[category].append(event)
                    categorized = True
                    break

            if not categorized:
                categories["general"].append(event)

        logger.debug(
            "事件分类完成，各类别数量: %s", {k: len(v) for k, v in categories.items()}
        )
        return categories

    except Exception as e:
        logger.error("事件分类失败: %s", str(e))
        return {"general": events}


def analyze_event_patterns(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    分析事件模式以识别重复问题

    Args:
        events: 事件列表

    Returns:
        Dict[str, Any]: 模式分析结果
    """
    logger = logging.getLogger("cloudpilot.events_api")

    try:
        patterns = {
            "recurring_events": [],
            "error_patterns": [],
            "resource_issues": [],
            "timing_patterns": {},
        }

        # 按原因分组统计
        reason_counts = {}
        reason_events = {}

        for event in events:
            reason = event.get("reason", "Unknown")
            count = event.get("count", 1)

            if reason not in reason_counts:
                reason_counts[reason] = 0
                reason_events[reason] = []

            reason_counts[reason] += count
            reason_events[reason].append(event)

        # 识别重复事件 (出现次数 > 5 或 count > 10)
        for reason, total_count in reason_counts.items():
            if total_count > 10 or len(reason_events[reason]) > 5:
                patterns["recurring_events"].append(
                    {
                        "reason": reason,
                        "total_count": total_count,
                        "event_count": len(reason_events[reason]),
                        "sample_event": reason_events[reason][0],
                    }
                )

        # 识别错误模式
        error_keywords = ["Failed", "Error", "Warning", "Timeout", "Denied"]
        for event in events:
            reason = event.get("reason", "")
            message = event.get("message", "")

            if any(
                keyword in reason or keyword in message for keyword in error_keywords
            ):
                patterns["error_patterns"].append(
                    {
                        "reason": reason,
                        "message": message,
                        "type": event.get("type", ""),
                        "object": event.get("involvedObject", {}).get("name", ""),
                    }
                )

        # 识别资源相关问题
        resource_keywords = ["OutOfMemory", "Evicted", "FailedMount", "DiskPressure"]
        for event in events:
            reason = event.get("reason", "")
            if any(keyword in reason for keyword in resource_keywords):
                patterns["resource_issues"].append(
                    {
                        "reason": reason,
                        "object": event.get("involvedObject", {}),
                        "message": event.get("message", ""),
                    }
                )

        logger.debug(
            "事件模式分析完成，发现 %d 个重复事件，%d 个错误模式",
            len(patterns["recurring_events"]),
            len(patterns["error_patterns"]),
        )

        return patterns

    except Exception as e:
        logger.error("事件模式分析失败: %s", str(e))
        return {
            "recurring_events": [],
            "error_patterns": [],
            "resource_issues": [],
            "timing_patterns": {},
        }


def get_resource_events(
    k8s_client,
    namespace: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    since_time: Optional[datetime] = None,
    until_time: Optional[datetime] = None,
    limit: int = 100,
    event_type: Optional[str] = None,
    cluster_name: str = "current",
) -> Optional[EventResponse]:
    """
    获取资源相关事件

    Args:
        k8s_client: Kubernetes客户端
        namespace: 命名空间
        resource_type: 资源类型
        resource_name: 资源名称
        since_time: 开始时间
        until_time: 结束时间
        limit: 返回数量限制
        event_type: 事件类型过滤
        cluster_name: 集群名称

    Returns:
        Optional[EventResponse]: 事件响应，如果失败则返回None
    """
    logger = logging.getLogger("cloudpilot.events_api")

    try:
        logger.info(
            "[事件查询][%s]开始获取事件: 命名空间=%s, 资源类型=%s, 资源名称=%s",
            cluster_name,
            namespace or "所有",
            resource_type or "所有",
            resource_name or "所有",
        )

        # 获取事件列表
        v1 = client.CoreV1Api(k8s_client.client)
        k8s_utils = K8sUtils(k8s_client)  # 用于时间格式化

        if namespace:
            event_list = v1.list_namespaced_event(namespace=namespace)
        else:
            event_list = v1.list_event_for_all_namespaces()

        # 过滤和处理事件
        filtered_events = []
        raw_events = []

        for event in event_list.items:
            event_dict = event.to_dict()
            raw_events.append(event_dict)

            # 资源类型过滤
            if resource_type:
                involved_object = event.involved_object
                if involved_object.kind.lower() != resource_type.lower():
                    continue

            # 资源名称过滤
            if resource_name:
                involved_object = event.involved_object
                if involved_object.name != resource_name:
                    continue

            # 事件类型过滤
            if event_type and event.type != event_type:
                continue

            # 时间过滤
            if since_time and event.first_timestamp:
                if event.first_timestamp < since_time.replace(tzinfo=timezone.utc):
                    continue

            if until_time and event.last_timestamp:
                if event.last_timestamp > until_time.replace(tzinfo=timezone.utc):
                    continue

            # 构建事件详情
            involved_object = event.involved_object
            event_detail = EventDetail(
                name=event.metadata.name,
                namespace=event.metadata.namespace,
                uid=event.metadata.uid,
                type=event.type,
                reason=event.reason,
                message=event.message or "",
                source_component=event.source.component if event.source else None,
                source_host=event.source.host if event.source else None,
                involved_object={
                    "kind": involved_object.kind,
                    "name": involved_object.name,
                    "namespace": involved_object.namespace,
                    "uid": involved_object.uid,
                    "api_version": involved_object.api_version,
                    "resource_version": involved_object.resource_version,
                },
                first_timestamp=k8s_utils.format_timestamp(event.first_timestamp),
                last_timestamp=k8s_utils.format_timestamp(event.last_timestamp),
                count=event.count or 1,
                creation_timestamp=k8s_utils.format_timestamp(
                    event.metadata.creation_timestamp
                ),
                age=k8s_utils.calculate_age(event.metadata.creation_timestamp),
                severity="high" if event.type == "Warning" else "normal",
                category="general",  # 将在后续分类中更新
                is_recurring=(event.count or 1) > 1,
            )

            filtered_events.append(event_detail)

        # 按时间排序 (最新的在前)
        filtered_events.sort(
            key=lambda x: x.last_timestamp or x.creation_timestamp, reverse=True
        )

        # 应用数量限制
        if limit > 0:
            filtered_events = filtered_events[:limit]

        # 事件分类和模式分析
        event_dicts = [event.model_dump() for event in filtered_events]
        categories = categorize_events(event_dicts)
        patterns = analyze_event_patterns(event_dicts)

        # 更新事件分类
        for event in filtered_events:
            for category, events_in_category in categories.items():
                if any(e["name"] == event.name for e in events_in_category):
                    event.category = category
                    break

        # 构建摘要
        warning_count = sum(1 for e in filtered_events if e.type == "Warning")
        normal_count = sum(1 for e in filtered_events if e.type == "Normal")
        recurring_count = sum(1 for e in filtered_events if e.is_recurring)

        # 统计主要原因
        reason_counts = {}
        for event in filtered_events:
            reason = event.reason
            if reason not in reason_counts:
                reason_counts[reason] = 0
            reason_counts[reason] += event.count

        top_reasons = [
            {"reason": reason, "count": count}
            for reason, count in sorted(
                reason_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]
        ]

        summary = EventSummary(
            total_events=len(filtered_events),
            warning_events=warning_count,
            normal_events=normal_count,
            error_events=warning_count,  # Warning事件视为错误
            recurring_events=recurring_count,
            recent_events=len([e for e in filtered_events if e.age.startswith("0")]),
            categories={k: len(v) for k, v in categories.items()},
            top_reasons=top_reasons,
        )

        # 构建响应
        event_response = EventResponse(
            namespace=namespace,
            resource_type=resource_type,
            resource_name=resource_name,
            events=filtered_events,
            summary=summary,
            query_info={
                "since_time": since_time.isoformat() if since_time else None,
                "until_time": until_time.isoformat() if until_time else None,
                "limit": limit,
                "event_type": event_type,
                "total_raw_events": len(raw_events),
                "filtered_events": len(filtered_events),
            },
        )

        logger.info(
            "[事件查询][%s]成功获取事件: 总数=%d, 过滤后=%d, 警告=%d",
            cluster_name,
            len(raw_events),
            len(filtered_events),
            warning_count,
        )

        return event_response

    except Exception as e:
        logger.error("[事件查询][%s]获取事件失败: %s", cluster_name, str(e))
        return None


def create_server_events_router(server_mode_instance) -> APIRouter:
    """创建Server模式的事件API路由"""
    router = APIRouter(
        prefix="/k8s/resources/events", tags=["K8s Events Resources - Server"]
    )

    @router.post("/resource", response_model=EventListResponse)
    async def get_resource_events_endpoint(request: EventRequest):
        """获取特定资源的事件"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[事件查询][%s]开始获取资源事件: %s/%s",
                cluster_name,
                request.resource_type or "所有类型",
                request.resource_name or "所有资源",
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取事件
            event_response = get_resource_events(
                dynamic_client,
                request.namespace,
                request.resource_type,
                request.resource_name,
                request.since_time,
                request.until_time,
                request.limit or 100,
                request.event_type,
                cluster_name,
            )

            if not event_response:
                return {"code": 500, "message": "获取事件失败"}

            server_mode_instance.logger.info(
                "[事件查询][%s]成功获取资源事件",
                cluster_name
            )

            return {"code": 200, "data": event_response}

        except Exception as e:
            server_mode_instance.logger.error(
                "[事件查询][%s]获取资源事件失败: %s", cluster_name, str(e)
            )
            return {"code": 500, "message": f"获取资源事件失败: {str(e)}"}

    @router.post("/namespace", response_model=EventListResponse)
    async def get_namespace_events_endpoint(request: EventRequest):
        """获取命名空间级别的事件"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[事件查询][%s]开始获取命名空间事件: %s",
                cluster_name,
                request.namespace,
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取事件 (不指定资源类型和名称)
            event_response = get_resource_events(
                dynamic_client,
                request.namespace,
                None,  # 不过滤资源类型
                None,  # 不过滤资源名称
                request.since_time,
                request.until_time,
                request.limit or 100,
                request.event_type,
                cluster_name,
            )

            if not event_response:
                return {"code": 500, "message": "获取命名空间事件失败"}

            server_mode_instance.logger.info(
                "[事件查询][%s]成功获取命名空间事件: %s",
                cluster_name,
                request.namespace,
            )

            return {"code": 200, "data": event_response}

        except Exception as e:
            server_mode_instance.logger.error(
                "[事件查询][%s]获取命名空间事件失败: %s, 错误: %s",
                cluster_name,
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取命名空间事件失败: {str(e)}"}

    @router.post("/cluster", response_model=EventListResponse)
    async def get_cluster_events_endpoint(request: EventRequest):
        """获取集群级别的事件"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[事件查询][%s]开始获取集群事件", cluster_name
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取事件 (不指定命名空间、资源类型和名称)
            event_response = get_resource_events(
                dynamic_client,
                None,  # 所有命名空间
                None,  # 不过滤资源类型
                None,  # 不过滤资源名称
                request.since_time,
                request.until_time,
                request.limit or 100,
                request.event_type,
                cluster_name,
            )

            if not event_response:
                return {"code": 500, "message": "获取集群事件失败"}

            server_mode_instance.logger.info(
                "[事件查询][%s]成功获取集群事件",
                cluster_name
            )

            return {"code": 200, "data": event_response}

        except Exception as e:
            server_mode_instance.logger.error(
                "[事件查询][%s]获取集群事件失败: %s", cluster_name, str(e)
            )
            return {"code": 500, "message": f"获取集群事件失败: {str(e)}"}

    return router


def create_instant_events_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的事件API路由"""
    router = APIRouter(
        prefix="/k8s/resources/events", tags=["K8s Events Resources - Instant"]
    )

    @router.post("/resource", response_model=EventListResponse)
    async def get_resource_events_endpoint(request: EventRequest):
        """获取特定资源的事件"""
        try:
            instant_mode_instance.logger.info(
                "[事件查询][当前集群]开始获取资源事件: %s/%s",
                request.resource_type or "所有类型",
                request.resource_name or "所有资源",
            )

            # 获取事件
            event_response = get_resource_events(
                instant_mode_instance.k8s_client,
                request.namespace,
                request.resource_type,
                request.resource_name,
                request.since_time,
                request.until_time,
                request.limit or 100,
                request.event_type,
                "当前集群",
            )

            if not event_response:
                return {"code": 500, "message": "获取事件失败"}

            instant_mode_instance.logger.info(
                "[事件查询][当前集群]成功获取资源事件"
            )

            return {"code": 200, "data": event_response}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[事件查询][当前集群]获取资源事件失败: %s", str(e)
            )
            return {"code": 500, "message": f"获取资源事件失败: {str(e)}"}

    @router.post("/namespace", response_model=EventListResponse)
    async def get_namespace_events_endpoint(request: EventRequest):
        """获取命名空间级别的事件"""
        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        try:
            instant_mode_instance.logger.info(
                "[事件查询][当前集群]开始获取命名空间事件: %s", request.namespace
            )

            # 获取事件 (不指定资源类型和名称)
            event_response = get_resource_events(
                instant_mode_instance.k8s_client,
                request.namespace,
                None,  # 不过滤资源类型
                None,  # 不过滤资源名称
                request.since_time,
                request.until_time,
                request.limit or 100,
                request.event_type,
                "当前集群",
            )

            if not event_response:
                return {"code": 500, "message": "获取命名空间事件失败"}

            instant_mode_instance.logger.info(
                "[事件查询][当前集群]成功获取命名空间事件: %s",
                request.namespace
            )

            return {"code": 200, "data": event_response}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[事件查询][当前集群]获取命名空间事件失败: %s, 错误: %s",
                request.namespace,
                str(e),
            )
            return {"code": 500, "message": f"获取命名空间事件失败: {str(e)}"}

    @router.post("/cluster", response_model=EventListResponse)
    async def get_cluster_events_endpoint(request: EventRequest):
        """获取集群级别的事件"""
        try:
            instant_mode_instance.logger.info("[事件查询][当前集群]开始获取集群事件")

            # 获取事件 (不指定命名空间、资源类型和名称)
            event_response = get_resource_events(
                instant_mode_instance.k8s_client,
                None,  # 所有命名空间
                None,  # 不过滤资源类型
                None,  # 不过滤资源名称
                request.since_time,
                request.until_time,
                request.limit or 100,
                request.event_type,
                "当前集群",
            )

            if not event_response:
                return {"code": 500, "message": "获取集群事件失败"}

            instant_mode_instance.logger.info(
                "[事件查询][当前集群]成功获取集群事件"
            )

            return {"code": 200, "data": event_response}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[事件查询][当前集群]获取集群事件失败: %s", str(e)
            )
            return {"code": 500, "message": f"获取集群事件失败: {str(e)}"}

    return router
