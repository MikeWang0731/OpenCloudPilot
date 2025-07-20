# -*- coding: utf-8 -*-
"""
分页功能测试
"""

import pytest
from datetime import datetime, timedelta
from src.core.pagination import (
    Paginator,
    PaginationRequest,
    TimeWindowRequest,
    LimitRequest,
    PaginationConfig,
    SortOrder,
    create_default_sort_func,
)


class TestPaginator:
    """分页器测试"""

    def setup_method(self):
        """测试前准备"""
        self.paginator = Paginator()

        # 创建测试数据
        self.test_items = []
        for i in range(100):
            self.test_items.append(
                {
                    "name": f"item-{i:03d}",
                    "value": i,
                    "creation_timestamp": datetime.now() - timedelta(hours=i),
                    "status": "running" if i % 2 == 0 else "pending",
                }
            )

    def test_basic_pagination(self):
        """测试基本分页功能"""
        pagination = PaginationRequest(page=1, page_size=10)
        result = self.paginator.paginate_list(self.test_items, pagination)

        assert len(result.items) == 10
        assert result.pagination.page == 1
        assert result.pagination.page_size == 10
        assert result.pagination.total_items == 100
        assert result.pagination.total_pages == 10
        assert result.pagination.has_next is True
        assert result.pagination.has_prev is False

    def test_last_page_pagination(self):
        """测试最后一页分页"""
        pagination = PaginationRequest(page=10, page_size=10)
        result = self.paginator.paginate_list(self.test_items, pagination)

        assert len(result.items) == 10
        assert result.pagination.page == 10
        assert result.pagination.has_next is False
        assert result.pagination.has_prev is True

    def test_partial_last_page(self):
        """测试不完整的最后一页"""
        pagination = PaginationRequest(page=4, page_size=30)
        result = self.paginator.paginate_list(self.test_items, pagination)

        assert len(result.items) == 10  # 100 - 3*30 = 10
        assert result.pagination.page == 4
        assert result.pagination.total_pages == 4
        assert result.pagination.has_next is False

    def test_empty_list_pagination(self):
        """测试空列表分页"""
        pagination = PaginationRequest(page=1, page_size=10)
        result = self.paginator.paginate_list([], pagination)

        assert len(result.items) == 0
        assert result.pagination.total_items == 0
        assert result.pagination.total_pages == 1
        assert result.pagination.has_next is False
        assert result.pagination.has_prev is False

    def test_sorting(self):
        """测试排序功能"""
        pagination = PaginationRequest(
            page=1, page_size=5, sort_by="value", sort_order=SortOrder.DESC
        )

        sort_func = create_default_sort_func("value")
        result = self.paginator.paginate_list(self.test_items, pagination, sort_func)

        # 检查是否按value降序排列
        values = [item["value"] for item in result.items]
        assert values == [99, 98, 97, 96, 95]

    def test_time_window_filtering(self):
        """测试时间窗口过滤"""
        time_window = TimeWindowRequest(last_hours=24)

        filtered_items = self.paginator.apply_time_window(
            self.test_items, time_window, "creation_timestamp"
        )

        # 应该只有最近24小时的数据（前25个项目）
        assert len(filtered_items) == 25

    def test_time_window_absolute_time(self):
        """测试绝对时间窗口过滤"""
        now = datetime.now()
        time_window = TimeWindowRequest(
            since_time=now - timedelta(hours=10), until_time=now - timedelta(hours=5)
        )

        filtered_items = self.paginator.apply_time_window(
            self.test_items, time_window, "creation_timestamp"
        )

        # 应该有5个小时的数据（索引5-9）
        assert len(filtered_items) == 6  # 包含边界

    def test_limit_application(self):
        """测试数量限制"""
        limit_request = LimitRequest(limit=50)

        limited_items = self.paginator.apply_limit(self.test_items, limit_request)

        assert len(limited_items) == 50
        assert limited_items[0]["name"] == "item-000"
        assert limited_items[-1]["name"] == "item-049"

    def test_max_page_size_limit(self):
        """测试最大页面大小限制"""
        config = PaginationConfig()
        config.MAX_PAGE_SIZE = 20

        paginator = Paginator(config)
        pagination = PaginationRequest(page=1, page_size=100)  # 请求超过限制

        result = paginator.paginate_list(self.test_items, pagination)

        # 应该被限制为最大页面大小
        assert result.pagination.page_size == 20
        assert len(result.items) == 20

    def test_invalid_page_number(self):
        """测试无效页码处理"""
        pagination = PaginationRequest(page=999, page_size=10)
        result = self.paginator.paginate_list(self.test_items, pagination)

        # 应该返回最后一页
        assert result.pagination.page == 10
        assert len(result.items) == 10

    def test_combined_operations(self):
        """测试组合操作"""
        # 先应用时间窗口过滤
        time_window = TimeWindowRequest(last_hours=50)
        filtered_items = self.paginator.apply_time_window(
            self.test_items, time_window, "creation_timestamp"
        )

        # 再应用限制
        limit_request = LimitRequest(limit=30)
        limited_items = self.paginator.apply_limit(filtered_items, limit_request)

        # 最后分页
        pagination = PaginationRequest(page=2, page_size=10, sort_by="value")
        sort_func = create_default_sort_func("value")
        result = self.paginator.paginate_list(limited_items, pagination, sort_func)

        assert len(result.items) == 10
        assert result.pagination.page == 2
        assert result.pagination.total_items == 30


class TestPaginationConfig:
    """分页配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = PaginationConfig()

        assert config.DEFAULT_PAGE_SIZE == 50
        assert config.MAX_PAGE_SIZE == 500
        assert config.DEFAULT_LOG_LINES == 100
        assert config.MAX_LOG_LINES == 10000
        assert config.DEFAULT_EVENT_LIMIT == 200
        assert config.MAX_EVENT_LIMIT == 5000


class TestSortFunction:
    """排序函数测试"""

    def test_default_sort_function(self):
        """测试默认排序函数"""
        items = [
            {"name": "zebra", "value": 1},
            {"name": "apple", "value": 2},
            {"name": "banana", "value": 3},
        ]

        sort_func = create_default_sort_func("name")

        # 升序排序
        sorted_items = sort_func(items, "name", SortOrder.ASC)
        names = [item["name"] for item in sorted_items]
        assert names == ["apple", "banana", "zebra"]

        # 降序排序
        sorted_items = sort_func(items, "name", SortOrder.DESC)
        names = [item["name"] for item in sorted_items]
        assert names == ["zebra", "banana", "apple"]

    def test_sort_by_value(self):
        """测试按值排序"""
        items = [
            {"name": "item1", "value": 30},
            {"name": "item2", "value": 10},
            {"name": "item3", "value": 20},
        ]

        sort_func = create_default_sort_func("name")

        # 按value升序排序
        sorted_items = sort_func(items, "value", SortOrder.ASC)
        values = [item["value"] for item in sorted_items]
        assert values == [10, 20, 30]

    def test_sort_missing_field(self):
        """测试排序字段缺失的情况"""
        items = [{"name": "item1"}, {"name": "item2", "value": 10}, {"name": "item3"}]

        sort_func = create_default_sort_func("name")

        # 按不存在的字段排序，应该不会出错
        sorted_items = sort_func(items, "missing_field", SortOrder.ASC)
        assert len(sorted_items) == 3


if __name__ == "__main__":
    pytest.main([__file__])
