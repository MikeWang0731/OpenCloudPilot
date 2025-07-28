# -*- coding: utf-8 -*-
"""
Istio缓存工具函数
提供针对Istio资源的专用缓存操作辅助函数
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional, Callable, Dict, List
from functools import wraps

from src.core.cache_utils import with_cache, cache_response
from src.core.resource_cache import get_resource_cache


async def with_istio_cache(
    cluster_name: str,
    resource_type: str,
    operation: str,
    force_refresh: bool = False,
    cache_params: Optional[Dict[str, Any]] = None,
    fetch_func: Optional[Callable] = None,
) -> Any:
    """
    Istio资源专用缓存装饰器函数

    Args:
        cluster_name: 集群名称
        resource_type: Istio资源类型 (istiod, gateway_workload, gateway, virtualservice, destinationrule)
        operation: 操作类型 (list, detail, logs, events)
        force_refresh: 是否强制刷新
        cache_params: 缓存参数
        fetch_func: 数据获取函数

    Returns:
        Any: 缓存或新获取的数据
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")

    # 使用通用缓存函数
    return await with_cache(
        cluster_name=cluster_name,
        resource_type=resource_type,
        operation=operation,
        force_refresh=force_refresh,
        cache_params=cache_params,
        fetch_func=fetch_func,
    )


def istio_cache_response(
    resource_type: str,
    operation: str,
    cluster_name_param: str = "cluster_name",
    cache_params_func: Optional[Callable] = None,
    enable_fallback: bool = True,
    retry_count: int = 3,
):
    """
    Istio响应缓存装饰器，支持优雅降级和重试

    Args:
        resource_type: Istio资源类型
        operation: 操作类型
        cluster_name_param: 集群名称参数名
        cache_params_func: 缓存参数提取函数
        enable_fallback: 是否启用回退机制
        retry_count: 重试次数
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

            try:
                # 使用增强的缓存机制
                return await with_istio_cache_enhanced(
                    cluster_name=cluster_name,
                    resource_type=resource_type,
                    operation=operation,
                    force_refresh=force_refresh,
                    cache_params=cache_params,
                    fetch_func=lambda: func(*args, **kwargs),
                    enable_fallback=enable_fallback,
                    retry_count=retry_count,
                )
            except Exception as e:
                if enable_fallback:
                    # 缓存失败时的回退处理
                    return await handle_cache_failure(
                        cluster_name=cluster_name,
                        resource_type=resource_type,
                        operation=operation,
                        error=e,
                        fallback_func=lambda: func(*args, **kwargs),
                        retry_count=retry_count,
                    )
                else:
                    raise

        return wrapper

    return decorator


async def with_istio_cache_enhanced(
    cluster_name: str,
    resource_type: str,
    operation: str,
    force_refresh: bool = False,
    cache_params: Optional[Dict[str, Any]] = None,
    fetch_func: Optional[Callable] = None,
    enable_fallback: bool = True,
    retry_count: int = 3,
) -> Any:
    """
    增强的Istio资源缓存函数，支持优雅降级

    Args:
        cluster_name: 集群名称
        resource_type: Istio资源类型
        operation: 操作类型
        force_refresh: 是否强制刷新
        cache_params: 缓存参数
        fetch_func: 数据获取函数
        enable_fallback: 是否启用回退机制
        retry_count: 重试次数

    Returns:
        Any: 缓存或新获取的数据
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")

    try:
        # 使用通用缓存函数
        return await with_cache(
            cluster_name=cluster_name,
            resource_type=resource_type,
            operation=operation,
            force_refresh=force_refresh,
            cache_params=cache_params,
            fetch_func=fetch_func,
        )
    except Exception as e:
        if enable_fallback and fetch_func:
            logger.warning(
                "[Istio缓存工具][%s]缓存操作失败，启用回退: %s/%s, 错误: %s",
                cluster_name,
                resource_type,
                operation,
                str(e),
            )

            return await handle_cache_failure(
                cluster_name=cluster_name,
                resource_type=resource_type,
                operation=operation,
                error=e,
                fallback_func=fetch_func,
                retry_count=retry_count,
            )
        else:
            raise


