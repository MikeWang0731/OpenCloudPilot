# AIOps CloudPilot

基于 Python + FastAPI 的 AIOps 系统后端，专注于 K8s 和 Istio 云原生环境的智能运维。

## 特性

- **灵活启动方式**：支持即时App模式和Server模式
- **多集群管理**：Server模式支持管理多个K8s集群
- **智能监控**：高效的集群监控系统，支持缓存和后台任务
- **资源分析**：详细的集群资源使用情况统计和分析
- **Istio支持**：完整的Istio Gateway管理功能
- **插拔式架构**：便于功能扩展和模块复用
- **模块化API设计**：K8s和Istio相关API按功能模块化组织，支持代码复用和维护
- **异步高性能**：基于FastAPI和异步编程，支持并发数据获取
- **智能缓存**：可配置的缓存机制，减少对K8s API Server的压力
- **类型安全**：使用Pydantic模型确保API请求响应的类型安全
- **智能配置**：支持环境变量、配置文件等多种配置方式
- **标准化日志**：使用Python标准日志格式，支持结构化日志记录
- **统一响应格式**：所有API接口采用一致的JSON响应格式，提供标准化的错误处理
- **完善测试**：提供完整的测试工具和分类异常处理测试

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动方式

#### 1. Server模式（推荐）

适合生产环境，支持多集群管理，使用SQLite数据库存储集群配置：

```bash
# 默认启动（默认为server模式）
python main.py

# 显式指定server模式
python main.py --mode server

# 指定端口和地址
python main.py --mode server --host 0.0.0.0 --port 8000

# 使用配置文件
python main.py --mode server --config config.yaml
```

#### 2. 即时App模式

适合在K8s集群内作为Pod运行，自动使用集群内权限：

```bash
# 启动即时App模式
python main.py --mode instant --port 8001
```

**注意**: 即时App模式会优先尝试使用集群内配置，如果失败则回退到本地kubeconfig（适合开发环境）。

### API接口

系统采用模块化API设计，将K8s相关功能按模块组织，支持Server模式（多集群管理）和Instant模式（单集群）。

#### Server模式接口

**基础接口**
- `GET /` - 服务信息
- `GET /health` - 健康检查
- `GET /docs` - Swagger UI 文档界面（自定义样式）

**集群管理模块 (`/k8s/cluster`)**
- `GET /k8s/cluster/list` - 获取集群列表
- `POST /k8s/cluster/add` - 添加集群配置
- `POST /k8s/cluster/info` - 获取指定集群信息

**集群概览模块 (`/k8s/overview`)**
- `POST /k8s/overview/cluster` - 获取指定集群资源概览

**资源管理模块 (`/k8s/resource`)**
- `POST /k8s/resource/pods` - 获取指定集群Pod列表（支持namespace参数）
- `POST /k8s/resource/namespaces` - 获取指定集群命名空间详情
- `POST /k8s/resource/nodes` - 获取指定集群节点详情

**Istio Gateway管理模块 (`/istio/gateway`)**
- `POST /istio/gateway/list` - 获取指定集群和命名空间的Istio Gateway列表

#### 即时App模式接口

**基础接口**
- `GET /` - 服务信息
- `GET /health` - 健康检查
- `GET /docs` - Swagger UI 文档界面

**集群管理模块 (`/k8s/cluster`)**
- `GET /k8s/cluster/info` - 获取当前集群信息

**集群概览模块 (`/k8s/overview`)**
- `POST /k8s/overview/cluster` - 获取当前集群资源概览

**资源管理模块 (`/k8s/resource`)**
- `POST /k8s/resource/pods` - 获取Pod列表（支持namespace参数）
- `POST /k8s/resource/namespaces` - 获取命名空间详细信息
- `POST /k8s/resource/nodes` - 获取节点详细信息

**Istio Gateway管理模块 (`/istio/gateway`)**
- `POST /istio/gateway/list` - 获取当前集群的Istio Gateway列表

