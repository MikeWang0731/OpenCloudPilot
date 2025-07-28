# -*- coding: utf-8 -*-
"""
Istio统一API路由注册器
提供统一的Istio API路由注册功能，支持Server和Instant模式
"""

import logging
from typing import Optional
from fastapi import APIRouter

# 导入Istio工作负载API
from .workloads.istiod_api import (
    create_server_istiod_router,
    create_instant_istiod_router,
)
from .workloads.gateway_workload_api import (
    create_server_gateway_workload_router,
    create_instant_gateway_workload_router,
)

# 导入Istio组件API
from .components.gateway_api import (
    create_gateway_router_for_server,
    create_gateway_router_for_instant,
)
from .components.virtualservice_api import (
    create_virtualservice_router_for_server,
    create_virtualservice_router_for_instant,
)
from .components.destinationrule_api import (
    create_destinationrule_router_for_server,
    create_destinationrule_router_for_instant,
)

# 导入Istio健康摘要API
from .health_summary_api import (
    create_server_health_summary_router,
    create_instant_health_summary_router,
)

logger = logging.getLogger(__name__)


def create_istio_router(mode_instance, mode_type: str) -> APIRouter:
    """
    创建统一的Istio API路由器

    Args:
        mode_instance: 模式实例 (ServerMode 或 InstantAppMode)
        mode_type: 模式类型 ("server" 或 "instant")

    Returns:
        APIRouter: 配置好的Istio API路由器

    Raises:
        ValueError: 当mode_type不支持时
    """
    try:
        logger.info("[Istio路由器][%s]开始创建Istio API路由器", mode_type)

        # 创建主路由器
        main_router = APIRouter()

        if mode_type.lower() == "server":
            # Server模式路由注册
            workload_routers = _create_server_workload_routers(mode_instance)
            component_routers = _create_server_component_routers(mode_instance)
            health_routers = _create_server_health_routers(mode_instance)

        elif mode_type.lower() == "instant":
            # Instant模式路由注册
            workload_routers = _create_instant_workload_routers(mode_instance)
            component_routers = _create_instant_component_routers(mode_instance)
            health_routers = _create_instant_health_routers(mode_instance)

        else:
            raise ValueError(f"不支持的模式类型: {mode_type}")

        # 注册所有路由器
        all_routers = workload_routers + component_routers + health_routers

        for router in all_routers:
            main_router.include_router(router)

        logger.info(
            "[Istio路由器][%s]成功创建Istio API路由器 - 响应摘要: 子路由器数量=%d",
            mode_type,
            len(all_routers),
        )

        return main_router

    except Exception as e:
        logger.error(
            "[Istio路由器][%s]创建路由器失败 - 错误类型=%s, 错误信息=%s",
            mode_type,
            type(e).__name__,
            str(e),
        )
        raise


