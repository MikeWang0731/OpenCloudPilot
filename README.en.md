# AIOps CloudPilot

[简体中文](README.md) | English

🤖 AIOps system backend based on Python + FastAPI, focusing on intelligent operations for K8s and Istio cloud-native environments.

✏️ The project vision is to build an open, open-source, and free AIOps system that provides a revolutionary interactive experience by integrating Large Language Model (LLM) capabilities, making it easy and efficient for anyone to manage cloud computing resources and microservice architectures.

💻 Current stage: *Early-stage backend development*

🏃‍♀️ Next steps: Complete AI Dashboard backend and log event collection features

👏 Welcome to share excellent product suggestions and ideas!

## Features

- **Flexible Launch Modes**: Supports Instant App mode and Server mode
- **Multi-cluster Management**: Server mode supports managing multiple K8s clusters
- **Intelligent Monitoring**: Efficient cluster monitoring system with caching and background tasks
- **Resource Analysis**: Detailed cluster resource usage statistics and analysis
- **Resource Parsing**: Intelligent parsing of K8s resource units (m, Ki, Mi, Gi, etc.)
- **Istio Support**: Complete Istio service mesh management functionality, including workload monitoring and traffic management
- **Pluggable Architecture**: Easy to extend features and reuse modules
- **Modular API Design**: K8s and Istio related APIs organized by functional modules, supporting code reuse and maintenance
- **Asynchronous High Performance**: Based on FastAPI and asynchronous programming, supporting concurrent data retrieval
- **Intelligent Caching**: Configurable caching mechanism to reduce pressure on K8s API Server
- **Type Safety**: Using Pydantic models to ensure type safety of API requests and responses
- **Smart Configuration**: Supports multiple configuration methods including environment variables and configuration files
- **Standardized Logging**: Uses Python standard log format, supporting structured logging
- **Unified Response Format**: All API interfaces adopt a consistent JSON response format, providing standardized error handling
- **Comprehensive Testing**: Provides complete testing tools and categorized exception handling tests
- ➡️ **More features in planning**: Natural language interaction capabilities, intelligent suggestions, AgentOps, intelligent awareness, resource prediction, fault location, fault identification and prediction, and other machine learning and deep learning capabilities, as well as other K8s and Istio management capabilities.

## Quick Start

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Launch Methods

#### 1. Server Mode (Recommended)

Suitable for production environments, supports multi-cluster management, uses SQLite database to store cluster configurations:

```bash
# Default launch (server mode by default)
python main.py

# Explicitly specify server mode
python main.py --mode server

# Specify port and address
python main.py --mode server --host 0.0.0.0 --port 8000

# Use configuration file
python main.py --mode server --config config.yaml
```

#### 2. Instant App Mode

Suitable for running as a Pod within a K8s cluster, automatically using in-cluster permissions:

```bash
# Launch Instant App mode
python main.py --mode instant --port 8001
```

**Note**: Instant App mode will first try to use in-cluster configuration, falling back to local kubeconfig if it fails (suitable for development environments).

## Configuration

### Environment Variables

```bash
# Basic configuration
DEBUG=false
LOG_LEVEL=INFO

# Database configuration
DATABASE_URL=sqlite:///./cloudpilot.db

# K8s configuration
K8S_IN_CLUSTER=true
K8S_API_SERVER=https://k8s-api.example.com:6443
K8S_TOKEN=your-token

# LLM configuration
LLM_PROVIDER=openai
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-3.5-turbo
```

### Configuration File

Copy `config.example.yaml` to `config.yaml` and modify the corresponding configurations. The configuration file uses YAML format and is loaded and parsed by the `Settings` class.

## Deployment Methods

### Docker Deployment (Instant App Mode)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py", "--mode", "instant", "--host", "0.0.0.0", "--port", "8000"]
```

### K8s Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cloudpilot
spec:
  replicas: 1
  selector:
    matchLabels:
      app: cloudpilot
  template:
    metadata:
      labels:
        app: cloudpilot
    spec:
      serviceAccountName: cloudpilot
      containers:
      - name: cloudpilot
        image: cloudpilot:latest
        ports:
        - containerPort: 8000
        env:
        - name: K8S_IN_CLUSTER
          value: "true"
```

## Core Features

