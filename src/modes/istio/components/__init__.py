"""
Istio Service Mesh Components Management

This module handles Istio service mesh component resources including:
- Gateway: Traffic ingress configuration
- VirtualService: Traffic routing rules
- DestinationRule: Traffic policies and load balancing
"""

# Import router creation functions
from .gateway_api import (
    create_gateway_router_for_server,
    create_gateway_router_for_instant,
)
from .virtualservice_api import (
    create_virtualservice_router_for_server,
    create_virtualservice_router_for_instant,
)
from .destinationrule_api import (
    create_destinationrule_router_for_server,
    create_destinationrule_router_for_instant,
)

__all__ = [
    "create_gateway_router_for_server",
    "create_gateway_router_for_instant",
    "create_virtualservice_router_for_server",
    "create_virtualservice_router_for_instant",
    "create_destinationrule_router_for_server",
    "create_destinationrule_router_for_instant",
]
