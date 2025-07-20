# -*- coding: utf-8 -*-
"""
Service资源管理API
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from kubernetes import client

from src.core.k8s_utils import K8sUtils
from src.core.resource_parser import ResourceParser


class ServiceRequest(BaseModel):
    """Service请求模型"""

    cluster_name: Optional[str] = Field(None, description="集群名称 (Server模式必需)")
    namespace: Optional[str] = Field(
        None, description="命名空间，为空则查询所有命名空间"
    )
    service_name: Optional[str] = Field(
        None, description="Service名称，为空则查询所有Service"
    )
    force_refresh: Optional[bool] = Field(False, description="是否强制刷新缓存")


class ServicePort(BaseModel):
    """服务端口模型"""

    name: Optional[str] = Field(None, description="端口名称")
    port: int = Field(..., description="服务端口")
    target_port: Optional[str] = Field(None, description="目标端口")
    protocol: str = Field("TCP", description="协议")
    node_port: Optional[int] = Field(None, description="节点端口 (NodePort类型)")


class EndpointSubset(BaseModel):
    """端点子集模型"""

    addresses: List[Dict[str, Any]] = Field(
        default_factory=list, description="就绪地址"
    )
    not_ready_addresses: List[Dict[str, Any]] = Field(
        default_factory=list, description="未就绪地址"
    )
    ports: List[Dict[str, Any]] = Field(default_factory=list, description="端口信息")


class EndpointInfo(BaseModel):
    """端点信息模型"""

    name: str = Field(..., description="端点名称")
    namespace: str = Field(..., description="命名空间")
    subsets: List[EndpointSubset] = Field(default_factory=list, description="端点子集")
    ready_addresses_count: int = Field(0, description="就绪地址数量")
    not_ready_addresses_count: int = Field(0, description="未就绪地址数量")
    total_addresses_count: int = Field(0, description="总地址数量")


class ExternalAccess(BaseModel):
    """外部访问信息模型"""

    type: str = Field(..., description="访问类型")
    external_ips: List[str] = Field(default_factory=list, description="外部IP列表")
    load_balancer_ip: Optional[str] = Field(None, description="负载均衡器IP")
    load_balancer_ingress: List[Dict[str, Any]] = Field(
        default_factory=list, description="负载均衡器入口"
    )
    external_name: Optional[str] = Field(
        None, description="外部名称 (ExternalName类型)"
    )


class ServiceDetail(BaseModel):
    """Service详细信息模型"""

    name: str = Field(..., description="Service名称")
    namespace: str = Field(..., description="命名空间")
    uid: str = Field(..., description="Service UID")
    service_type: str = Field(..., description="服务类型")
    cluster_ip: Optional[str] = Field(None, description="集群IP")
    cluster_ips: List[str] = Field(default_factory=list, description="集群IP列表")
    creation_timestamp: str = Field(..., description="创建时间")
    age: str = Field(..., description="年龄")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="注解")
    selector: Dict[str, str] = Field(default_factory=dict, description="选择器")
    ports: List[ServicePort] = Field(default_factory=list, description="端口配置")
    endpoints: Optional[EndpointInfo] = Field(None, description="端点信息")
    external_access: Optional[ExternalAccess] = Field(None, description="外部访问信息")
    session_affinity: Optional[str] = Field(None, description="会话亲和性")
    health_score: float = Field(100.0, description="健康分数 (0-100)")
    error_indicators: List[str] = Field(default_factory=list, description="错误指示器")
    connectivity_status: str = Field("Unknown", description="连接状态")


class ServiceListResponse(BaseModel):
    """Service列表响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")


class ServiceDetailResponse(BaseModel):
    """Service详情响应模型"""

    code: int = Field(..., description="响应码")
    message: Optional[str] = Field(None, description="响应消息")
    data: Optional[ServiceDetail] = Field(None, description="Service详情")


# Service信息提取函数