### Resource Parser (ResourceParser)

The system provides powerful resource parsing capabilities through the `ResourceParser` class:

- **Resource Unit Conversion**: Intelligent parsing of CPU (m, u, n) and memory (Ki, Mi, Gi, Ti, Pi) units
- **Resource Usage Calculation**: Calculate resource usage percentages, supporting conversion between different units
- **LLM-Friendly Formatting**: Format resource data into LLM-friendly structures for AI analysis
- **Error Indicator Extraction**: Automatically extract error indicators from resource data
- **Resource Relationship Analysis**: Analyze owner and related relationships between resources
- **Resource Limit Validation**: Validate the reasonableness of resource requests and limits

### Istio Service Mesh Management

The system provides complete Istio service mesh management functionality through unified API interfaces supporting Istio workload monitoring and traffic management:

#### Istio Workload Management

**Istiod Workload Monitoring**
- Istiod deployment status and health metrics monitoring
- Container resource usage and configuration analysis
- Istiod log queries and event tracking
- Health scoring and error indicator detection

**Istio Gateway Workload Monitoring**
- istio-ingressgateway deployment monitoring
- Gateway Pod status and traffic metrics
- Gateway workload logs and event queries
- Gateway health status assessment

#### Istio Traffic Management Components

**Gateway Configuration Management**
- Gateway resource configuration queries and analysis
- Server configuration, selector, and TLS settings validation
- Gateway configuration health checks and issue diagnosis
- Configuration change history and impact analysis

**VirtualService Route Management**
- VirtualService routing rule configuration queries
- HTTP/TCP/TLS routing rule analysis
- Route matching conditions and destination configuration validation
- Route health status and configuration issue detection

**DestinationRule Traffic Policies**
- DestinationRule traffic policy configuration management
- Load balancing, connection pool, and circuit breaker configuration
- Subset definitions and traffic distribution policies
- Traffic policy health assessment and optimization recommendations

#### Istio Health Analysis

- **Intelligent Health Scoring**: Health scoring algorithm based on Istio-specific metrics
- **Configuration Validation**: Automatic detection of common Istio configuration issues
- **Performance Optimization Recommendations**: Optimization suggestions based on resource usage
- **Fault Diagnosis**: Detailed error indicators and troubleshooting information

### Cluster Monitoring Features

The system provides powerful cluster monitoring capabilities through the `ClusterMonitor` class for efficient cluster state monitoring:

#### Monitoring Data Types

**Resource Overview (ResourceOverview)**
- Node count and status statistics (ready/not ready)
- Namespace, deployment, service, ConfigMap, Secret counts
- Pod status distribution (running/pending/failed/succeeded)
- CPU/memory request and limit statistics
- Last update time

**Node Details (NodeDetail)**
- Node name, status, and role
- Resource capacity and allocatable resources
- Resource usage and health score
- Node conditions and system information
- Error indicators and taint information

**Pod Details (PodDetail)**
- Pod name, status, and namespace
- Container information and health status
- Resource usage and configuration
- Pod conditions and event information

#### Monitoring Features

- **Intelligent Caching**: Supports configurable cache TTL to reduce API call frequency
- **Concurrent Retrieval**: Uses asynchronous concurrency to retrieve multiple resource information, improving performance
- **Background Monitoring**: Supports starting background monitoring tasks to periodically update cluster status
- **Fault Tolerance**: Single resource retrieval failure does not affect overall monitoring functionality
- **Resource Parsing**: Intelligently parses K8s resource units (m, Ki, Mi, Gi, etc.)

### API Design

The system adopts a modular API design, mainly including:

#### K8s Resource Management API
- **Node API**: Node management API, supporting retrieval of node lists, details, and capacity information
- **Pod API**: Pod management API, supporting retrieval of Pod lists and details
- **Deployment API**: Deployment management API, supporting deployment status monitoring and scaling operations
- **Service API**: Service management API, supporting service discovery and endpoint management
- **Other Resource APIs**: Supporting management of ConfigMap, Secret, and other resources

#### Istio Service Mesh API
- **Istio Workload API**: Istiod and Gateway workload monitoring
- **Istio Component API**: Gateway, VirtualService, DestinationRule management
- **Istio Health API**: Service mesh health status and performance analysis

