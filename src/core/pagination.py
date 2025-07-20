# -*- coding: utf-8 -*-
"""
分页和限制工具
提供统一的分页、排序和限制功能
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union, Callable
from pydantic import BaseModel, Field
from enum import Enum


class SortOrder(str, Enum):
    """排序顺序"""

    ASC = "asc"
    DESC = "desc"


class PaginationRequest(BaseModel):
    """分页请求模型"""

    page: int = Field(1, ge=1, description="页码，从1开始")
    page_size: int = Field(50, ge=1, le=500, description="每页大小，最大500")
    sort_by: Optional[str] = Field(None, description="排序字段")
    sort_order: SortOrder = Field(SortOrder.ASC, description="排序顺序")


class TimeWindowRequest(BaseModel):
    """时间窗口请求模型"""

    since_time: Optional[datetime] = Field(None, description="开始时间")
    until_time: Optional[datetime] = Field(None, description="结束时间")
    last_hours: Optional[int] = Field(
        None, ge=1, le=168, description="最近N小时，最大7天"
    )
    last_minutes: Optional[int] = Field(
        None, ge=1, le=1440, description="最近N分钟，最大24小时"
    )


class LimitRequest(BaseModel):
    """限制请求模型"""

    limit: int = Field(100, ge=1, le=10000, description="最大返回数量")
    tail_lines: Optional[int] = Field(
        None, ge=1, le=10000, description="尾部行数（用于日志）"
    )


class PaginationResponse(BaseModel):
    """分页响应模型"""

    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    total_items: int = Field(..., description="总条目数")
    total_pages: int = Field(..., description="总页数")
    has_next: bool = Field(..., description="是否有下一页")
    has_prev: bool = Field(..., description="是否有上一页")


class PaginatedData(BaseModel):
    """分页数据模型"""

    items: List[Any] = Field(..., description="数据项列表")
    pagination: PaginationResponse = Field(..., description="分页信息")


class PaginationConfig:
    """分页配置"""

    # 默认分页大小
    DEFAULT_PAGE_SIZE = 50

    # 最大分页大小
    MAX_PAGE_SIZE = 500

    # 资源列表默认限制
    DEFAULT_RESOURCE_LIMIT = 1000
    MAX_RESOURCE_LIMIT = 10000

    # 日志默认限制
    DEFAULT_LOG_LINES = 100
    MAX_LOG_LINES = 10000

    # 事件默认限制
    DEFAULT_EVENT_LIMIT = 200
    MAX_EVENT_LIMIT = 5000

    # 时间窗口限制
    MAX_TIME_WINDOW_HOURS = 168  # 7天
    MAX_TIME_WINDOW_MINUTES = 1440  # 24小时

    # 默认时间窗口
    DEFAULT_LOG_WINDOW_HOURS = 24
    DEFAULT_EVENT_WINDOW_HOURS = 24


class Paginator:
    """分页器"""

    def __init__(self, config: Optional[PaginationConfig] = None):
        """
        初始化分页器

        Args:
            config: 分页配置
        """
        self.config = config or PaginationConfig()
        self.logger = logging.getLogger("cloudpilot.Paginator")

    def paginate_list(
        self,
        items: List[Any],
        pagination: PaginationRequest,
        sort_func: Optional[Callable] = None,
    ) -> PaginatedData:
        """
        对列表进行分页

        Args:
            items: 要分页的项目列表
            pagination: 分页请求
            sort_func: 自定义排序函数

        Returns:
            PaginatedData: 分页后的数据
        """
        total_items = len(items)

        # 排序
        if sort_func and pagination.sort_by:
            try:
                items = sort_func(items, pagination.sort_by, pagination.sort_order)
            except Exception as e:
                self.logger.warning("排序失败，使用原始顺序: %s", str(e))

        # 计算分页信息
        page_size = min(pagination.page_size, self.config.MAX_PAGE_SIZE)
        total_pages = (
            (total_items + page_size - 1) // page_size if total_items > 0 else 1
        )
        current_page = min(pagination.page, total_pages)

        # 计算起始和结束索引
        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)

        # 提取当前页数据
        page_items = items[start_idx:end_idx]

        # 构建分页响应
        pagination_response = PaginationResponse(
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=current_page < total_pages,
            has_prev=current_page > 1,
        )

        return PaginatedData(items=page_items, pagination=pagination_response)

    def apply_time_window(
        self,
        items: List[Dict[str, Any]],
        time_window: TimeWindowRequest,
        timestamp_field: str = "creation_timestamp",
    ) -> List[Dict[str, Any]]:
        """
        应用时间窗口过滤

        Args:
            items: 要过滤的项目列表
            time_window: 时间窗口请求
            timestamp_field: 时间戳字段名

        Returns:
            List[Dict[str, Any]]: 过滤后的项目列表
        """
        if not time_window:
            return items

        now = datetime.now()
        start_time = None
        end_time = None

        # 处理相对时间
        if time_window.last_hours:
            hours = min(time_window.last_hours, self.config.MAX_TIME_WINDOW_HOURS)
            start_time = now - timedelta(hours=hours)
        elif time_window.last_minutes:
            minutes = min(time_window.last_minutes, self.config.MAX_TIME_WINDOW_MINUTES)
            start_time = now - timedelta(minutes=minutes)

        # 处理绝对时间
        if time_window.since_time:
            start_time = time_window.since_time
        if time_window.until_time:
            end_time = time_window.until_time

        # 如果没有指定时间范围，返回原列表
        if not start_time and not end_time:
            return items

        filtered_items = []
        for item in items:
            item_time = self._extract_timestamp(item, timestamp_field)
            if not item_time:
                continue

            # 检查时间范围
            if start_time and item_time < start_time:
                continue
            if end_time and item_time > end_time:
                continue

            filtered_items.append(item)

        return filtered_items

    def apply_limit(self, items: List[Any], limit_request: LimitRequest) -> List[Any]:
        """
        应用数量限制

        Args:
            items: 要限制的项目列表
            limit_request: 限制请求

        Returns:
            List[Any]: 限制后的项目列表
        """
        if not limit_request:
            return items

        limit = min(limit_request.limit, self.config.MAX_RESOURCE_LIMIT)
        return items[:limit]

    def _extract_timestamp(
        self, item: Dict[str, Any], timestamp_field: str
    ) -> Optional[datetime]:
        """
        从项目中提取时间戳

        Args:
            item: 数据项
            timestamp_field: 时间戳字段名

        Returns:
            Optional[datetime]: 提取的时间戳
        """
        try:
            timestamp_value = item.get(timestamp_field)
            if not timestamp_value:
                return None

            # 如果已经是datetime对象
            if isinstance(timestamp_value, datetime):
                return timestamp_value

            # 如果是字符串，尝试解析
            if isinstance(timestamp_value, str):
                # 尝试ISO格式
                try:
                    return datetime.fromisoformat(
                        timestamp_value.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

                # 尝试其他常见格式
                from dateutil import parser

                return parser.parse(timestamp_value)

            return None
        except Exception as e:
            self.logger.warning("解析时间戳失败: %s", str(e))
            return None


def create_default_sort_func(default_field: str = "name") -> Callable:
    """
    创建默认排序函数

    Args:
        default_field: 默认排序字段

    Returns:
        Callable: 排序函数
    """

    def sort_func(
        items: List[Dict[str, Any]], sort_by: str, sort_order: SortOrder
    ) -> List[Dict[str, Any]]:
        """
        排序函数

        Args:
            items: 要排序的项目列表
            sort_by: 排序字段
            sort_order: 排序顺序

        Returns:
            List[Dict[str, Any]]: 排序后的列表
        """
        # 使用指定字段或默认字段
        field = sort_by or default_field
        reverse = sort_order == SortOrder.DESC

        try:
            return sorted(items, key=lambda x: x.get(field, ""), reverse=reverse)
        except Exception:
            # 如果排序失败，返回原列表
            return items

    return sort_func


# 全局分页器实例
_global_paginator: Optional[Paginator] = None


def get_paginator() -> Paginator:
    """
    获取全局分页器实例

    Returns:
        Paginator: 全局分页器实例
    """
    global _global_paginator
    if _global_paginator is None:
        _global_paginator = Paginator()
    return _global_paginator