def get_endpoint_info(
    v1_api, namespace: str, service_name: str, cluster_name: str = "current"
) -> Optional[EndpointInfo]:
    """
    获取Service的端点信息

    Args:
        v1_api: Core V1 API客户端
        namespace: 命名空间
        service_name: Service名称
        cluster_name: 集群名称

    Returns:
        Optional[EndpointInfo]: 端点信息，如果不存在则返回None
    """
    logger = logging.getLogger("cloudpilot.service_api")

    try:
        logger.info(
            "[Service详情][%s]开始获取端点信息: %s/%s",
            cluster_name,
            namespace,
            service_name,
        )

        # 获取端点信息
        try:
            endpoints = v1_api.read_namespaced_endpoints(
                name=service_name, namespace=namespace
            )
        except client.ApiException as e:
            if e.status == 404:
                logger.warning(
                    "[Service详情][%s]端点不存在: %s/%s",
                    cluster_name,
                    namespace,
                    service_name,
                )
                return None
            raise

        # 解析端点子集
        subsets = []
        total_ready = 0
        total_not_ready = 0

        for subset in endpoints.subsets or []:
            addresses = []
            not_ready_addresses = []
            ports = []

            # 处理就绪地址
            for addr in subset.addresses or []:
                address_info = {
                    "ip": addr.ip,
                    "hostname": addr.hostname,
                    "node_name": addr.node_name,
                    "target_ref": (
                        {
                            "kind": addr.target_ref.kind,
                            "name": addr.target_ref.name,
                            "namespace": addr.target_ref.namespace,
                            "uid": addr.target_ref.uid,
                        }
                        if addr.target_ref
                        else None
                    ),
                }
                addresses.append(address_info)
                total_ready += 1

            # 处理未就绪地址
            for addr in subset.not_ready_addresses or []:
                address_info = {
                    "ip": addr.ip,
                    "hostname": addr.hostname,
                    "node_name": addr.node_name,
                    "target_ref": (
                        {
                            "kind": addr.target_ref.kind,
                            "name": addr.target_ref.name,
                            "namespace": addr.target_ref.namespace,
                            "uid": addr.target_ref.uid,
                        }
                        if addr.target_ref
                        else None
                    ),
                }
                not_ready_addresses.append(address_info)
                total_not_ready += 1

            # 处理端口信息
            for port in subset.ports or []:
                port_info = {
                    "name": port.name,
                    "port": port.port,
                    "protocol": port.protocol,
                }
                ports.append(port_info)

            subset_info = EndpointSubset(
                addresses=addresses,
                not_ready_addresses=not_ready_addresses,
                ports=ports,
            )
            subsets.append(subset_info)

        endpoint_info = EndpointInfo(
            name=endpoints.metadata.name,
            namespace=endpoints.metadata.namespace,
            subsets=subsets,
            ready_addresses_count=total_ready,
            not_ready_addresses_count=total_not_ready,
            total_addresses_count=total_ready + total_not_ready,
        )

        logger.info(
            "[Service详情][%s]成功获取端点信息: %s/%s, 就绪地址: %d, 未就绪地址: %d",
            cluster_name,
            namespace,
            service_name,
            total_ready,
            total_not_ready,
        )

        return endpoint_info

    except Exception as e:
        logger.error(
            "[Service详情][%s]获取端点信息失败: %s/%s, 错误: %s",
            cluster_name,
            namespace,
            service_name,
            str(e),
        )
        return None


def analyze_service_health(
    service_data: Dict[str, Any], endpoint_info: Optional[EndpointInfo] = None
) -> tuple[float, str, List[str]]:
    """
    分析Service健康状态和连接性

    Args:
        service_data: Service原始数据
        endpoint_info: 端点信息

    Returns:
        tuple: (健康分数, 连接状态, 错误指示器列表)
    """
    logger = logging.getLogger("cloudpilot.service_api")

    try:
        score = 100.0
        connectivity_status = "Healthy"
        error_indicators = []

        # 检查Service类型和配置
        service_type = service_data.get("spec", {}).get("type", "ClusterIP")
        selector = service_data.get("spec", {}).get("selector", {})

        # 检查选择器
        if not selector and service_type != "ExternalName":
            score -= 20
            error_indicators.append("缺少Pod选择器")
            connectivity_status = "Warning"

        # 检查端点状态
        if endpoint_info:
            if endpoint_info.total_addresses_count == 0:
                score -= 50
                error_indicators.append("没有可用的端点")
                connectivity_status = "Unhealthy"
            elif endpoint_info.ready_addresses_count == 0:
                score -= 40
                error_indicators.append("所有端点都未就绪")
                connectivity_status = "Degraded"
            elif endpoint_info.not_ready_addresses_count > 0:
                score -= 15
                error_indicators.append(
                    f"有{endpoint_info.not_ready_addresses_count}个端点未就绪"
                )
                if connectivity_status == "Healthy":
                    connectivity_status = "Warning"

        # 检查端口配置
        ports = service_data.get("spec", {}).get("ports", [])
        if not ports:
            score -= 30
            error_indicators.append("未配置服务端口")
            connectivity_status = "Warning"

        # 检查LoadBalancer类型的外部访问
        if service_type == "LoadBalancer":
            status = service_data.get("status", {})
            load_balancer = status.get("loadBalancer", {})
            ingress = load_balancer.get("ingress", [])

            if not ingress:
                score -= 25
                error_indicators.append("LoadBalancer未分配外部IP")
                if connectivity_status == "Healthy":
                    connectivity_status = "Warning"

        # 检查ExternalName类型
        if service_type == "ExternalName":
            external_name = service_data.get("spec", {}).get("externalName")
            if not external_name:
                score -= 40
                error_indicators.append("ExternalName类型缺少外部名称")
                connectivity_status = "Warning"

        # 确保分数在0-100范围内
        score = max(0.0, min(100.0, score))

        return score, connectivity_status, error_indicators

    except Exception as e:
        logger.error("分析Service健康状态失败: %s", str(e))
        return 0.0, "Error", [f"健康状态分析失败: {str(e)}"]