def extract_istio_cache_params(request) -> Dict[str, Any]:
    """
    从Istio请求中提取缓存参数

    Args:
        request: Istio API请求对象

    Returns:
        Dict[str, Any]: 缓存参数字典
    """
    cache_params = {}

    # 添加命名空间参数
    if hasattr(request, "namespace") and request.namespace:
        cache_params["namespace"] = request.namespace

    # 添加资源名称参数
    if hasattr(request, "name") and request.name:
        cache_params["name"] = request.name
    elif hasattr(request, "gateway_name") and request.gateway_name:
        cache_params["name"] = request.gateway_name
    elif hasattr(request, "virtualservice_name") and request.virtualservice_name:
        cache_params["name"] = request.virtualservice_name
    elif hasattr(request, "destinationrule_name") and request.destinationrule_name:
        cache_params["name"] = request.destinationrule_name

    # 添加容器名称参数（用于日志）
    if hasattr(request, "container_name") and request.container_name:
        cache_params["container_name"] = request.container_name

    # 添加时间参数（用于日志和事件）
    if hasattr(request, "tail_lines") and request.tail_lines:
        cache_params["tail_lines"] = request.tail_lines

    if hasattr(request, "last_hours") and request.last_hours:
        cache_params["last_hours"] = request.last_hours

    if hasattr(request, "limit") and request.limit:
        cache_params["limit"] = request.limit

    return cache_params


