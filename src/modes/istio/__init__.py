"""
Istio Resource Management Module

This module provides comprehensive management capabilities for Istio service mesh resources,
including workloads (istiod, istio-ingressgateway) and service mesh components 
(Gateway, VirtualService, DestinationRule).
"""

__version__ = "1.0.0"
__author__ = "CloudPilot Team"

# Import main components for easy access
from .utils.istio_parser import IstioParser
from .utils.health_analyzer import HealthAnalyzer

__all__ = [
    "IstioParser",
    "HealthAnalyzer",
]