def get_service_details(
    dynamic_client, namespace: str, service_name: str, cluster_name: str = "current"
) -> Optional[ServiceDetail]:
    """
    提取Service详细信息

    Args:
        dynamic_client: Kubernetes动态客户端
        namespace: 命名空间
        service_name: Service名称
        cluster_name: 集群名称

    Returns:
        Optional[ServiceDetail]: Service详细信息，如果不存在则返回None
    """
    logger = logging.getLogger("cloudpilot.service_api")

    try:
        logger.info(
            "[Service详情][%s]开始提取Service信息: %s/%s",
            cluster_name,
            namespace,
            service_name,
        )

        # 获取Service信息
        v1 = client.CoreV1Api(dynamic_client.client)
        service = v1.read_namespaced_service(name=service_name, namespace=namespace)

        # 初始化工具类
        k8s_utils = K8sUtils(dynamic_client)
        resource_parser = ResourceParser()

        # 基本信息
        metadata = service.metadata
        spec = service.spec
        status = service.status

        # 提取端口信息
        ports = []
        for port_spec in spec.ports or []:
            port = ServicePort(
                name=port_spec.name,
                port=port_spec.port,
                target_port=(
                    str(port_spec.target_port) if port_spec.target_port else None
                ),
                protocol=port_spec.protocol or "TCP",
                node_port=port_spec.node_port,
            )
            ports.append(port)

        # 获取端点信息
        endpoint_info = get_endpoint_info(v1, namespace, service_name, cluster_name)

        # 提取外部访问信息
        external_access = None
        if spec.type in ["LoadBalancer", "NodePort", "ExternalName"]:
            external_ips = spec.external_i_ps or []
            load_balancer_ip = None
            load_balancer_ingress = []

            if status and status.load_balancer:
                load_balancer_ingress = [
                    {
                        "ip": ingress.ip,
                        "hostname": ingress.hostname,
                        "ports": [
                            {
                                "port": port.port,
                                "protocol": port.protocol,
                                "error": port.error,
                            }
                            for port in (ingress.ports or [])
                        ],
                    }
                    for ingress in (status.load_balancer.ingress or [])
                ]

                # 获取第一个可用的IP
                for ingress in status.load_balancer.ingress or []:
                    if ingress.ip:
                        load_balancer_ip = ingress.ip
                        break

            external_access = ExternalAccess(
                type=spec.type,
                external_ips=external_ips,
                load_balancer_ip=load_balancer_ip,
                load_balancer_ingress=load_balancer_ingress,
                external_name=spec.external_name,
            )

        # 分析健康状态
        service_dict = service.to_dict()
        health_score, connectivity_status, error_indicators = analyze_service_health(
            service_dict, endpoint_info
        )

        # 构建ServiceDetail对象
        service_detail = ServiceDetail(
            name=metadata.name,
            namespace=metadata.namespace,
            uid=metadata.uid,
            service_type=spec.type or "ClusterIP",
            cluster_ip=spec.cluster_ip,
            cluster_ips=spec.cluster_i_ps or [],
            creation_timestamp=k8s_utils.format_timestamp(metadata.creation_timestamp),
            age=k8s_utils.calculate_age(metadata.creation_timestamp),
            labels=metadata.labels or {},
            annotations=metadata.annotations or {},
            selector=spec.selector or {},
            ports=ports,
            endpoints=endpoint_info,
            external_access=external_access,
            session_affinity=spec.session_affinity,
            health_score=health_score,
            error_indicators=error_indicators,
            connectivity_status=connectivity_status,
        )

        logger.info(
            "[Service详情][%s]成功提取Service信息: %s/%s",
            cluster_name,
            namespace,
            service_name,
        )
        return service_detail

    except client.ApiException as e:
        if e.status == 404:
            logger.warning(
                "[Service详情][%s]Service不存在: %s/%s",
                cluster_name,
                namespace,
                service_name,
            )
            return None
        logger.error(
            "[Service详情][%s]API错误: %s/%s, 状态码: %d",
            cluster_name,
            namespace,
            service_name,
            e.status,
        )
        raise
    except Exception as e:
        logger.error(
            "[Service详情][%s]提取Service详情失败: %s/%s, 错误: %s",
            cluster_name,
            namespace,
            service_name,
            str(e),
        )
        raise