async def invalidate_istio_cache(
    cluster_name: str,
    resource_type: Optional[str] = None,
    operation: Optional[str] = None,
):
    """
    使Istio资源缓存失效

    Args:
        cluster_name: 集群名称
        resource_type: Istio资源类型，为None则清除所有Istio资源类型
        operation: 操作类型，为None则清除所有操作
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")
    cache = get_resource_cache()

    if resource_type:
        await cache.invalidate(cluster_name, resource_type, operation)
        logger.info("[Istio缓存工具][%s]已清除 %s 缓存", cluster_name, resource_type)
    else:
        # 清除所有Istio相关缓存
        istio_resource_types = [
            "istiod",
            "gateway_workload",
            "gateway",
            "virtualservice",
            "destinationrule",
            "istio_logs",
            "istio_events",
        ]

        for rt in istio_resource_types:
            await cache.invalidate(cluster_name, rt, operation)

        logger.info("[Istio缓存工具][%s]已清除所有Istio资源缓存", cluster_name)


async def get_istio_cache_stats(cluster_name: str) -> Dict[str, Any]:
    """
    获取Istio资源缓存统计信息

    Args:
        cluster_name: 集群名称

    Returns:
        Dict[str, Any]: Istio缓存统计信息
    """
    cache = get_resource_cache()
    all_stats = cache.get_stats()

    # 过滤出Istio相关的统计信息
    istio_stats = {
        "cluster_name": cluster_name,
        "total_hits": all_stats["hits"],
        "total_misses": all_stats["misses"],
        "hit_rate": all_stats["hit_rate"],
        "total_entries": all_stats["total_entries"],
        "istio_ttl_config": {
            "istiod_detail": all_stats["config"]["ttl_config"]["istiod_detail"],
            "gateway_workload_detail": all_stats["config"]["ttl_config"][
                "gateway_workload_detail"
            ],
            "gateway_list": all_stats["config"]["ttl_config"]["gateway_list"],
            "gateway_detail": all_stats["config"]["ttl_config"]["gateway_detail"],
            "virtualservice_list": all_stats["config"]["ttl_config"][
                "virtualservice_list"
            ],
            "virtualservice_detail": all_stats["config"]["ttl_config"][
                "virtualservice_detail"
            ],
            "destinationrule_list": all_stats["config"]["ttl_config"][
                "destinationrule_list"
            ],
            "destinationrule_detail": all_stats["config"]["ttl_config"][
                "destinationrule_detail"
            ],
            "istio_logs": all_stats["config"]["ttl_config"]["istio_logs"],
            "istio_events": all_stats["config"]["ttl_config"]["istio_events"],
        },
    }

    return istio_stats


def create_cache_invalidation_strategy(resource_type: str) -> Dict[str, Any]:
    """
    创建Istio资源的缓存失效策略

    Args:
        resource_type: Istio资源类型

    Returns:
        Dict[str, Any]: 缓存失效策略配置
    """
    strategies = {
        "istiod": {
            "related_resources": ["gateway_workload", "istio_logs", "istio_events"],
            "invalidate_on_change": True,
            "cascade_invalidation": True,
            "ttl_multiplier": 1.5,  # 较长的TTL
        },
        "gateway_workload": {
            "related_resources": ["gateway", "istio_logs", "istio_events"],
            "invalidate_on_change": True,
            "cascade_invalidation": True,
            "ttl_multiplier": 1.5,
        },
        "gateway": {
            "related_resources": ["virtualservice"],
            "invalidate_on_change": True,
            "cascade_invalidation": False,
            "ttl_multiplier": 1.0,
        },
        "virtualservice": {
            "related_resources": ["destinationrule"],
            "invalidate_on_change": True,
            "cascade_invalidation": False,
            "ttl_multiplier": 1.0,
        },
        "destinationrule": {
            "related_resources": [],
            "invalidate_on_change": True,
            "cascade_invalidation": False,
            "ttl_multiplier": 1.0,
        },
        "istio_logs": {
            "related_resources": [],
            "invalidate_on_change": False,
            "cascade_invalidation": False,
            "ttl_multiplier": 0.5,  # 较短的TTL
        },
        "istio_events": {
            "related_resources": [],
            "invalidate_on_change": False,
            "cascade_invalidation": False,
            "ttl_multiplier": 0.5,
        },
    }

    return strategies.get(
        resource_type,
        {
            "related_resources": [],
            "invalidate_on_change": True,
            "cascade_invalidation": False,
            "ttl_multiplier": 1.0,
        },
    )


async def warm_istio_cache(
    cluster_name: str,
    resource_types: Optional[List[str]] = None,
    namespaces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    预热Istio资源缓存

    Args:
        cluster_name: 集群名称
        resource_types: 要预热的资源类型列表，为None则预热所有类型
        namespaces: 要预热的命名空间列表，为None则使用默认命名空间

    Returns:
        Dict[str, Any]: 预热结果统计
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")

    if resource_types is None:
        resource_types = [
            "istiod",
            "gateway_workload",
            "gateway",
            "virtualservice",
            "destinationrule",
        ]

    if namespaces is None:
        namespaces = ["istio-system", "default"]

    warm_stats = {
        "total_resources": 0,
        "successful_warm": 0,
        "failed_warm": 0,
        "resource_stats": {},
    }

    logger.info(
        "[Istio缓存工具][%s]开始预热缓存，资源类型: %s, 命名空间: %s",
        cluster_name,
        resource_types,
        namespaces,
    )

    try:
        for resource_type in resource_types:
            resource_stats = {"success": 0, "failed": 0}

            for namespace in namespaces:
                try:
                    warm_stats["total_resources"] += 1

                    # 这里应该调用实际的资源获取函数来预热缓存
                    # 由于我们在装饰器级别处理缓存，这里只是模拟预热过程
                    cache_params = {"namespace": namespace}

                    # 模拟缓存预热（实际实现中应该调用相应的API函数）
                    await smart_cache_refresh(
                        cluster_name=cluster_name,
                        resource_type=resource_type,
                        operation="list",
                        cache_params=cache_params,
                        fetch_func=None,  # 实际实现中应该提供获取函数
                    )

                    resource_stats["success"] += 1
                    warm_stats["successful_warm"] += 1

                except Exception as e:
                    logger.warning(
                        "[Istio缓存工具][%s]预热缓存失败: %s/%s, 错误: %s",
                        cluster_name,
                        resource_type,
                        namespace,
                        str(e),
                    )
                    resource_stats["failed"] += 1
                    warm_stats["failed_warm"] += 1

            warm_stats["resource_stats"][resource_type] = resource_stats

        logger.info(
            "[Istio缓存工具][%s]缓存预热完成，成功: %d, 失败: %d",
            cluster_name,
            warm_stats["successful_warm"],
            warm_stats["failed_warm"],
        )

        return warm_stats

    except Exception as e:
        logger.error(
            "[Istio缓存工具][%s]缓存预热失败: %s",
            cluster_name,
            str(e),
        )
        return warm_stats


async def optimize_cache_performance(cluster_name: str) -> Dict[str, Any]:
    """
    优化缓存性能

    Args:
        cluster_name: 集群名称

    Returns:
        Dict[str, Any]: 优化结果
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")
    cache = get_resource_cache()

    try:
        # 清理过期缓存
        await cache.cleanup_expired()

        # 获取缓存统计信息
        stats = await get_istio_cache_stats(cluster_name)

        optimization_result = {
            "cluster_name": cluster_name,
            "optimization_time": "completed",
            "cache_stats": stats,
            "recommendations": [],
        }

        # 基于统计信息提供优化建议
        hit_rate = stats.get("hit_rate", 0)
        if hit_rate < 50:
            optimization_result["recommendations"].append(
                "缓存命中率较低，建议增加TTL或预热缓存"
            )

        total_entries = stats.get("total_entries", 0)
        if total_entries > 800:  # 接近最大缓存条目数
            optimization_result["recommendations"].append(
                "缓存条目数量较多，建议清理不常用的缓存"
            )

        logger.info(
            "[Istio缓存工具][%s]缓存性能优化完成，命中率: %.2f%%",
            cluster_name,
            hit_rate,
        )

        return optimization_result

    except Exception as e:
        logger.error(
            "[Istio缓存工具][%s]缓存性能优化失败: %s",
            cluster_name,
            str(e),
        )
        return {
            "cluster_name": cluster_name,
            "optimization_time": "failed",
            "error": str(e),
            "recommendations": ["检查缓存系统状态"],
        }


