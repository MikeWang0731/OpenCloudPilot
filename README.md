# AIOps CloudPilot

简体中文 | [English](README.en.md)

🤖 基于 Python + FastAPI 的 AIOps 系统后端，专注于 K8s 和 Istio 云原生环境的智能运维。

✏️ 项目愿景是构建一个开放、开源且免费的AIOps系统，通过整合大型语言模型(LLM)能力，提供革命性的交互体验，让任何人都能轻松、高效地管理云计算资源和微服务架构。

💻 当前阶段：*后端研发前期*

🏃‍♀️ 下一步计划：完善AI Dashboard 后端和日志事件收集功能

👏 欢迎大家提出优秀的产品建议与想法！

## 特性

- **灵活启动方式**：支持即时App模式和Server模式
- **多集群管理**：Server模式支持管理多个K8s集群
- **智能监控**：高效的集群监控系统，支持缓存和后台任务
- **资源分析**：详细的集群资源使用情况统计和分析
- **资源解析**：智能解析K8s资源单位（m、Ki、Mi、Gi等）
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
- ➡️ **更多功能正在计划**: 自然语言交互能力、智能建议、AgentOps、智能感知、资源预测、故障定位、故障识别与预测等多种基于机器学习与深度学习的能力以及其他 K8s 和 istio 的管理能力。

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

复制 `config.example.yaml` 为 `config.yaml` 并修改相应配置。配置文件使用YAML格式，通过 `Settings` 类进行加载和解析。

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

## 核心功能

### 资源解析器 (ResourceParser)

系统提供了强大的资源解析功能，通过 `ResourceParser` 类实现对K8s资源的智能解析：

- **资源单位转换**：支持CPU (m, u, n) 和内存 (Ki, Mi, Gi, Ti, Pi) 单位的智能解析
- **资源使用率计算**：计算资源使用百分比，支持不同单位间的转换
- **LLM友好格式化**：将资源数据格式化为LLM友好的结构，便于AI分析
- **错误指标提取**：自动提取资源数据中的错误指标
- **资源关系分析**：分析资源间的所有者和关联关系
- **资源限制验证**：验证资源请求和限制的合理性

### 集群监控功能

系统提供了强大的集群监控功能，通过 `ClusterMonitor` 类实现高效的集群状态监控：

#### 监控数据类型

**资源概览 (ResourceOverview)**
- 节点数量和状态统计（就绪/未就绪）
- 命名空间、部署、服务、ConfigMap、Secret数量
- Pod状态分布（运行中/等待中/失败/成功）
- CPU/内存请求量和限制量统计
- 最后更新时间

**节点详情 (NodeDetail)**
- 节点名称、状态和角色
- 资源容量和可分配资源
- 资源使用情况和健康分数
- 节点条件和系统信息
- 错误指标和污点信息

**Pod详情 (PodDetail)**
- Pod名称、状态和命名空间
- 容器信息和健康状态
- 资源使用情况和配置
- Pod条件和事件信息

#### 监控特性

- **智能缓存**：支持可配置的缓存TTL，减少API调用频率
- **并发获取**：使用异步并发方式获取多种资源信息，提升性能
- **后台监控**：支持启动后台监控任务，定期更新集群状态
- **容错处理**：单个资源获取失败不影响整体监控功能
- **资源解析**：智能解析K8s资源单位（m、Ki、Mi、Gi等）

### API设计

系统采用模块化API设计，主要包括：

- **Node API**：节点管理API，支持获取节点列表、详情和容量信息
- **Pod API**：Pod管理API，支持获取Pod列表和详情信息
- **其他资源API**：支持Deployment、Service等资源的管理

所有API均采用统一的响应格式，包含状态码、消息和数据三部分，确保客户端处理的一致性。

## 项目结构

```
├── main.py                 # 主启动文件
├── requirements.txt        # 依赖列表
├── config.example.yaml     # 配置文件示例
├── cloudpilot.db          # SQLite数据库文件
├── src/
│   ├── core/              # 核心模块
│   │   ├── __init__.py    # 包初始化
│   │   ├── async_utils.py # 异步工具
│   │   ├── cache_utils.py # 缓存工具
│   │   ├── config.py      # 配置管理
│   │   ├── error_handler.py # 错误处理
│   │   ├── k8s_utils.py   # K8s工具
│   │   ├── logger.py      # 日志配置
│   │   ├── pagination.py  # 分页工具
│   │   ├── resource_cache.py # 资源缓存
│   │   ├── resource_parser.py # 资源解析
│   │   └── cluster_monitor.py # 集群监控核心
│   └── modes/             # 启动模式
│       ├── __init__.py    # 包初始化
│       ├── base_mode.py   # 基础模式类
│       ├── instant_app.py # 即时App模式
│       ├── server_mode.py # Server模式
│       ├── k8s/           # K8s相关API模块
│       │   ├── __init__.py
│       │   ├── node_api.py # 节点API
│       │   ├── pod_api.py  # Pod API
│       │   └── ...         # 其他资源API
│       └── istio/         # Istio相关API模块
│           ├── __init__.py
│           └── gateway_api.py # Istio Gateway管理API
└── unit_test/             # 测试模块
    ├── test_async_performance.py # 异步性能测试
    ├── test_cluster_monitor.py   # 集群监控测试
    ├── test_error_handling.py    # 错误处理测试
    ├── test_pagination.py        # 分页功能测试
    └── ...                       # 其他测试
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
- [x] 完善的API文档和示例
- [ ] AI Dashboard 后端
- [x] 日志和事件收集
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