def create_server_service_router(server_mode_instance) -> APIRouter:
    """创建Server模式的Service API路由"""
    router = APIRouter(
        prefix="/k8s/resources/services", tags=["K8s Service Resources - Server"]
    )

    @router.post("/list", response_model=ServiceListResponse)
    async def list_services(request: ServiceRequest):
        """获取Service列表"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[Service列表][%s]开始获取Service列表，命名空间: %s",
                cluster_name,
                request.namespace or "所有",
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取Service列表
            v1 = client.CoreV1Api(dynamic_client.client)

            if request.namespace:
                service_list = v1.list_namespaced_service(namespace=request.namespace)
            else:
                service_list = v1.list_service_for_all_namespaces()

            services = []
            k8s_utils = K8sUtils(dynamic_client)
            for service in service_list.items:
                # 提取基本Service信息
                service_info = {
                    "name": service.metadata.name,
                    "namespace": service.metadata.namespace,
                    "type": service.spec.type or "ClusterIP",
                    "cluster_ip": service.spec.cluster_ip,
                    "external_ips": service.spec.external_i_ps or [],
                    "ports": [
                        {
                            "name": port.name,
                            "port": port.port,
                            "target_port": (
                                str(port.target_port) if port.target_port else None
                            ),
                            "protocol": port.protocol or "TCP",
                            "node_port": port.node_port,
                        }
                        for port in (service.spec.ports or [])
                    ],
                    "selector": service.spec.selector or {},
                    "creation_timestamp": k8s_utils.format_timestamp(
                        service.metadata.creation_timestamp
                    ),
                    "age": k8s_utils.calculate_age(service.metadata.creation_timestamp),
                    "labels": service.metadata.labels or {},
                    "session_affinity": service.spec.session_affinity,
                }

                # 添加LoadBalancer状态信息
                if service.spec.type == "LoadBalancer" and service.status:
                    load_balancer = service.status.load_balancer
                    if load_balancer and load_balancer.ingress:
                        service_info["load_balancer_ingress"] = [
                            {"ip": ingress.ip, "hostname": ingress.hostname}
                            for ingress in load_balancer.ingress
                        ]

                services.append(service_info)

            server_mode_instance.logger.info(
                "[Service列表][%s]成功获取%d个Service", cluster_name, len(services)
            )

            return {
                "code": 200,
                "data": {
                    "cluster_name": cluster_name,
                    "namespace": request.namespace,
                    "services": services,
                    "count": len(services),
                },
            }

        except Exception as e:
            server_mode_instance.logger.error(
                "[Service列表][%s]获取Service列表失败: %s", cluster_name, str(e)
            )
            return {"code": 500, "message": f"获取Service列表失败: {str(e)}"}

    @router.post("/detail", response_model=ServiceDetailResponse)
    async def get_service_detail(request: ServiceRequest):
        """获取Service详细信息"""
        cluster_name = request.cluster_name
        if not cluster_name:
            return {"code": 400, "message": "Server模式下cluster_name参数必需"}

        if not request.service_name:
            return {"code": 400, "message": "service_name参数必需"}

        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        try:
            # 获取集群监控器
            monitor = await server_mode_instance._get_cluster_monitor(cluster_name)
            if not monitor:
                return {"code": 404, "message": "集群不存在或连接失败"}

            server_mode_instance.logger.info(
                "[Service详情][%s]开始获取Service详情: %s/%s",
                cluster_name,
                request.namespace,
                request.service_name,
            )

            # 获取动态客户端
            dynamic_client = server_mode_instance.cluster_clients.get(cluster_name)
            if not dynamic_client:
                return {"code": 404, "message": "集群客户端不存在"}

            # 获取Service详情
            service_detail = get_service_details(
                dynamic_client, request.namespace, request.service_name, cluster_name
            )

            if not service_detail:
                return {
                    "code": 404,
                    "message": f"Service {request.namespace}/{request.service_name} 不存在",
                }

            server_mode_instance.logger.info(
                "[Service详情][%s]成功获取Service详情: %s/%s",
                cluster_name,
                request.namespace,
                request.service_name,
            )

            return {"code": 200, "data": service_detail}

        except Exception as e:
            server_mode_instance.logger.error(
                "[Service详情][%s]获取Service详情失败: %s/%s, 错误: %s",
                cluster_name,
                request.namespace,
                request.service_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Service详情失败: {str(e)}"}

    return router


def create_instant_service_router(instant_mode_instance) -> APIRouter:
    """创建Instant模式的Service API路由"""
    router = APIRouter(
        prefix="/k8s/resources/services", tags=["K8s Service Resources - Instant"]
    )

    @router.post("/list", response_model=ServiceListResponse)
    async def list_services(request: ServiceRequest):
        """获取Service列表"""
        try:
            instant_mode_instance.logger.info(
                "[Service列表][当前集群]开始获取Service列表，命名空间: %s",
                request.namespace or "所有",
            )

            # 获取Service列表
            v1 = client.CoreV1Api(instant_mode_instance.k8s_client)

            if request.namespace:
                service_list = v1.list_namespaced_service(namespace=request.namespace)
            else:
                service_list = v1.list_service_for_all_namespaces()

            services = []
            k8s_utils = K8sUtils(instant_mode_instance.dynamic_client)
            for service in service_list.items:
                # 提取基本Service信息
                service_info = {
                    "name": service.metadata.name,
                    "namespace": service.metadata.namespace,
                    "type": service.spec.type or "ClusterIP",
                    "cluster_ip": service.spec.cluster_ip,
                    "external_ips": service.spec.external_i_ps or [],
                    "ports": [
                        {
                            "name": port.name,
                            "port": port.port,
                            "target_port": (
                                str(port.target_port) if port.target_port else None
                            ),
                            "protocol": port.protocol or "TCP",
                            "node_port": port.node_port,
                        }
                        for port in (service.spec.ports or [])
                    ],
                    "selector": service.spec.selector or {},
                    "creation_timestamp": k8s_utils.format_timestamp(
                        service.metadata.creation_timestamp
                    ),
                    "age": k8s_utils.calculate_age(service.metadata.creation_timestamp),
                    "labels": service.metadata.labels or {},
                    "session_affinity": service.spec.session_affinity,
                }

                # 添加LoadBalancer状态信息
                if service.spec.type == "LoadBalancer" and service.status:
                    load_balancer = service.status.load_balancer
                    if load_balancer and load_balancer.ingress:
                        service_info["load_balancer_ingress"] = [
                            {"ip": ingress.ip, "hostname": ingress.hostname}
                            for ingress in load_balancer.ingress
                        ]

                services.append(service_info)

            instant_mode_instance.logger.info(
                "[Service列表][当前集群]成功获取%d个Service", len(services)
            )

            return {
                "code": 200,
                "data": {
                    "namespace": request.namespace,
                    "services": services,
                    "count": len(services),
                },
            }

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Service列表][当前集群]获取Service列表失败: %s", str(e)
            )
            return {"code": 500, "message": f"获取Service列表失败: {str(e)}"}

    @router.post("/detail", response_model=ServiceDetailResponse)
    async def get_service_detail(request: ServiceRequest):
        """获取Service详细信息"""
        if not request.service_name:
            return {"code": 400, "message": "service_name参数必需"}

        if not request.namespace:
            return {"code": 400, "message": "namespace参数必需"}

        try:
            instant_mode_instance.logger.info(
                "[Service详情][当前集群]开始获取Service详情: %s/%s",
                request.namespace,
                request.service_name,
            )

            # 获取Service详情
            service_detail = get_service_details(
                instant_mode_instance.dynamic_client,
                request.namespace,
                request.service_name,
                "当前集群",
            )

            if not service_detail:
                return {
                    "code": 404,
                    "message": f"Service {request.namespace}/{request.service_name} 不存在",
                }

            instant_mode_instance.logger.info(
                "[Service详情][当前集群]成功获取Service详情: %s/%s",
                request.namespace,
                request.service_name,
            )

            return {"code": 200, "data": service_detail}

        except Exception as e:
            instant_mode_instance.logger.error(
                "[Service详情][当前集群]获取Service详情失败: %s/%s, 错误: %s",
                request.namespace,
                request.service_name,
                str(e),
            )
            return {"code": 500, "message": f"获取Service详情失败: {str(e)}"}

    return router
