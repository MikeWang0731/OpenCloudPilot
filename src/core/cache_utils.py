# -*- coding: utf-8 -*-
"""
缓存工具函数
提供通用的缓存操作辅助函数
"""

import logging
from typing import Any, Optional, Callable, Dict
from functools import wraps

from src.core.resource_cache import get_resource_cache


async def with_cache(
    cluster_name: str,
    resource_type: str,
    operation: str,
    force_refresh: bool = False,
    cache_params: Optional[Dict[str, Any]] = None,
    fetch_func: Optional[Callable] = None,
) -> Any:
    """
    通用缓存装饰器函数

    Args:
        cluster_name: 集群名称
        resource_type: 资源类型
        operation: 操作类型
        force_refresh: 是否强制刷新
        cache_params: 缓存参数
        fetch_func: 数据获取函数

    Returns:
        Any: 缓存或新获取的数据
    """
    logger = logging.getLogger("cloudpilot.cache_utils")
    cache = get_resource_cache()
    cache_params = cache_params or {}

    # 尝试从缓存获取数据
    if not force_refresh:
        cached_data = await cache.get(
            cluster_name=cluster_name,
            resource_type=resource_type,
            operation=operation,
            **cache_params
        )
        if cached_data:
            logger.debug(
                "[缓存工具][%s]缓存命中: %s/%s", cluster_name, resource_type, operation
            )
            return cached_data

    # 如果没有缓存或强制刷新，调用获取函数
    if fetch_func:
        data = await fetch_func()

        # 缓存数据
        await cache.set(
            cluster_name=cluster_name,
            resource_type=resource_type,
            operation=operation,
            data=data,
            **cache_params
        )

        logger.debug(
            "[缓存工具][%s]数据已缓存: %s/%s", cluster_name, resource_type, operation
        )

        return data

    return None


def cache_response(
    resource_type: str,
    operation: str,
    cluster_name_param: str = "cluster_name",
    cache_params_func: Optional[Callable] = None,
):
    """
    响应缓存装饰器

    Args:
        resource_type: 资源类型
        operation: 操作类型
        cluster_name_param: 集群名称参数名
        cache_params_func: 缓存参数提取函数
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 提取请求对象（通常是第一个参数）
            request = args[0] if args else None
            if not request:
                return await func(*args, **kwargs)

            # 获取集群名称
            cluster_name = getattr(request, cluster_name_param, None)
            if not cluster_name:
                cluster_name = "current"  # Instant模式默认值

            # 获取force_refresh参数
            force_refresh = getattr(request, "force_refresh", False)

            # 提取缓存参数
            cache_params = {}
            if cache_params_func:
                cache_params = cache_params_func(request)

            # 使用缓存
            return await with_cache(
                cluster_name=cluster_name,
                resource_type=resource_type,
                operation=operation,
                force_refresh=force_refresh,
                cache_params=cache_params,
                fetch_func=lambda: func(*args, **kwargs),
            )

        return wrapper

    return decorator


async def invalidate_resource_cache(
    cluster_name: str,
    resource_type: Optional[str] = None,
    operation: Optional[str] = None,
):
    """
    使资源缓存失效

    Args:
        cluster_name: 集群名称
        resource_type: 资源类型，为None则清除所有资源类型
        operation: 操作类型，为None则清除所有操作
    """
    cache = get_resource_cache()
    await cache.invalidate(cluster_name, resource_type, operation)


async def get_cache_stats() -> Dict[str, Any]:
    """
    获取缓存统计信息

    Returns:
        Dict[str, Any]: 缓存统计信息
    """
    cache = get_resource_cache()
    return cache.get_stats()


async def cleanup_expired_cache():
    """清理过期的缓存条目"""
    cache = get_resource_cache()
    await cache.cleanup_expired()


async def clear_all_cache():
    """清除所有缓存"""
    cache = get_resource_cache()
    await cache.clear_all()