#### 统一响应格式

所有API接口都采用统一的JSON响应格式，确保客户端处理的一致性：

**成功响应**：
```json
{
  "code": 200,
  "data": { /* 具体数据内容 */ },
  "message": "操作成功信息（可选）"
}
```

**错误响应**：
```json
{
  "code": 500,
  "message": "具体错误信息"
}
```

**Pod列表响应示例**：
```json
{
  "code": 200,
  "data": {
    "namespace": "default",
    "pod_count": 3,
    "pods": [
      {
        "name": "nginx-deployment-abc123",
        "status": "Running",
        "ready": 1,
        "restarts": 0
      }
    ]
  }
}
```

**集群概览响应示例**：
```json
{
  "code": 200,
  "data": {
    "cluster_name": "my-cluster",
    "nodes": {
      "total": 3,
      "ready": 3,
      "not_ready": 0
    },
    "workloads": {
      "pods": {
        "total": 25,
        "running": 23,
        "pending": 1,
        "failed": 1,
        "succeeded": 0
      },
      "deployments": 8
    },
    "discovery": {
      "services": 12
    },
    "configs": {
      "configmaps": 15,
      "secrets": 10,
      "namespaces": 5
    },
    "resources": {
      "cpu_requests": 2.5,
      "memory_requests": 4.2,
      "cpu_limits": 4.0,
      "memory_limits": 8.0
    },
    "metadata": {
      "last_updated": "2024-01-15T10:30:00"
    }
  }
}
```

#### API请求和响应模型

系统使用Pydantic模型确保API请求和响应的类型安全和文档完整性：

**请求模型**
- **ClusterConfig**: 集群配置模型（用于添加集群）
  - `name`: 集群名称
  - `api_server`: K8s API服务器地址
  - `token`: 访问令牌（可选）
  - `kubeconfig`: kubeconfig配置（可选）
  - `description`: 集群描述（可选）

- **ClusterRequest**: 集群操作请求模型
  - `cluster_name`: 集群名称
  - `force_refresh`: 是否强制刷新缓存（可选，默认false）

- **PodListRequest**: Pod列表请求模型
  - `cluster_name`: 集群名称
  - `namespace`: 命名空间（可选，默认"default"）

- **GatewayRequest**: Istio Gateway请求模型（Server模式）
  - `cluster_name`: 集群名称
  - `namespace`: 命名空间（可选，默认"istio-system"）

- **RefreshRequest**: 刷新请求模型（Instant模式）
  - `force_refresh`: 是否强制刷新缓存（可选，默认false）

**响应模型**
- **ServiceInfo**: 服务基本信息响应
- **HealthResponse**: 健康检查响应
- **ClusterInfo**: 集群信息响应（包含版本、节点数量和节点状态）
- **PodInfo**: Pod详细信息（名称、状态、就绪状态、重启次数）
- **PodListResponse**: Pod列表响应（命名空间、Pod数量和Pod列表）
- **GatewayListResponse**: Istio Gateway列表响应（集群名称、命名空间、Gateway数量和Gateway详情列表）
- **GatewayInfo**: Gateway详细信息（名称、命名空间、服务器配置、选择器）

### 添加集群配置（Server模式）

```bash
curl -X POST http://localhost:8000/k8s/cluster/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-cluster",
    "api_server": "https://k8s-api.example.com:6443",
    "token": "your-k8s-token",
    "description": "生产环境集群"
  }'
```

**响应格式**：
```json
{
  "code": 200,
  "message": "集群 my-cluster 添加成功"
}
```

**错误响应**：
```json
{
  "code": 500,
  "message": "添加集群失败: 具体错误信息"
}
```

### 获取集群信息

```bash
# Server模式 - 获取集群列表
curl http://localhost:8000/k8s/cluster/list

# Server模式 - 获取指定集群信息
curl -X POST http://localhost:8000/k8s/cluster/info \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "my-cluster"
  }'

# 即时App模式
curl http://localhost:8001/k8s/cluster/info
```

