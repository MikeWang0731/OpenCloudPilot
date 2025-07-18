# AIOps OpenCloudPilot

🤖 AIOps system backend based on Python + FastAPI, focusing on intelligent operations for K8s and Istio cloud-native environments.

✏️ The project vision is to build an open, open-source, and free AIOps system that provides a revolutionary interactive experience by integrating Large Language Model (LLM) capabilities, making it easy and efficient for anyone to manage cloud computing resources and microservice architectures.

💻 Current stage: *Early backend development*

🏃‍♀️ Next steps: Release feature preview when basic functionality is ready

👏 Welcome to share excellent product suggestions and ideas!

## Features

- **Flexible Launch Modes**: Supports Instant App mode and Server mode
- **Multi-cluster Management**: Server mode supports managing multiple K8s clusters
- **Intelligent Monitoring**: Efficient cluster monitoring system with caching and background tasks
- **Resource Analysis**: Detailed cluster resource usage statistics and analysis
- **Istio Support**: Complete Istio Gateway management functionality
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

Copy `config.example.yaml` to `config.yaml` and modify the corresponding configurations.

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

## Cluster Monitoring Features

### Core Monitoring Components

The system provides powerful cluster monitoring capabilities through the `ClusterMonitor` class for efficient cluster state monitoring:

#### Monitoring Data Types

**Resource Overview (ResourceOverview)**
- Node count and status statistics (ready/not ready)
- Namespace, deployment, service, ConfigMap, Secret counts
- Pod status distribution (running/pending/failed/succeeded)
- CPU/memory request and limit statistics
- Last update time

**Namespace Details (NamespaceDetail)**
- Namespace name and status
- Pod, Deployment, Service counts in each namespace
- Creation time information

**Node Details (NodeDetail)**
- Node name, status, and role
- Kubernetes version, operating system information
- CPU/memory capacity and allocatable resources
- Container runtime information

#### Monitoring Features

- **Intelligent Caching**: Supports configurable cache TTL to reduce API call frequency
- **Concurrent Retrieval**: Uses asynchronous concurrency to retrieve multiple resource information, improving performance
- **Background Monitoring**: Supports starting background monitoring tasks to periodically update cluster status
- **Fault Tolerance**: Single resource retrieval failure does not affect overall monitoring functionality
- **Resource Parsing**: Intelligently parses K8s resource units (m, Ki, Mi, Gi, etc.)

## Project Structure

```
├── main.py                 # Main startup file
├── requirements.txt        # Dependency list
├── config.example.yaml     # Configuration file example
├── cloudpilot.db          # SQLite database file
├── src/
│   ├── core/              # Core modules
│   │   ├── config.py      # Configuration management
│   │   ├── logger.py      # Log configuration
│   │   └── cluster_monitor.py  # Cluster monitoring core
│   └── modes/             # Launch modes
│       ├── base_mode.py   # Base mode class
│       ├── instant_app.py # Instant App mode
│       ├── server_mode.py # Server mode
│       ├── k8s/           # K8s related API modules
│       │   ├── __init__.py
│       │   ├── cluster_management_api.py  # Cluster management API
│       │   ├── cluster_overview_api.py    # Cluster overview API
│       │   └── resource_api.py            # Resource management API
│       └── istio/         # Istio related API modules
│           ├── __init__.py
│           └── gateway_api.py    # Istio Gateway management API
└── unit_test/             # Test modules
    ├── test_modes.py      # Base mode tests
    └── test_cluster_monitor.py # Cluster monitoring feature tests
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

### Phase 3 (In Progress)
- [x] Unified API response format
- [x] Improved error handling mechanism
- [x] Complete API documentation and examples
- [ ] AI Dashboard backend
- [ ] Log and event collection
- [ ] AI Chat backend integration

### Phase 4 (Planned)
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

[简体中文](README.md) | English