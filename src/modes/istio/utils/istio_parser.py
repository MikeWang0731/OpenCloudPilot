"""
Istio Resource Parser Utilities

This module provides common parsing operations for Istio resources,
following the same patterns as the existing K8s resource parsers.
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class IstioMetadata(BaseModel):
    """Common Istio resource metadata"""

    name: str
    namespace: str
    labels: Dict[str, str] = {}
    annotations: Dict[str, str] = {}
    creation_timestamp: Optional[datetime] = None
    resource_version: Optional[str] = None
    uid: Optional[str] = None


class IstioResourceStatus(BaseModel):
    """Common Istio resource status information"""

    phase: str = "Unknown"
    conditions: List[Dict[str, Any]] = []
    observed_generation: Optional[int] = None
    last_updated: Optional[datetime] = None


class IstioParser:
    """
    Utility class for parsing Istio resources and extracting common information.
    Provides standardized parsing methods for different Istio resource types.
    """

    @staticmethod
    def parse_istio_workload(resource: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Istio workload resources (Deployments for istiod, istio-ingressgateway).

        Args:
            resource: Raw Kubernetes resource dictionary

        Returns:
            Parsed workload information with standardized structure
        """
        try:
            metadata = IstioParser.extract_istio_metadata(resource)

            # Extract deployment-specific information
            spec = resource.get("spec", {})
            status = resource.get("status", {})

            workload_info = {
                "metadata": metadata.model_dump(),
                "replicas": {
                    "desired": spec.get("replicas", 0),
                    "ready": status.get("ready_replicas", 0),
                    "available": status.get("available_replicas", 0),
                    "updated": status.get("updated_replicas", 0),
                },
                "containers": IstioParser._extract_container_info(spec),
                "conditions": status.get("conditions", []),
                "strategy": spec.get("strategy", {}),
                "selector": spec.get("selector", {}),
            }

            logger.debug(
                "[Istio解析器][未知集群]成功解析工作负载 - 资源名称=%s",
                metadata.name,
            )
            return workload_info

        except Exception as e:
            logger.error(
                "[Istio解析器][未知集群]解析工作负载失败 - 错误类型=%s, 错误信息=%s",
                type(e).__name__,
                str(e),
            )
            raise

    @staticmethod
    def extract_istio_metadata(resource: Dict[str, Any]) -> IstioMetadata:
        """
        Extract common Istio metadata from resource.

        Args:
            resource: Raw Kubernetes resource dictionary

        Returns:
            Structured metadata information
        """
        metadata = resource.get("metadata", {})

        # Parse creation timestamp
        creation_timestamp = None
        if "creationTimestamp" in metadata:
            try:
                creation_timestamp = datetime.fromisoformat(
                    metadata["creationTimestamp"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                logger.warning(
                    "[Istio解析器][未知集群]时间戳格式无效 - 时间戳=%s",
                    metadata.get("creationTimestamp"),
                )

        return IstioMetadata(
            name=metadata.get("name", ""),
            namespace=metadata.get("namespace", "default"),
            labels=metadata.get("labels", {}),
            annotations=metadata.get("annotations", {}),
            creation_timestamp=creation_timestamp,
            resource_version=metadata.get("resourceVersion"),
            uid=metadata.get("uid"),
        )

    @staticmethod
    def parse_traffic_config(resource: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse traffic management configurations (Gateway, VirtualService, DestinationRule).

        Args:
            resource: Raw Istio resource dictionary

        Returns:
            Parsed traffic configuration with standardized structure
        """
        try:
            metadata = IstioParser.extract_istio_metadata(resource)
            spec = resource.get("spec", {})
            status = resource.get("status", {})

            config_info = {
                "metadata": metadata.model_dump(),
                "spec": spec,
                "status": status,
                "kind": resource.get("kind", ""),
                "api_version": resource.get("apiVersion", ""),
            }

            logger.debug(
                "[Istio解析器][未知集群]成功解析流量配置 - 资源名称=%s",
                metadata.name,
            )
            return config_info

        except Exception as e:
            logger.error(
                "[Istio解析器][未知集群]解析流量配置失败 - 错误类型=%s, 错误信息=%s",
                type(e).__name__,
                str(e),
            )
            raise

    @staticmethod
    def validate_istio_config(resource: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate Istio resource configurations and identify common issues.

        Args:
            resource: Istio resource dictionary

        Returns:
            Validation results with issues and recommendations
        """
        validation_result = {
            "is_valid": True,
            "issues": [],
            "warnings": [],
            "recommendations": [],
        }

        try:
            metadata = resource.get("metadata", {})
            spec = resource.get("spec", {})
            kind = resource.get("kind", "")

            # Basic validation
            if not metadata.get("name"):
                validation_result["issues"].append("Resource name is missing")
                validation_result["is_valid"] = False

            if not spec:
                validation_result["issues"].append("Resource spec is empty")
                validation_result["is_valid"] = False

            # Kind-specific validation
            if kind == "Gateway":
                gateway_result = IstioParser._validate_gateway_config(spec)
                validation_result["issues"].extend(gateway_result["issues"])
                validation_result["warnings"].extend(gateway_result["warnings"])
                validation_result["recommendations"].extend(
                    gateway_result["recommendations"]
                )
                if gateway_result["issues"]:
                    validation_result["is_valid"] = False
            elif kind == "VirtualService":
                vs_result = IstioParser._validate_virtualservice_config(spec)
                validation_result["issues"].extend(vs_result["issues"])
                validation_result["warnings"].extend(vs_result["warnings"])
                validation_result["recommendations"].extend(
                    vs_result["recommendations"]
                )
                if vs_result["issues"]:
                    validation_result["is_valid"] = False
            elif kind == "DestinationRule":
                dr_result = IstioParser._validate_destinationrule_config(spec)
                validation_result["issues"].extend(dr_result["issues"])
                validation_result["warnings"].extend(dr_result["warnings"])
                validation_result["recommendations"].extend(
                    dr_result["recommendations"]
                )
                if dr_result["issues"]:
                    validation_result["is_valid"] = False

            logger.debug(
                "[Istio解析器][未知集群]配置验证完成 - 资源类型=%s, 资源名称=%s",
                kind,
                metadata.get("name"),
            )
            return validation_result

        except Exception as e:
            logger.error(
                "[Istio解析器][未知集群]配置验证失败 - 错误类型=%s, 错误信息=%s",
                type(e).__name__,
                str(e),
            )
            validation_result["is_valid"] = False
            validation_result["issues"].append(f"Validation error: {str(e)}")
            return validation_result

    @staticmethod
    def _extract_container_info(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract container information from deployment spec"""
        containers = []
        template = spec.get("template", {}).get("spec", {})

        for container in template.get("containers", []):
            container_info = {
                "name": container.get("name", ""),
                "image": container.get("image", ""),
                "ports": container.get("ports", []),
                "resources": container.get("resources", {}),
                "env": container.get("env", []),
                "volume_mounts": container.get("volumeMounts", []),
            }
            containers.append(container_info)

        return containers

    @staticmethod
    def _validate_gateway_config(spec: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Gateway configuration"""
        result = {"issues": [], "warnings": [], "recommendations": []}

        servers = spec.get("servers", [])
        if not servers:
            result["issues"].append("Gateway has no servers configured")

        for i, server in enumerate(servers):
            if not server.get("hosts"):
                result["issues"].append(f"Server {i} has no hosts configured")

            port = server.get("port", {})
            if not port.get("number"):
                result["issues"].append(f"Server {i} has no port number configured")

        return result

    @staticmethod
    def _validate_virtualservice_config(spec: Dict[str, Any]) -> Dict[str, Any]:
        """Validate VirtualService configuration"""
        result = {"issues": [], "warnings": [], "recommendations": []}

        hosts = spec.get("hosts", [])
        if not hosts:
            result["issues"].append("VirtualService has no hosts configured")

        http_routes = spec.get("http", [])
        tcp_routes = spec.get("tcp", [])
        tls_routes = spec.get("tls", [])

        if not (http_routes or tcp_routes or tls_routes):
            result["issues"].append("VirtualService has no routing rules configured")

        # Validate HTTP routes
        for i, route in enumerate(http_routes):
            if not route.get("route"):
                result["issues"].append(f"HTTP route {i} has no destination configured")

        return result

    @staticmethod
    def _validate_destinationrule_config(spec: Dict[str, Any]) -> Dict[str, Any]:
        """Validate DestinationRule configuration"""
        result = {"issues": [], "warnings": [], "recommendations": []}

        host = spec.get("host")
        if not host:
            result["issues"].append("DestinationRule has no host configured")

        traffic_policy = spec.get("trafficPolicy", {})
        subsets = spec.get("subsets", [])

        if not traffic_policy and not subsets:
            result["warnings"].append(
                "DestinationRule has no traffic policy or subsets configured"
            )

        return result