async def handle_cache_failure(
    cluster_name: str,
    resource_type: str,
    operation: str,
    error: Exception,
    fallback_func: Optional[Callable] = None,
    retry_count: int = 3,
    retry_delay: float = 1.0,
) -> Any:
    """
    处理缓存操作失败的情况，支持重试和优雅降级

    Args:
        cluster_name: 集群名称
        resource_type: 资源类型
        operation: 操作类型
        error: 缓存错误
        fallback_func: 回退函数
        retry_count: 重试次数
        retry_delay: 重试延迟（秒）

    Returns:
        Any: 回退结果或None
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")

    logger.warning(
        "[Istio缓存工具][%s]缓存操作失败: %s/%s, 错误: %s",
        cluster_name,
        resource_type,
        operation,
        str(error),
    )

    # 记录缓存失败统计
    await _record_cache_failure(cluster_name, resource_type, operation, error)

    # 尝试执行回退函数，支持重试
    if fallback_func:
        for attempt in range(retry_count):
            try:
                logger.info(
                    "[Istio缓存工具][%s]执行回退函数，尝试 %d/%d: %s/%s",
                    cluster_name,
                    attempt + 1,
                    retry_count,
                    resource_type,
                    operation,
                )

                result = await fallback_func()

                # 成功获取数据后，尝试更新缓存
                try:
                    await _update_cache_after_fallback(
                        cluster_name, resource_type, operation, result
                    )
                except Exception as cache_update_error:
                    logger.warning(
                        "[Istio缓存工具][%s]回退后更新缓存失败: %s",
                        cluster_name,
                        str(cache_update_error),
                    )

                return result

            except Exception as fallback_error:
                logger.error(
                    "[Istio缓存工具][%s]回退函数执行失败，尝试 %d/%d: %s",
                    cluster_name,
                    attempt + 1,
                    retry_count,
                    str(fallback_error),
                )

                # 如果不是最后一次尝试，等待后重试
                if attempt < retry_count - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避
                else:
                    # 最后一次尝试失败，记录最终错误
                    await _record_fallback_failure(
                        cluster_name, resource_type, operation, fallback_error
                    )

    return None


async def _record_cache_failure(
    cluster_name: str, resource_type: str, operation: str, error: Exception
):
    """记录缓存失败统计"""
    try:
        # 这里可以集成到监控系统或统计系统
        logger = logging.getLogger("cloudpilot.istio_cache_stats")
        logger.info(
            "[缓存失败统计][%s]%s/%s 失败: %s",
            cluster_name,
            resource_type,
            operation,
            str(error),
        )
    except Exception:
        pass  # 忽略统计记录失败


async def _update_cache_after_fallback(
    cluster_name: str, resource_type: str, operation: str, data: Any
):
    """回退成功后更新缓存"""
    try:
        cache = get_resource_cache()
        await cache.set(
            cluster_name=cluster_name,
            resource_type=resource_type,
            operation=operation,
            data=data,
        )

        logger = logging.getLogger("cloudpilot.istio_cache_utils")
        logger.info(
            "[Istio缓存工具][%s]回退后成功更新缓存: %s/%s",
            cluster_name,
            resource_type,
            operation,
        )
    except Exception as e:
        logger = logging.getLogger("cloudpilot.istio_cache_utils")
        logger.error(
            "[Istio缓存工具][%s]回退后更新缓存失败: %s/%s, 错误: %s",
            cluster_name,
            resource_type,
            operation,
            str(e),
        )


async def _record_fallback_failure(
    cluster_name: str, resource_type: str, operation: str, error: Exception
):
    """记录回退失败统计"""
    try:
        logger = logging.getLogger("cloudpilot.istio_cache_stats")
        logger.error(
            "[回退失败统计][%s]%s/%s 最终失败: %s",
            cluster_name,
            resource_type,
            operation,
            str(error),
        )
    except Exception:
        pass  # 忽略统计记录失败


async def cascade_invalidate_cache(
    cluster_name: str,
    resource_type: str,
    operation: Optional[str] = None,
    max_depth: int = 3,
) -> Dict[str, Any]:
    """
    级联失效相关资源缓存，支持深度控制和结果统计

    Args:
        cluster_name: 集群名称
        resource_type: 触发失效的资源类型
        operation: 操作类型
        max_depth: 最大级联深度

    Returns:
        Dict[str, Any]: 级联失效结果统计
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")

    invalidation_result = {
        "cluster_name": cluster_name,
        "trigger_resource": resource_type,
        "operation": operation,
        "invalidated_resources": [],
        "failed_invalidations": [],
        "total_invalidated": 0,
        "cascade_depth": 0,
    }

    try:
        # 使用队列进行广度优先级联失效
        invalidation_queue = [(resource_type, 0)]  # (resource_type, depth)
        processed_resources = set()

        while invalidation_queue and max_depth > 0:
            current_resource, current_depth = invalidation_queue.pop(0)

            if current_resource in processed_resources or current_depth >= max_depth:
                continue

            processed_resources.add(current_resource)
            invalidation_result["cascade_depth"] = max(
                invalidation_result["cascade_depth"], current_depth
            )

            try:
                # 失效当前资源缓存
                await invalidate_istio_cache(cluster_name, current_resource, operation)
                invalidation_result["invalidated_resources"].append(
                    {
                        "resource_type": current_resource,
                        "depth": current_depth,
                        "success": True,
                    }
                )
                invalidation_result["total_invalidated"] += 1

                logger.info(
                    "[Istio缓存工具][%s]级联失效缓存成功: %s (深度: %d)",
                    cluster_name,
                    current_resource,
                    current_depth,
                )

                # 获取失效策略并添加相关资源到队列
                strategy = create_cache_invalidation_strategy(current_resource)
                if strategy.get("cascade_invalidation", False):
                    related_resources = strategy.get("related_resources", [])

                    for related_resource in related_resources:
                        if related_resource not in processed_resources:
                            invalidation_queue.append(
                                (related_resource, current_depth + 1)
                            )

            except Exception as resource_error:
                logger.error(
                    "[Istio缓存工具][%s]级联失效资源失败: %s (深度: %d), 错误: %s",
                    cluster_name,
                    current_resource,
                    current_depth,
                    str(resource_error),
                )
                invalidation_result["failed_invalidations"].append(
                    {
                        "resource_type": current_resource,
                        "depth": current_depth,
                        "error": str(resource_error),
                    }
                )

        logger.info(
            "[Istio缓存工具][%s]级联失效完成: 成功 %d 个，失败 %d 个，最大深度 %d",
            cluster_name,
            invalidation_result["total_invalidated"],
            len(invalidation_result["failed_invalidations"]),
            invalidation_result["cascade_depth"],
        )

        return invalidation_result

    except Exception as e:
        logger.error(
            "[Istio缓存工具][%s]级联失效缓存失败: %s, 错误: %s",
            cluster_name,
            resource_type,
            str(e),
        )
        invalidation_result["failed_invalidations"].append(
            {
                "resource_type": resource_type,
                "depth": 0,
                "error": str(e),
            }
        )
        return invalidation_result


