"""
Istio Workloads Management

This module handles Istio workload resources including:
- istiod: Core Istio control plane component
- istio-ingressgateway: Istio ingress gateway workload
"""

# Import router creation functions
from .istiod_api import (
    create_server_istiod_router,
    create_instant_istiod_router,
)
from .gateway_workload_api import (
    create_server_gateway_workload_router,
    create_instant_gateway_workload_router,
)

__all__ = [
    "create_server_istiod_router",
    "create_instant_istiod_router",
    "create_server_gateway_workload_router",
    "create_instant_gateway_workload_router",
]