### 获取Istio Gateway信息

```bash
# Server模式 - 获取指定集群的Gateway列表
curl -X POST http://localhost:8000/istio/gateway/list \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "my-cluster",
    "namespace": "istio-system"
  }'

# 即时App模式 - 获取当前集群的Gateway列表
curl -X POST http://localhost:8001/istio/gateway/list \
  -H "Content-Type: application/json" \
  -d '{
    "force_refresh": false
  }'
```

## 配置说明

### 环境变量

```bash
# 基础配置
DEBUG=false
LOG_LEVEL=INFO

# 数据库配置
DATABASE_URL=sqlite:///./cloudpilot.db

# K8s配置
K8S_IN_CLUSTER=true
K8S_API_SERVER=https://k8s-api.example.com:6443
K8S_TOKEN=your-token

# LLM配置
LLM_PROVIDER=openai
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-3.5-turbo
```

### 配置文件

复制 `config.example.yaml` 为 `config.yaml` 并修改相应配置。

## 部署方式

### Docker部署（即时App模式）

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py", "--mode", "instant", "--host", "0.0.0.0", "--port", "8000"]
```

### K8s部署

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

## 集群监控功能

### 核心监控组件

系统提供了强大的集群监控功能，通过 `ClusterMonitor` 类实现高效的集群状态监控：

#### 监控数据类型

**资源概览 (ResourceOverview)**
- 节点数量和状态统计（就绪/未就绪）
- 命名空间、部署、服务、ConfigMap、Secret数量
- Pod状态分布（运行中/等待中/失败/成功）
- CPU/内存请求量和限制量统计
- 最后更新时间

**命名空间详情 (NamespaceDetail)**
- 命名空间名称和状态
- 各命名空间内的Pod、Deployment、Service数量
- 创建时间信息

**节点详情 (NodeDetail)**
- 节点名称、状态和角色
- Kubernetes版本、操作系统信息
- CPU/内存容量和可分配资源
- 容器运行时信息

#### 监控特性

- **智能缓存**：支持可配置的缓存TTL，减少API调用频率
- **并发获取**：使用异步并发方式获取多种资源信息，提升性能
- **后台监控**：支持启动后台监控任务，定期更新集群状态
- **容错处理**：单个资源获取失败不影响整体监控功能
- **资源解析**：智能解析K8s资源单位（m、Ki、Mi、Gi等）

#### 使用示例

```python
from src.core.cluster_monitor import ClusterMonitor
from kubernetes.dynamic import DynamicClient

# 创建监控器
monitor = ClusterMonitor(
    dynamic_client=dynamic_client,
    cache_ttl=30  # 缓存30秒
)

# 获取资源概览
overview = await monitor.get_resource_overview()
print(f"节点总数: {overview.nodes['total']}")
print(f"就绪节点: {overview.nodes['ready']}")
print(f"运行中Pod: {overview.workloads['pods']['running']}")
print(f"CPU请求总量: {overview.resources['cpu_requests']}核")
print(f"内存请求总量: {overview.resources['memory_requests']}GB")

# 获取命名空间详情
namespaces = await monitor.get_namespaces_detail()
for ns in namespaces:
    print(f"命名空间 {ns.name}: {ns.pods} pods, {ns.deployments} deployments")

# 获取节点详情
nodes = await monitor.get_nodes_detail()
for node in nodes:
    print(f"节点 {node.name}: {node.status} ({', '.join(node.roles)})")