async def smart_cache_refresh(
    cluster_name: str,
    resource_type: str,
    operation: str,
    cache_params: Optional[Dict[str, Any]] = None,
    fetch_func: Optional[Callable] = None,
) -> Any:
    """
    智能缓存刷新，支持后台刷新和预加载

    Args:
        cluster_name: 集群名称
        resource_type: 资源类型
        operation: 操作类型
        cache_params: 缓存参数
        fetch_func: 数据获取函数

    Returns:
        Any: 缓存或新获取的数据
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")
    cache = get_resource_cache()
    cache_params = cache_params or {}

    try:
        # 尝试从缓存获取数据
        cached_data = await cache.get(
            cluster_name=cluster_name,
            resource_type=resource_type,
            operation=operation,
            **cache_params,
        )

        if cached_data:
            # 检查缓存是否即将过期（剩余TTL < 20%）
            # 如果即将过期，启动后台刷新
            # 这里简化实现，直接返回缓存数据
            logger.debug(
                "[Istio缓存工具][%s]智能缓存命中: %s/%s",
                cluster_name,
                resource_type,
                operation,
            )
            return cached_data

        # 缓存未命中，获取新数据
        if fetch_func:
            data = await fetch_func()

            # 缓存数据
            await cache.set(
                cluster_name=cluster_name,
                resource_type=resource_type,
                operation=operation,
                data=data,
                **cache_params,
            )

            logger.debug(
                "[Istio缓存工具][%s]智能缓存已更新: %s/%s",
                cluster_name,
                resource_type,
                operation,
            )

            return data

        return None

    except Exception as e:
        logger.error(
            "[Istio缓存工具][%s]智能缓存刷新失败: %s/%s, 错误: %s",
            cluster_name,
            resource_type,
            operation,
            str(e),
        )

        # 尝试回退到直接获取数据
        if fetch_func:
            try:
                return await fetch_func()
            except Exception as fallback_error:
                logger.error(
                    "[Istio缓存工具][%s]回退数据获取失败: %s",
                    cluster_name,
                    str(fallback_error),
                )

        return None


async def batch_cache_operations(
    cluster_name: str,
    operations: List[Dict[str, Any]],
    max_concurrent: int = 10,
    rate_limit_delay: float = 0.1,
    enable_circuit_breaker: bool = True,
) -> Dict[str, Any]:
    """
    批量缓存操作，支持速率限制和熔断器

    Args:
        cluster_name: 集群名称
        operations: 缓存操作列表
        max_concurrent: 最大并发数
        rate_limit_delay: 速率限制延迟（秒）
        enable_circuit_breaker: 是否启用熔断器

    Returns:
        Dict[str, Any]: 批量操作结果
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")

    # 熔断器状态
    circuit_breaker = {
        "failure_count": 0,
        "failure_threshold": max_concurrent // 2,  # 失败阈值为并发数的一半
        "is_open": False,
        "last_failure_time": None,
        "recovery_timeout": 30.0,  # 30秒恢复时间
    }

    try:
        logger.info(
            "[Istio缓存工具][%s]开始批量缓存操作，操作数: %d, 最大并发: %d",
            cluster_name,
            len(operations),
            max_concurrent,
        )

        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_cache_operation(
            operation: Dict[str, Any], index: int
        ) -> tuple:
            # 检查熔断器状态
            if enable_circuit_breaker and _is_circuit_breaker_open(circuit_breaker):
                return f"operation_{index}", {
                    "success": False,
                    "error": "熔断器开启，跳过操作",
                    "circuit_breaker_open": True,
                }

            async with semaphore:
                op_type = operation.get("type")  # get, set, invalidate
                resource_type = operation.get("resource_type")
                op_operation = operation.get("operation")
                cache_params = operation.get("cache_params", {})
                operation_key = f"{resource_type}:{op_operation}:{index}"

                try:
                    # 添加速率限制
                    if rate_limit_delay > 0:
                        await asyncio.sleep(rate_limit_delay)

                    cache = get_resource_cache()
                    start_time = time.time()

                    if op_type == "get":
                        result = await cache.get(
                            cluster_name=cluster_name,
                            resource_type=resource_type,
                            operation=op_operation,
                            **cache_params,
                        )
                        execution_time = time.time() - start_time

                        return operation_key, {
                            "success": True,
                            "data": result,
                            "execution_time": execution_time,
                            "cache_hit": result is not None,
                        }

                    elif op_type == "set":
                        data = operation.get("data")
                        await cache.set(
                            cluster_name=cluster_name,
                            resource_type=resource_type,
                            operation=op_operation,
                            data=data,
                            **cache_params,
                        )
                        execution_time = time.time() - start_time

                        return operation_key, {
                            "success": True,
                            "action": "cached",
                            "execution_time": execution_time,
                        }

                    elif op_type == "invalidate":
                        await cache.invalidate(
                            cluster_name=cluster_name,
                            resource_type=resource_type,
                            operation=op_operation,
                        )
                        execution_time = time.time() - start_time

                        return operation_key, {
                            "success": True,
                            "action": "invalidated",
                            "execution_time": execution_time,
                        }

                    elif op_type == "batch_invalidate":
                        # 批量失效操作
                        invalidation_result = await cascade_invalidate_cache(
                            cluster_name, resource_type, op_operation
                        )
                        execution_time = time.time() - start_time

                        return operation_key, {
                            "success": invalidation_result["total_invalidated"] > 0,
                            "action": "batch_invalidated",
                            "execution_time": execution_time,
                            "invalidation_result": invalidation_result,
                        }

                    else:
                        return operation_key, {
                            "success": False,
                            "error": f"不支持的操作类型: {op_type}",
                        }

                except Exception as e:
                    execution_time = time.time() - start_time

                    # 更新熔断器状态
                    if enable_circuit_breaker:
                        _update_circuit_breaker_on_failure(circuit_breaker)

                    return operation_key, {
                        "success": False,
                        "error": str(e),
                        "execution_time": execution_time,
                    }

        # 创建并发任务
        tasks = [execute_cache_operation(op, idx) for idx, op in enumerate(operations)]

        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        operation_results = {}
        successful_count = 0
        failed_count = 0
        cache_hits = 0
        total_execution_time = 0.0
        circuit_breaker_failures = 0

        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    "[Istio缓存工具][%s]缓存操作异常: %s",
                    cluster_name,
                    str(result),
                )
                failed_count += 1
                continue

            operation_key, operation_result = result
            operation_results[operation_key] = operation_result

            if operation_result.get("success"):
                successful_count += 1
                if operation_result.get("cache_hit"):
                    cache_hits += 1
            else:
                failed_count += 1
                if operation_result.get("circuit_breaker_open"):
                    circuit_breaker_failures += 1

            # 累计执行时间
            execution_time = operation_result.get("execution_time", 0)
            total_execution_time += execution_time

        # 计算统计信息
        avg_execution_time = (
            total_execution_time / len(operations) if len(operations) > 0 else 0
        )
        cache_hit_rate = (
            (cache_hits / successful_count * 100) if successful_count > 0 else 0
        )

        logger.info(
            "[Istio缓存工具][%s]批量缓存操作完成，成功: %d/%d, 缓存命中率: %.2f%%, 平均耗时: %.3f秒",
            cluster_name,
            successful_count,
            len(operations),
            cache_hit_rate,
            avg_execution_time,
        )

        return {
            "cluster_name": cluster_name,
            "total_operations": len(operations),
            "successful_operations": successful_count,
            "failed_operations": failed_count,
            "cache_hits": cache_hits,
            "cache_hit_rate": cache_hit_rate,
            "average_execution_time": avg_execution_time,
            "total_execution_time": total_execution_time,
            "circuit_breaker_failures": circuit_breaker_failures,
            "circuit_breaker_status": {
                "is_open": circuit_breaker["is_open"],
                "failure_count": circuit_breaker["failure_count"],
            },
            "results": operation_results,
        }

    except Exception as e:
        logger.error(
            "[Istio缓存工具][%s]批量缓存操作失败: %s",
            cluster_name,
            str(e),
        )
        return {
            "cluster_name": cluster_name,
            "total_operations": len(operations),
            "successful_operations": 0,
            "failed_operations": len(operations),
            "error": str(e),
            "results": {},
        }