All APIs adopt a unified response format, including status code, message, and data parts, ensuring client handling consistency.

## Project Structure

```
├── main.py                 # Main startup file
├── requirements.txt        # Dependency list
├── config.example.yaml     # Configuration file example
├── cloudpilot.db          # SQLite database file
├── src/
│   ├── core/              # Core modules
│   │   ├── __init__.py    # Package initialization
│   │   ├── async_utils.py # Async utilities
│   │   ├── cache_utils.py # Cache utilities
│   │   ├── config.py      # Configuration management
│   │   ├── error_handler.py # Error handling
│   │   ├── k8s_utils.py   # K8s utilities
│   │   ├── logger.py      # Log configuration
│   │   ├── pagination.py  # Pagination utilities
│   │   ├── resource_cache.py # Resource cache
│   │   ├── resource_parser.py # Resource parsing
│   │   └── cluster_monitor.py # Cluster monitoring core
│   └── modes/             # Launch modes
│       ├── __init__.py    # Package initialization
│       ├── base_mode.py   # Base mode class
│       ├── instant_app.py # Instant App mode
│       ├── server_mode.py # Server mode
│       ├── k8s/           # K8s related API modules
│       │   ├── __init__.py
│       │   ├── node_api.py # Node API
│       │   ├── pod_api.py  # Pod API
│       │   └── ...         # Other resource APIs
│       └── istio/         # Istio related API modules
│           ├── __init__.py
│           ├── router.py      # Istio unified route registration
│           ├── workloads/     # Istio workload management
│           │   ├── istiod_api.py # Istiod workload API
│           │   └── gateway_workload_api.py # Gateway workload API
│           ├── components/    # Istio component management
│           │   ├── gateway_api.py # Gateway configuration API
│           │   ├── virtualservice_api.py # VirtualService API
│           │   └── destinationrule_api.py # DestinationRule API
│           ├── utils/         # Istio utility modules
│           │   ├── istio_parser.py # Istio resource parsing
│           │   ├── health_analyzer.py # Health analysis
│           │   └── cache_manager.py # Cache management
│           └── health_summary_api.py # Health summary API
└── unit_test/             # Test modules
    ├── test_async_performance.py # Async performance tests
    ├── test_cluster_monitor.py   # Cluster monitoring tests
    ├── test_error_handling.py    # Error handling tests
    ├── test_pagination.py        # Pagination feature tests
    └── ...                       # Other tests
```

## Development Plan

### Phase 1 ✅
- [x] Flexible launch methods (Instant App + Server mode)
- [x] Basic K8s cluster connection
- [x] Multi-cluster configuration management
- [x] Basic API interfaces

### Phase 2 ✅
- [x] Cluster monitoring system
- [x] Resource overview and detailed information
- [x] Caching mechanism and performance optimization
- [x] Complete testing tools

### Phase 3 ✅
- [x] Unified API response format
- [x] Improved error handling mechanism
- [x] Complete API documentation and examples
- [x] Istio service mesh complete support
- [x] Log and event collection
- [x] System integration testing and documentation

### Phase 4 (Planned)
- [ ] AI Dashboard backend
- [ ] AI Chat backend integration
- [ ] K8s Fast Dashboard
- [ ] Istio Fast Dashboard
- [ ] LLM intelligent analysis
- [ ] Natural language interaction

## Development Guidelines

### Code Quality

The project follows Python best practices:
- **Type Safety**: Uses type hints and Pydantic models to ensure API request and response type safety
- **Code Standards**: Follows PEP 8 code style guidelines, including 100 character line length limit
- **Logging Standards**: Uses lazy % formatting for logging, supporting structured logging
- **Exception Handling**: Uses specific exception types rather than generic Exception, providing detailed error information
- **Modular Design**: Import statements grouped and sorted by standard library, third-party library, local module
- **Test Completeness**: Test code has comprehensive error handling and categorized exception catching
- **Performance Optimization**: Code complexity controlled within a reasonable range, avoiding overly long functions and too many branches
- **Unified Response**: All API interfaces adopt a unified JSON response format, avoiding throwing exceptions with HTTPException, ensuring client handling consistency
- **Asynchronous Optimization**: Fully utilizes asynchronous programming and concurrent processing to improve system performance