```

## 项目结构

```
├── main.py                 # 主启动文件
├── requirements.txt        # 依赖列表
├── config.example.yaml     # 配置文件示例
├── cloudpilot.db          # SQLite数据库文件
├── src/
│   ├── core/              # 核心模块
│   │   ├── config.py      # 配置管理
│   │   ├── logger.py      # 日志配置
│   │   └── cluster_monitor.py  # 集群监控核心
│   └── modes/             # 启动模式
│       ├── base_mode.py   # 基础模式类
│       ├── instant_app.py # 即时App模式
│       ├── server_mode.py # Server模式
│       ├── k8s/           # K8s相关API模块
│       │   ├── __init__.py
│       │   ├── cluster_management_api.py  # 集群管理API
│       │   ├── cluster_overview_api.py    # 集群概览API
│       │   └── resource_api.py            # 资源管理API
│       └── istio/         # Istio相关API模块
│           ├── __init__.py
│           └── gateway_api.py    # Istio Gateway管理API
└── unit_test/             # 测试模块
    ├── test_modes.py      # 基础模式测试
    └── test_cluster_monitor.py # 集群监控功能测试（已优化代码质量）
```

## 开发计划

### 第一阶段 ✅
- [x] 灵活启动方式（即时App + Server模式）
- [x] 基础K8s集群连接
- [x] 多集群配置管理
- [x] 基础API接口

### 第二阶段 ✅
- [x] 集群监控系统
- [x] 资源概览和详细信息
- [x] 缓存机制和性能优化
- [x] 完整的测试工具

### 第三阶段（进行中）
- [x] 统一API响应格式
- [x] 改进错误处理机制
- [x] Istio Gateway管理API
- [x] 完善的API文档和示例
- [ ] AI Dashboard 后端
- [ ] 日志和事件收集
- [ ] AI Chat 后端集成

### 第四阶段（计划中）
- [ ] K8s Fast Dashboard
- [ ] Istio Fast Dashboard
- [ ] LLM智能分析
- [ ] 自然语言交互

## 开发指南

### 代码质量

项目遵循Python最佳实践：
- **类型安全**：使用类型提示和Pydantic模型确保API请求响应的类型安全
- **代码规范**：遵循PEP 8代码风格规范，包括100字符行长度限制
- **日志规范**：使用lazy % formatting进行日志记录，支持结构化日志
- **异常处理**：使用具体异常类型而非通用Exception，提供详细错误信息
- **模块化设计**：导入语句按标准库、第三方库、本地模块分组排序
- **测试完备**：测试代码具备完善的错误处理和分类异常捕获
- **性能优化**：代码复杂度控制在合理范围内，避免过长函数和过多分支
- **统一响应**：所有API接口采用统一的JSON响应格式，避免使用HTTPException抛出异常，确保客户端处理的一致性
- **异步优化**：充分利用异步编程和并发处理，提升系统性能

### 测试

项目提供了完整的测试工具来验证集群监控功能：

#### 集群监控测试

使用专门的测试脚本验证集群监控API：

```bash
# 测试即时模式
python unit_test/test_cluster_monitor.py instant

# 测试服务器模式
python unit_test/test_cluster_monitor.py server

# 测试两种模式
python unit_test/test_cluster_monitor.py both

# 指定服务地址
python unit_test/test_cluster_monitor.py instant http://localhost:8001
```

测试功能包括：
- 健康检查验证
- 集群概览数据获取
- 命名空间详情查询
- 节点状态检查
- 缓存性能测试
- 多集群管理测试（Server模式）
- 分类异常处理测试（网络异常、数据格式异常、未知异常）
- 完整的错误信息展示和调试支持

#### 模式测试

```bash
# 运行基础模式测试
python unit_test/test_modes.py
```

#### 测试特性

测试工具具备以下特性：
- **智能异常处理**：区分网络异常、数据格式异常和未知异常
- **详细错误报告**：提供具体的错误信息和状态码
- **性能测试**：包含缓存功能的性能对比测试
- **灵活配置**：支持自定义服务地址和测试模式
- **代码质量**：遵循Python最佳实践，包括行长度限制和异常处理规范

## 贡献

欢迎提交Issue和Pull Request！请确保代码符合项目的质量标准。

## 许可证

MIT License