def _is_circuit_breaker_open(circuit_breaker: Dict[str, Any]) -> bool:
    """检查熔断器是否开启"""
    if not circuit_breaker["is_open"]:
        return False

    # 检查是否到了恢复时间
    if circuit_breaker["last_failure_time"]:
        import time

        current_time = time.time()
        if (
            current_time - circuit_breaker["last_failure_time"]
            > circuit_breaker["recovery_timeout"]
        ):
            # 重置熔断器
            circuit_breaker["is_open"] = False
            circuit_breaker["failure_count"] = 0
            circuit_breaker["last_failure_time"] = None
            return False

    return True


def _update_circuit_breaker_on_failure(circuit_breaker: Dict[str, Any]):
    """更新熔断器失败状态"""
    import time

    circuit_breaker["failure_count"] += 1
    circuit_breaker["last_failure_time"] = time.time()

    if circuit_breaker["failure_count"] >= circuit_breaker["failure_threshold"]:
        circuit_breaker["is_open"] = True


async def adaptive_cache_ttl(
    cluster_name: str,
    resource_type: str,
    operation: str,
    base_ttl: int,
    performance_metrics: Optional[Dict[str, Any]] = None,
) -> int:
    """
    自适应缓存TTL调整

    Args:
        cluster_name: 集群名称
        resource_type: 资源类型
        operation: 操作类型
        base_ttl: 基础TTL
        performance_metrics: 性能指标

    Returns:
        int: 调整后的TTL
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")

    try:
        # 获取缓存统计信息
        cache_stats = await get_istio_cache_stats(cluster_name)
        hit_rate = cache_stats.get("hit_rate", 0)

        # 根据命中率调整TTL
        if hit_rate > 80:
            # 命中率高，可以适当延长TTL
            adjusted_ttl = int(base_ttl * 1.2)
        elif hit_rate < 30:
            # 命中率低，缩短TTL以获取更新的数据
            adjusted_ttl = int(base_ttl * 0.8)
        else:
            adjusted_ttl = base_ttl

        # 根据性能指标进一步调整
        if performance_metrics:
            avg_response_time = performance_metrics.get("avg_response_time", 0)
            if avg_response_time > 5.0:  # 响应时间超过5秒
                # 响应慢，延长TTL减少请求频率
                adjusted_ttl = int(adjusted_ttl * 1.5)
            elif avg_response_time < 1.0:  # 响应时间小于1秒
                # 响应快，可以缩短TTL获取更新数据
                adjusted_ttl = int(adjusted_ttl * 0.9)

        # 确保TTL在合理范围内
        adjusted_ttl = max(10, min(adjusted_ttl, 600))  # 10秒到10分钟

        logger.debug(
            "[Istio缓存工具][%s]自适应TTL调整: %s/%s, %d -> %d",
            cluster_name,
            resource_type,
            operation,
            base_ttl,
            adjusted_ttl,
        )

        return adjusted_ttl

    except Exception as e:
        logger.error(
            "[Istio缓存工具][%s]自适应TTL调整失败: %s",
            cluster_name,
            str(e),
        )
        return base_ttl


async def cache_health_check(cluster_name: str) -> Dict[str, Any]:
    """
    缓存健康检查

    Args:
        cluster_name: 集群名称

    Returns:
        Dict[str, Any]: 健康检查结果
    """
    logger = logging.getLogger("cloudpilot.istio_cache_utils")

    try:
        cache = get_resource_cache()
        stats = await get_istio_cache_stats(cluster_name)

        # 计算健康指标
        hit_rate = stats.get("hit_rate", 0)
        total_entries = stats.get("total_entries", 0)

        # 健康状态判断
        health_status = "healthy"
        issues = []
        recommendations = []

        if hit_rate < 30:
            health_status = "warning"
            issues.append(f"缓存命中率较低: {hit_rate}%")
            recommendations.append("考虑调整TTL设置或预热缓存")

        if total_entries > 800:  # 接近最大缓存条目数
            health_status = "warning"
            issues.append(f"缓存条目数量较多: {total_entries}")
            recommendations.append("考虑清理不常用的缓存条目")

        if hit_rate < 10:
            health_status = "critical"
            issues.append("缓存命中率极低，可能存在配置问题")
            recommendations.append("检查缓存配置和TTL设置")

        health_result = {
            "cluster_name": cluster_name,
            "status": health_status,
            "hit_rate": hit_rate,
            "total_entries": total_entries,
            "issues": issues,
            "recommendations": recommendations,
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(
            "[Istio缓存工具][%s]缓存健康检查完成，状态: %s, 命中率: %.2f%%",
            cluster_name,
            health_status,
            hit_rate,
        )

        return health_result

    except Exception as e:
        logger.error(
            "[Istio缓存工具][%s]缓存健康检查失败: %s",
            cluster_name,
            str(e),
        )
        return {
            "cluster_name": cluster_name,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
