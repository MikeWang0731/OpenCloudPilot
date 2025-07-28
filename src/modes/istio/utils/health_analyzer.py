"""
Istio Health Analyzer

This module provides health analysis and scoring algorithms for Istio resources,
including workloads and service mesh components.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
from enum import Enum
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status enumeration"""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class HealthScore(BaseModel):
    """Health score with detailed breakdown"""

    overall_score: float  # 0-100
    status: HealthStatus
    component_scores: Dict[str, float]
    issues: List[str]
    recommendations: List[str]
    last_updated: datetime


class HealthAnalyzer:
    """
    Health analyzer for Istio resources with scoring algorithms.
    Provides comprehensive health assessment for workloads and service mesh components.
    """

    # Scoring weights for different health components
    WORKLOAD_WEIGHTS = {
        "availability": 0.4,
        "performance": 0.3,
        "configuration": 0.2,
        "security": 0.1,
    }

    TRAFFIC_CONFIG_WEIGHTS = {
        "configuration": 0.5,
        "connectivity": 0.3,
        "security": 0.2,
    }

    def __init__(self):
        """Initialize the health analyzer"""
        self.scoring_cache = {}
        self.cache_ttl = timedelta(minutes=5)

    def analyze_workload_health(self, workload_data: Dict[str, Any]) -> HealthScore:
        """
        Analyze health of Istio workloads (istiod, istio-ingressgateway).

        Args:
            workload_data: Parsed workload information from IstioParser

        Returns:
            Comprehensive health score with breakdown
        """
        try:
            workload_name = workload_data.get("metadata", {}).get("name", "unknown")
            logger.debug(
                "[健康分析器][未知集群]开始分析工作负载健康状态 - 工作负载名称=%s",
                workload_name,
            )

            # Check cache first
            cache_key = f"workload_{workload_name}_{workload_data.get('metadata', {}).get('resource_version', '')}"
            if self._is_cache_valid(cache_key):
                return self.scoring_cache[cache_key]

            component_scores = {}
            issues = []
            recommendations = []

            # Analyze availability
            availability_score, avail_issues, avail_recs = (
                self._analyze_workload_availability(workload_data)
            )
            component_scores["availability"] = availability_score
            issues.extend(avail_issues)
            recommendations.extend(avail_recs)

            # Analyze performance
            performance_score, perf_issues, perf_recs = (
                self._analyze_workload_performance(workload_data)
            )
            component_scores["performance"] = performance_score
            issues.extend(perf_issues)
            recommendations.extend(perf_recs)

            # Analyze configuration
            config_score, config_issues, config_recs = (
                self._analyze_workload_configuration(workload_data)
            )
            component_scores["configuration"] = config_score
            issues.extend(config_issues)
            recommendations.extend(config_recs)

            # Analyze security
            security_score, sec_issues, sec_recs = self._analyze_workload_security(
                workload_data
            )
            component_scores["security"] = security_score
            issues.extend(sec_issues)
            recommendations.extend(sec_recs)

            # Calculate overall score
            overall_score = sum(
                score * self.WORKLOAD_WEIGHTS[component]
                for component, score in component_scores.items()
            )

            # Determine status
            status = self._determine_health_status(overall_score, issues)

            health_score = HealthScore(
                overall_score=round(overall_score, 2),
                status=status,
                component_scores=component_scores,
                issues=issues,
                recommendations=recommendations,
                last_updated=datetime.now(),
            )

            # Cache result
            self.scoring_cache[cache_key] = health_score

            logger.info(
                "[健康分析器][未知集群]工作负载健康分析完成 - 工作负载名称=%s, 健康状态=%s, 健康分数=%.1f",
                workload_name,
                status.value,
                overall_score,
            )
            return health_score

        except Exception as e:
            logger.error(
                "[健康分析器][未知集群]工作负载健康分析失败 - 错误类型=%s, 错误信息=%s",
                type(e).__name__,
                str(e),
            )
            return HealthScore(
                overall_score=0.0,
                status=HealthStatus.UNKNOWN,
                component_scores={},
                issues=[f"Health analysis failed: {str(e)}"],
                recommendations=["Check workload configuration and status"],
                last_updated=datetime.now(),
            )

    def analyze_traffic_config_health(self, config_data: Dict[str, Any]) -> HealthScore:
        """
        Analyze health of Istio traffic configurations (Gateway, VirtualService, DestinationRule).

        Args:
            config_data: Parsed traffic configuration from IstioParser

        Returns:
            Comprehensive health score with breakdown
        """
        try:
            config_name = config_data.get("metadata", {}).get("name", "unknown")
            config_kind = config_data.get("kind", "unknown")
            logger.debug(
                "[健康分析器][未知集群]开始分析流量配置健康状态 - 配置类型=%s, 配置名称=%s",
                config_kind,
                config_name,
            )

            # Check cache first
            cache_key = f"config_{config_name}_{config_data.get('metadata', {}).get('resource_version', '')}"
            if self._is_cache_valid(cache_key):
                return self.scoring_cache[cache_key]

            component_scores = {}
            issues = []
            recommendations = []

            # Analyze configuration validity
            config_score, config_issues, config_recs = (
                self._analyze_traffic_configuration(config_data)
            )
            component_scores["configuration"] = config_score
            issues.extend(config_issues)
            recommendations.extend(config_recs)

            # Analyze connectivity
            connectivity_score, conn_issues, conn_recs = (
                self._analyze_traffic_connectivity(config_data)
            )
            component_scores["connectivity"] = connectivity_score
            issues.extend(conn_issues)
            recommendations.extend(conn_recs)

            # Analyze security
            security_score, sec_issues, sec_recs = self._analyze_traffic_security(
                config_data
            )
            component_scores["security"] = security_score
            issues.extend(sec_issues)
            recommendations.extend(sec_recs)

            # Calculate overall score
            overall_score = sum(
                score * self.TRAFFIC_CONFIG_WEIGHTS[component]
                for component, score in component_scores.items()
            )

            # Determine status
            status = self._determine_health_status(overall_score, issues)

            health_score = HealthScore(
                overall_score=round(overall_score, 2),
                status=status,
                component_scores=component_scores,
                issues=issues,
                recommendations=recommendations,
                last_updated=datetime.now(),
            )

            # Cache result
            self.scoring_cache[cache_key] = health_score

            logger.info(
                "[健康分析器][未知集群]流量配置健康分析完成 - 配置类型=%s, 配置名称=%s, 健康状态=%s, 健康分数=%.1f",
                config_kind,
                config_name,
                status.value,
                overall_score,
            )
            return health_score

        except Exception as e:
            logger.error(
                "[健康分析器][未知集群]流量配置健康分析失败 - 错误类型=%s, 错误信息=%s",
                type(e).__name__,
                str(e),
            )
            return HealthScore(
                overall_score=0.0,
                status=HealthStatus.UNKNOWN,
                component_scores={},
                issues=[f"Health analysis failed: {str(e)}"],
                recommendations=["Check traffic configuration and status"],
                last_updated=datetime.now(),
            )

    def _analyze_workload_availability(
        self, workload_data: Dict[str, Any]
    ) -> Tuple[float, List[str], List[str]]:
        """Analyze workload availability metrics"""
        score = 100.0
        issues = []
        recommendations = []

        replicas = workload_data.get("replicas", {})
        desired = replicas.get("desired", 0)
        ready = replicas.get("ready", 0)
        available = replicas.get("available", 0)

        if desired == 0:
            score = 0.0
            issues.append("No replicas desired - workload is scaled down")
            recommendations.append("Scale up workload if it should be running")
        elif ready == 0:
            score = 0.0
            issues.append("No replicas are ready")
            recommendations.append("Check pod status and resource availability")
        elif ready < desired:
            availability_ratio = ready / desired
            score = availability_ratio * 100
            issues.append(f"Only {ready}/{desired} replicas are ready")
            recommendations.append("Investigate why some replicas are not ready")

        # Check conditions for additional issues
        conditions = workload_data.get("conditions", [])
        for condition in conditions:
            if (
                condition.get("type") == "Available"
                and condition.get("status") != "True"
            ):
                score = min(score, 50.0)
                issues.append(f"Availability condition is {condition.get('status')}")
                recommendations.append("Check deployment conditions and events")

        return score, issues, recommendations

    def _analyze_workload_performance(
        self, workload_data: Dict[str, Any]
    ) -> Tuple[float, List[str], List[str]]:
        """Analyze workload performance metrics"""
        score = 100.0
        issues = []
        recommendations = []

        containers = workload_data.get("containers", [])

        for container in containers:
            resources = container.get("resources", {})

            # Check if resource limits are set
            limits = resources.get("limits", {})
            requests = resources.get("requests", {})

            if not limits:
                score = min(score, 80.0)
                issues.append(
                    f"Container {container.get('name')} has no resource limits"
                )
                recommendations.append(
                    "Set resource limits to prevent resource exhaustion"
                )

            if not requests:
                score = min(score, 85.0)
                issues.append(
                    f"Container {container.get('name')} has no resource requests"
                )
                recommendations.append("Set resource requests for proper scheduling")

        return score, issues, recommendations

    def _analyze_workload_configuration(
        self, workload_data: Dict[str, Any]
    ) -> Tuple[float, List[str], List[str]]:
        """Analyze workload configuration"""
        score = 100.0
        issues = []
        recommendations = []

        metadata = workload_data.get("metadata", {})
        labels = metadata.get("labels", {})

        # Check for required Istio labels
        if "app" not in labels:
            score = min(score, 90.0)
            issues.append("Missing 'app' label")
            recommendations.append("Add 'app' label for proper Istio service discovery")

        if "version" not in labels:
            score = min(score, 95.0)
            recommendations.append(
                "Consider adding 'version' label for traffic management"
            )

        # Check strategy
        strategy = workload_data.get("strategy", {})
        if strategy.get("type") == "Recreate":
            score = min(score, 85.0)
            recommendations.append(
                "Consider using RollingUpdate strategy for zero-downtime deployments"
            )

        return score, issues, recommendations

    def _analyze_workload_security(
        self, workload_data: Dict[str, Any]
    ) -> Tuple[float, List[str], List[str]]:
        """Analyze workload security configuration"""
        score = 100.0
        issues = []
        recommendations = []

        containers = workload_data.get("containers", [])

        for container in containers:
            # Check for security context
            # Note: This would need to be extracted from the full pod spec
            # For now, we'll do basic checks on what's available

            # Check if running as root (would need security context)
            recommendations.append("Ensure containers run with non-root user")
            recommendations.append("Set read-only root filesystem where possible")

        return score, issues, recommendations

    def _analyze_traffic_configuration(
        self, config_data: Dict[str, Any]
    ) -> Tuple[float, List[str], List[str]]:
        """Analyze traffic configuration validity"""
        score = 100.0
        issues = []
        recommendations = []

        kind = config_data.get("kind", "")
        spec = config_data.get("spec", {})

        if kind == "Gateway":
            servers = spec.get("servers", [])
            if not servers:
                score = 0.0
                issues.append("Gateway has no servers configured")

            for server in servers:
                if not server.get("hosts"):
                    score = min(score, 50.0)
                    issues.append("Gateway server missing hosts")

                tls = server.get("tls", {})
                if tls and not tls.get("credentialName"):
                    score = min(score, 80.0)
                    recommendations.append(
                        "Configure TLS credentials for secure connections"
                    )

        elif kind == "VirtualService":
            if not spec.get("hosts"):
                score = 0.0
                issues.append("VirtualService has no hosts configured")

            http_routes = spec.get("http", [])
            if not http_routes:
                score = min(score, 70.0)
                recommendations.append("Consider adding HTTP routing rules")

        elif kind == "DestinationRule":
            if not spec.get("host"):
                score = 0.0
                issues.append("DestinationRule has no host configured")

        return score, issues, recommendations

    def _analyze_traffic_connectivity(
        self, config_data: Dict[str, Any]
    ) -> Tuple[float, List[str], List[str]]:
        """Analyze traffic connectivity"""
        score = 100.0
        issues = []
        recommendations = []

        # This would typically involve checking if referenced services exist
        # For now, we'll provide basic connectivity recommendations
        recommendations.append("Verify that referenced services and endpoints exist")
        recommendations.append("Test connectivity using istioctl proxy-config commands")

        return score, issues, recommendations

    def _analyze_traffic_security(
        self, config_data: Dict[str, Any]
    ) -> Tuple[float, List[str], List[str]]:
        """Analyze traffic security configuration"""
        score = 100.0
        issues = []
        recommendations = []

        kind = config_data.get("kind", "")
        spec = config_data.get("spec", {})

        if kind == "Gateway":
            servers = spec.get("servers", [])
            for server in servers:
                tls = server.get("tls", {})
                if not tls:
                    score = min(score, 70.0)
                    recommendations.append(
                        "Consider enabling TLS for secure connections"
                    )
                elif tls.get("mode") == "PASSTHROUGH":
                    recommendations.append(
                        "Verify TLS passthrough configuration is intentional"
                    )

        elif kind == "DestinationRule":
            traffic_policy = spec.get("trafficPolicy", {})
            tls = traffic_policy.get("tls", {})
            if not tls:
                score = min(score, 80.0)
                recommendations.append(
                    "Consider enabling mTLS for service-to-service communication"
                )

        return score, issues, recommendations

    def _determine_health_status(self, score: float, issues: List[str]) -> HealthStatus:
        """Determine health status based on score and issues"""
        critical_issues = [
            issue
            for issue in issues
            if any(
                keyword in issue.lower()
                for keyword in ["no replicas", "not ready", "missing", "failed"]
            )
        ]

        if critical_issues or score < 50:
            return HealthStatus.CRITICAL
        elif score < 80:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached result is still valid"""
        if cache_key not in self.scoring_cache:
            return False

        cached_result = self.scoring_cache[cache_key]
        return datetime.now() - cached_result.last_updated < self.cache_ttl

    def clear_cache(self):
        """Clear the scoring cache"""
        self.scoring_cache.clear()
        logger.debug("[健康分析器][未知集群]缓存已清除")

    def calculate_workload_health(self, workload_data: Dict[str, Any]) -> HealthScore:
        """
        Calculate health score for Istio workloads (istiod, istio-ingressgateway).
        This is the main entry point for workload health analysis.

        Args:
            workload_data: Parsed workload information from IstioParser

        Returns:
            Comprehensive health score with breakdown
        """
        return self.analyze_workload_health(workload_data)

    def analyze_component_health(self, component_data: Dict[str, Any]) -> HealthScore:
        """
        Analyze health of service mesh components (Gateway, VirtualService, DestinationRule).
        This is the main entry point for component health analysis.

        Args:
            component_data: Parsed component configuration from IstioParser

        Returns:
            Comprehensive health score with breakdown
        """
        return self.analyze_traffic_config_health(component_data)

    def detect_configuration_issues(self, resource_data: Dict[str, Any]) -> List[str]:
        """
        Detect common configuration issues in Istio resources.

        Args:
            resource_data: Parsed resource data from IstioParser

        Returns:
            List of detected configuration issues
        """
        issues = []
        kind = resource_data.get("kind", "")
        spec = resource_data.get("spec", {})
        metadata = resource_data.get("metadata", {})

        try:
            logger.debug("[健康分析器][未知集群]开始检测配置问题 - 资源类型=%s", kind)

            # Common issues across all resources
            if not metadata.get("name"):
                issues.append("Resource missing name in metadata")

            if not metadata.get("namespace"):
                issues.append("Resource missing namespace in metadata")

            # Resource-specific issue detection
            if kind == "Gateway":
                issues.extend(self._detect_gateway_issues(spec))
            elif kind == "VirtualService":
                issues.extend(self._detect_virtualservice_issues(spec))
            elif kind == "DestinationRule":
                issues.extend(self._detect_destinationrule_issues(spec))
            elif kind in ["Deployment", "ReplicaSet"]:
                issues.extend(self._detect_workload_issues(resource_data))

            logger.debug(
                "[健康分析器][未知集群]配置问题检测完成 - 问题数量=%d", len(issues)
            )
            return issues

        except Exception as e:
            logger.error(
                "[健康分析器][未知集群]配置问题检测失败 - 错误类型=%s, 错误信息=%s",
                type(e).__name__,
                str(e),
            )
            return [f"Configuration analysis failed: {str(e)}"]

    def generate_health_recommendations(
        self, resource_data: Dict[str, Any], health_score: Optional[HealthScore] = None
    ) -> List[str]:
        """
        Generate improvement recommendations for Istio resources.

        Args:
            resource_data: Parsed resource data from IstioParser
            health_score: Optional existing health score for context

        Returns:
            List of improvement recommendations
        """
        recommendations = []
        kind = resource_data.get("kind", "")
        spec = resource_data.get("spec", {})

        try:
            logger.debug(f"[Health Analyzer] Generating recommendations for {kind}")

            # Generate health score if not provided
            if health_score is None:
                if kind in ["Deployment", "ReplicaSet"]:
                    health_score = self.calculate_workload_health(resource_data)
                else:
                    health_score = self.analyze_component_health(resource_data)

            # Use existing recommendations from health score
            recommendations.extend(health_score.recommendations)

            # Add resource-specific recommendations
            if kind == "Gateway":
                recommendations.extend(
                    self._generate_gateway_recommendations(spec, health_score)
                )
            elif kind == "VirtualService":
                recommendations.extend(
                    self._generate_virtualservice_recommendations(spec, health_score)
                )
            elif kind == "DestinationRule":
                recommendations.extend(
                    self._generate_destinationrule_recommendations(spec, health_score)
                )
            elif kind in ["Deployment", "ReplicaSet"]:
                recommendations.extend(
                    self._generate_workload_recommendations(resource_data, health_score)
                )

            # Remove duplicates while preserving order
            unique_recommendations = []
            seen = set()
            for rec in recommendations:
                if rec not in seen:
                    unique_recommendations.append(rec)
                    seen.add(rec)

            logger.debug(
                f"[Health Analyzer] Generated {len(unique_recommendations)} recommendations"
            )
            return unique_recommendations

        except Exception as e:
            logger.error(
                "[健康分析器][未知集群]生成建议失败 - 错误类型=%s, 错误信息=%s",
                type(e).__name__,
                str(e),
            )
            return ["Unable to generate recommendations due to analysis error"]

    def _detect_gateway_issues(self, spec: Dict[str, Any]) -> List[str]:
        """Detect Gateway-specific configuration issues"""
        issues = []
        servers = spec.get("servers", [])

        if not servers:
            issues.append("Gateway has no servers configured")
            return issues

        for i, server in enumerate(servers):
            server_prefix = f"Server {i+1}"

            if not server.get("hosts"):
                issues.append(f"{server_prefix}: Missing hosts configuration")

            port = server.get("port", {})
            if not port:
                issues.append(f"{server_prefix}: Missing port configuration")
            elif not port.get("number"):
                issues.append(f"{server_prefix}: Missing port number")
            elif not port.get("protocol"):
                issues.append(f"{server_prefix}: Missing port protocol")

            tls = server.get("tls", {})
            if tls:
                mode = tls.get("mode")
                if mode in ["SIMPLE", "MUTUAL"] and not tls.get("credentialName"):
                    issues.append(
                        f"{server_prefix}: TLS mode {mode} requires credentialName"
                    )

        return issues

    def _detect_virtualservice_issues(self, spec: Dict[str, Any]) -> List[str]:
        """Detect VirtualService-specific configuration issues"""
        issues = []

        if not spec.get("hosts"):
            issues.append("VirtualService missing hosts configuration")

        http_routes = spec.get("http", [])
        tcp_routes = spec.get("tcp", [])
        tls_routes = spec.get("tls", [])

        if not http_routes and not tcp_routes and not tls_routes:
            issues.append("VirtualService has no routing rules configured")

        # Check HTTP routes
        for i, route in enumerate(http_routes):
            route_prefix = f"HTTP route {i+1}"

            if (
                not route.get("route")
                and not route.get("redirect")
                and not route.get("directResponse")
            ):
                issues.append(
                    f"{route_prefix}: Missing route action (route/redirect/directResponse)"
                )

            if route.get("route"):
                for j, destination in enumerate(route["route"]):
                    if not destination.get("destination", {}).get("host"):
                        issues.append(f"{route_prefix} destination {j+1}: Missing host")

        return issues

    def _detect_destinationrule_issues(self, spec: Dict[str, Any]) -> List[str]:
        """Detect DestinationRule-specific configuration issues"""
        issues = []

        if not spec.get("host"):
            issues.append("DestinationRule missing host configuration")

        subsets = spec.get("subsets", [])
        for i, subset in enumerate(subsets):
            subset_prefix = f"Subset {i+1}"

            if not subset.get("name"):
                issues.append(f"{subset_prefix}: Missing name")

            if not subset.get("labels"):
                issues.append(f"{subset_prefix}: Missing labels for subset selection")

        return issues

    def _detect_workload_issues(self, workload_data: Dict[str, Any]) -> List[str]:
        """Detect workload-specific configuration issues"""
        issues = []

        replicas = workload_data.get("replicas", {})
        if replicas.get("desired", 0) == 0:
            issues.append("Workload is scaled to zero replicas")

        containers = workload_data.get("containers", [])
        for container in containers:
            container_name = container.get("name", "unknown")
            resources = container.get("resources", {})

            if not resources.get("limits"):
                issues.append(f"Container {container_name}: Missing resource limits")

            if not resources.get("requests"):
                issues.append(f"Container {container_name}: Missing resource requests")

        return issues

    def _generate_gateway_recommendations(
        self, spec: Dict[str, Any], health_score: HealthScore
    ) -> List[str]:
        """Generate Gateway-specific recommendations"""
        recommendations = []

        servers = spec.get("servers", [])
        for server in servers:
            tls = server.get("tls", {})
            if not tls:
                recommendations.append("Consider enabling TLS for secure connections")
            elif tls.get("mode") == "SIMPLE":
                recommendations.append(
                    "Consider upgrading to mutual TLS (mTLS) for enhanced security"
                )

            hosts = server.get("hosts", [])
            if "*" in hosts:
                recommendations.append(
                    "Consider using specific hostnames instead of wildcards for better security"
                )

        if health_score.overall_score < 80:
            recommendations.append(
                "Review Gateway configuration for security and reliability improvements"
            )

        return recommendations

    def _generate_virtualservice_recommendations(
        self, spec: Dict[str, Any], health_score: HealthScore
    ) -> List[str]:
        """Generate VirtualService-specific recommendations"""
        recommendations = []

        http_routes = spec.get("http", [])
        if not http_routes:
            recommendations.append(
                "Consider adding HTTP routing rules for traffic management"
            )

        for route in http_routes:
            if not route.get("timeout"):
                recommendations.append("Consider setting timeouts for HTTP routes")

            if not route.get("retries"):
                recommendations.append(
                    "Consider configuring retry policies for resilience"
                )

            # Check for fault injection
            fault = route.get("fault")
            if fault:
                recommendations.append(
                    "Review fault injection configuration - ensure it's intentional"
                )

        if health_score.overall_score < 80:
            recommendations.append(
                "Review VirtualService routing rules for optimization"
            )

        return recommendations

    def _generate_destinationrule_recommendations(
        self, spec: Dict[str, Any], health_score: HealthScore
    ) -> List[str]:
        """Generate DestinationRule-specific recommendations"""
        recommendations = []

        traffic_policy = spec.get("trafficPolicy", {})
        if not traffic_policy:
            recommendations.append(
                "Consider adding traffic policies for load balancing and resilience"
            )

        if traffic_policy:
            if not traffic_policy.get("loadBalancer"):
                recommendations.append("Consider configuring load balancing strategy")

            if not traffic_policy.get("connectionPool"):
                recommendations.append("Consider setting connection pool limits")

            if not traffic_policy.get("outlierDetection"):
                recommendations.append(
                    "Consider enabling outlier detection for unhealthy instances"
                )

        if health_score.overall_score < 80:
            recommendations.append(
                "Review DestinationRule traffic policies for performance optimization"
            )

        return recommendations

    def _generate_workload_recommendations(
        self, workload_data: Dict[str, Any], health_score: HealthScore
    ) -> List[str]:
        """Generate workload-specific recommendations"""
        recommendations = []

        replicas = workload_data.get("replicas", {})
        if replicas.get("desired", 0) < 2:
            recommendations.append(
                "Consider running multiple replicas for high availability"
            )

        strategy = workload_data.get("strategy", {})
        if strategy.get("type") == "Recreate":
            recommendations.append(
                "Consider using RollingUpdate strategy for zero-downtime deployments"
            )

        if health_score.overall_score < 80:
            recommendations.append(
                "Review workload configuration for reliability improvements"
            )

        return recommendations

    def get_health_summary(self, health_scores: List[HealthScore]) -> Dict[str, Any]:
        """
        Generate a summary of multiple health scores.

        Args:
            health_scores: List of health scores to summarize

        Returns:
            Summary statistics and overall health status
        """
        if not health_scores:
            return {
                "total_resources": 0,
                "average_score": 0.0,
                "status_distribution": {},
                "common_issues": [],
                "top_recommendations": [],
            }

        total_score = sum(score.overall_score for score in health_scores)
        average_score = total_score / len(health_scores)

        # Count status distribution
        status_counts = {}
        for score in health_scores:
            status = score.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        # Collect common issues and recommendations
        all_issues = []
        all_recommendations = []
        for score in health_scores:
            all_issues.extend(score.issues)
            all_recommendations.extend(score.recommendations)

        # Find most common issues and recommendations
        issue_counts = {}
        for issue in all_issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1

        rec_counts = {}
        for rec in all_recommendations:
            rec_counts[rec] = rec_counts.get(rec, 0) + 1

        common_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]
        top_recommendations = sorted(
            rec_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "total_resources": len(health_scores),
            "average_score": round(average_score, 2),
            "status_distribution": status_counts,
            "common_issues": [issue for issue, count in common_issues],
            "top_recommendations": [rec for rec, count in top_recommendations],
        }


# Global health analyzer instance for easy access
_health_analyzer_instance = None


def get_health_analyzer() -> HealthAnalyzer:
    """Get global health analyzer instance"""
    global _health_analyzer_instance
    if _health_analyzer_instance is None:
        _health_analyzer_instance = HealthAnalyzer()
    return _health_analyzer_instance


def calculate_workload_health(workload_data: Dict[str, Any]) -> HealthScore:
    """
    Calculate health score for Istio workloads (istiod, istio-ingressgateway).
    This is a convenience function that uses the global health analyzer instance.

    Args:
        workload_data: Parsed workload information from IstioParser

    Returns:
        Comprehensive health score with breakdown
    """
    analyzer = get_health_analyzer()
    return analyzer.calculate_workload_health(workload_data)


def analyze_component_health(component_data: Dict[str, Any]) -> HealthScore:
    """
    Analyze health of service mesh components (Gateway, VirtualService, DestinationRule).
    This is a convenience function that uses the global health analyzer instance.

    Args:
        component_data: Parsed component configuration from IstioParser

    Returns:
        Comprehensive health score with breakdown
    """
    analyzer = get_health_analyzer()
    return analyzer.analyze_component_health(component_data)


def detect_configuration_issues(resource_data: Dict[str, Any]) -> List[str]:
    """
    Detect common configuration issues in Istio resources.
    This is a convenience function that uses the global health analyzer instance.

    Args:
        resource_data: Parsed resource data from IstioParser

    Returns:
        List of detected configuration issues
    """
    analyzer = get_health_analyzer()
    return analyzer.detect_configuration_issues(resource_data)


def generate_health_recommendations(
    resource_data: Dict[str, Any], health_score: Optional[HealthScore] = None
) -> List[str]:
    """
    Generate improvement recommendations for Istio resources.
    This is a convenience function that uses the global health analyzer instance.

    Args:
        resource_data: Parsed resource data from IstioParser
        health_score: Optional existing health score for context

    Returns:
        List of improvement recommendations
    """
    analyzer = get_health_analyzer()
    return analyzer.generate_health_recommendations(resource_data, health_score)