def _create_server_workload_routers(server_mode_instance) -> list[APIRouter]:
    """
    创建Server模式的工作负载路由器

    Args:
        server_mode_instance: Server模式实例

    Returns:
        list[APIRouter]: 工作负载路由器列表
    """
    try:
        routers = []

        # Istiod工作负载API
        istiod_router = create_server_istiod_router(server_mode_instance)
        routers.append(istiod_router)
        logger.info("[Istio路由器][Server]注册Istiod工作负载API")

        # Gateway工作负载API
        gateway_workload_router = create_server_gateway_workload_router(
            server_mode_instance
        )
        routers.append(gateway_workload_router)
        logger.info("[Istio路由器][Server]注册Gateway工作负载API")

        return routers

    except Exception as e:
        logger.error(
            "[Istio路由器][Server]创建工作负载路由器失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        raise


def _create_server_component_routers(server_mode_instance) -> list[APIRouter]:
    """
    创建Server模式的组件路由器

    Args:
        server_mode_instance: Server模式实例

    Returns:
        list[APIRouter]: 组件路由器列表
    """
    try:
        routers = []

        # Gateway组件API
        gateway_router = create_gateway_router_for_server(server_mode_instance)
        routers.append(gateway_router)
        logger.info("[Istio路由器][Server]注册Gateway组件API")

        # VirtualService组件API
        virtualservice_router = create_virtualservice_router_for_server(
            server_mode_instance
        )
        routers.append(virtualservice_router)
        logger.info("[Istio路由器][Server]注册VirtualService组件API")

        # DestinationRule组件API
        destinationrule_router = create_destinationrule_router_for_server(
            server_mode_instance
        )
        routers.append(destinationrule_router)
        logger.info("[Istio路由器][Server]注册DestinationRule组件API")

        return routers

    except Exception as e:
        logger.error(
            "[Istio路由器][Server]创建组件路由器失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        raise


def _create_instant_workload_routers(instant_mode_instance) -> list[APIRouter]:
    """
    创建Instant模式的工作负载路由器

    Args:
        instant_mode_instance: Instant模式实例

    Returns:
        list[APIRouter]: 工作负载路由器列表
    """
    try:
        routers = []

        # Istiod工作负载API
        istiod_router = create_instant_istiod_router(instant_mode_instance)
        routers.append(istiod_router)
        logger.info("[Istio路由器][Instant]注册Istiod工作负载API")

        # Gateway工作负载API
        gateway_workload_router = create_instant_gateway_workload_router(
            instant_mode_instance
        )
        routers.append(gateway_workload_router)
        logger.info("[Istio路由器][Instant]注册Gateway工作负载API")

        return routers

    except Exception as e:
        logger.error(
            "[Istio路由器][Instant]创建工作负载路由器失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        raise


def _create_instant_component_routers(instant_mode_instance) -> list[APIRouter]:
    """
    创建Instant模式的组件路由器

    Args:
        instant_mode_instance: Instant模式实例

    Returns:
        list[APIRouter]: 组件路由器列表
    """
    try:
        routers = []

        # Gateway组件API
        gateway_router = create_gateway_router_for_instant(instant_mode_instance)
        routers.append(gateway_router)
        logger.info("[Istio路由器][Instant]注册Gateway组件API")

        # VirtualService组件API
        virtualservice_router = create_virtualservice_router_for_instant(
            instant_mode_instance
        )
        routers.append(virtualservice_router)
        logger.info("[Istio路由器][Instant]注册VirtualService组件API")

        # DestinationRule组件API
        destinationrule_router = create_destinationrule_router_for_instant(
            instant_mode_instance
        )
        routers.append(destinationrule_router)
        logger.info("[Istio路由器][Instant]注册DestinationRule组件API")

        return routers

    except Exception as e:
        logger.error(
            "[Istio路由器][Instant]创建组件路由器失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        raise


def _create_server_health_routers(server_mode_instance) -> list[APIRouter]:
    """
    创建Server模式的健康摘要路由器

    Args:
        server_mode_instance: Server模式实例

    Returns:
        list[APIRouter]: 健康摘要路由器列表
    """
    try:
        routers = []

        # 健康摘要API
        health_summary_router = create_server_health_summary_router(
            server_mode_instance
        )
        routers.append(health_summary_router)
        logger.info("[Istio路由器][Server]注册健康摘要API")

        return routers

    except Exception as e:
        logger.error(
            "[Istio路由器][Server]创建健康摘要路由器失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        raise


def _create_instant_health_routers(instant_mode_instance) -> list[APIRouter]:
    """
    创建Instant模式的健康摘要路由器

    Args:
        instant_mode_instance: Instant模式实例

    Returns:
        list[APIRouter]: 健康摘要路由器列表
    """
    try:
        routers = []

        # 健康摘要API
        health_summary_router = create_instant_health_summary_router(
            instant_mode_instance
        )
        routers.append(health_summary_router)
        logger.info("[Istio路由器][Instant]注册健康摘要API")

        return routers

    except Exception as e:
        logger.error(
            "[Istio路由器][Instant]创建健康摘要路由器失败 - 错误类型=%s, 错误信息=%s",
            type(e).__name__,
            str(e),
        )
        raise


def create_server_istio_router(server_mode_instance) -> APIRouter:
    """
    为Server模式创建Istio路由器的便捷函数

    Args:
        server_mode_instance: Server模式实例

    Returns:
        APIRouter: 配置好的Istio路由器
    """
    return create_istio_router(server_mode_instance, "server")


def create_instant_istio_router(instant_mode_instance) -> APIRouter:
    """
    为Instant模式创建Istio路由器的便捷函数

    Args:
        instant_mode_instance: Instant模式实例

    Returns:
        APIRouter: 配置好的Istio路由器
    """
    return create_istio_router(instant_mode_instance, "instant")
