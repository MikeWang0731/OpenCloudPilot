# CloudPilot API 参考文档

本文档提供了CloudPilot系统所有API端点的详细说明，包括请求参数、响应格式和使用示例。

## 基础信息

- **基础URL**: `http://localhost:8000` (默认)
- **响应格式**: JSON
- **认证方式**: 基于K8s集群配置

## 统一响应格式

所有API端点都采用统一的响应格式：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    // 具体数据内容
  }
}
```

## K8s资源管理API

### 集群管理

#### 添加集群配置 (Server模式)
- **端点**: `POST /k8s/cluster/add`
- **描述**: 添加新的K8s集群配置
- **请求体**:
```json
{
  "name": "production-cluster",
  "api_server": "https://k8s-api.example.com:6443",
  "token": "your-bearer-token",
  "description": "生产环境集群"
}
```

#### 获取集群列表 (Server模式)
- **端点**: `GET /k8s/cluster/list`
- **描述**: 获取所有已配置的集群列表

#### 获取集群信息
- **端点**: `GET /k8s/cluster/info`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
- **描述**: 获取指定集群的基本信息

### 资源概览

#### 获取集群概览
- **端点**: `GET /k8s/overview/cluster`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取集群资源概览信息

### 节点管理

#### 获取节点列表
- **端点**: `GET /k8s/resources/nodes/list`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取集群中所有节点的列表

#### 获取节点详情
- **端点**: `GET /k8s/resources/nodes/detail`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `node_name`: 节点名称
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取指定节点的详细信息

#### 获取节点容量信息
- **端点**: `GET /k8s/resources/nodes/capacity`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `node_name`: 节点名称
- **描述**: 获取节点的资源容量和使用情况

### Pod管理

#### 获取Pod列表
- **端点**: `GET /k8s/resources/pods/list`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间过滤
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取集群中的Pod列表

#### 获取Pod详情
- **端点**: `GET /k8s/resources/pods/detail`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: Pod所在命名空间
  - `pod_name`: Pod名称
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取指定Pod的详细信息

### 部署管理

#### 获取部署列表
- **端点**: `GET /k8s/resources/deployments/list`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间过滤
  - `force_refresh` (可选): 是否强制刷新缓存

#### 获取部署详情
- **端点**: `GET /k8s/resources/deployments/detail`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: 部署所在命名空间
  - `deployment_name`: 部署名称
  - `force_refresh` (可选): 是否强制刷新缓存

#### 部署扩缩容
- **端点**: `POST /k8s/resources/deployments/scaling`
- **请求体**:
```json
{
  "cluster_name": "production-cluster",
  "namespace": "default",
  "deployment_name": "my-app",
  "replicas": 3
}
```

### 服务管理

#### 获取服务列表
- **端点**: `GET /k8s/resources/services/list`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间过滤
  - `force_refresh` (可选): 是否强制刷新缓存

#### 获取服务详情
- **端点**: `GET /k8s/resources/services/detail`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: 服务所在命名空间
  - `service_name`: 服务名称
  - `force_refresh` (可选): 是否强制刷新缓存

### 日志管理

#### 获取Pod日志
- **端点**: `GET /k8s/resources/logs/pod`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: Pod所在命名空间
  - `pod_name`: Pod名称
  - `lines` (可选): 日志行数，默认100
  - `since_seconds` (可选): 获取最近N秒的日志

#### 获取容器日志
- **端点**: `GET /k8s/resources/logs/container`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: Pod所在命名空间
  - `pod_name`: Pod名称
  - `container_name`: 容器名称
  - `lines` (可选): 日志行数，默认100
  - `since_seconds` (可选): 获取最近N秒的日志

### 事件管理

#### 获取资源事件
- **端点**: `GET /k8s/resources/events/resource`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: 资源所在命名空间
  - `resource_name`: 资源名称
  - `resource_kind`: 资源类型 (Pod, Deployment等)

#### 获取命名空间事件
- **端点**: `GET /k8s/resources/events/namespace`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: 命名空间名称

#### 获取集群事件
- **端点**: `GET /k8s/resources/events/cluster`
- **参数**:
  - `cluster_name` (Server模式): 集群名称

## Istio服务网格API

### Istio工作负载管理

#### Istiod工作负载详情
- **端点**: `GET /istio/workloads/istiod/detail`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间，默认istio-system
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取Istiod工作负载的详细信息，包括部署状态、健康指标和资源使用情况

#### Istiod日志查询
- **端点**: `GET /istio/workloads/istiod/logs`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间，默认istio-system
  - `lines` (可选): 日志行数，默认100
  - `since_seconds` (可选): 获取最近N秒的日志
- **描述**: 获取Istiod容器的日志信息

#### Istiod事件查询
- **端点**: `GET /istio/workloads/istiod/events`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间，默认istio-system
- **描述**: 获取Istiod相关的K8s事件

#### Gateway工作负载详情
- **端点**: `GET /istio/workloads/gateway/detail`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间，默认istio-system
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取istio-ingressgateway工作负载的详细信息

#### Gateway工作负载日志
- **端点**: `GET /istio/workloads/gateway/logs`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间，默认istio-system
  - `lines` (可选): 日志行数，默认100
  - `since_seconds` (可选): 获取最近N秒的日志

#### Gateway工作负载事件
- **端点**: `GET /istio/workloads/gateway/events`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间，默认istio-system

### Istio组件管理

#### Gateway配置列表
- **端点**: `GET /api/istio/gateway/list`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间过滤
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取集群中所有Gateway配置的列表

#### Gateway配置详情
- **端点**: `GET /api/istio/gateway/detail`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: Gateway所在命名空间
  - `gateway_name`: Gateway名称
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取指定Gateway的详细配置信息，包括服务器配置、TLS设置和健康状态

#### VirtualService列表
- **端点**: `GET /api/istio/virtualservice/list`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间过滤
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取集群中所有VirtualService配置的列表

#### VirtualService详情
- **端点**: `GET /api/istio/virtualservice/detail`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: VirtualService所在命名空间
  - `virtualservice_name`: VirtualService名称
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取指定VirtualService的详细配置，包括路由规则、匹配条件和目标配置

#### DestinationRule列表
- **端点**: `GET /api/istio/destinationrule/list`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace` (可选): 命名空间过滤
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取集群中所有DestinationRule配置的列表

#### DestinationRule详情
- **端点**: `GET /api/istio/destinationrule/detail`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `namespace`: DestinationRule所在命名空间
  - `destinationrule_name`: DestinationRule名称
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取指定DestinationRule的详细配置，包括流量策略、负载均衡和熔断器设置

### Istio健康分析

#### 健康摘要
- **端点**: `GET /istio/health/summary`
- **参数**:
  - `cluster_name` (Server模式): 集群名称
  - `force_refresh` (可选): 是否强制刷新缓存
- **描述**: 获取Istio服务网格的整体健康状态摘要，包括工作负载健康、组件配置状态和性能指标

## 使用示例

### Server模式示例

```bash
# 添加集群配置
curl -X POST http://localhost:8000/k8s/cluster/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "prod-cluster",
    "api_server": "https://k8s-api.example.com:6443",
    "token": "your-token",
    "description": "生产环境集群"
  }'

# 获取集群概览
curl "http://localhost:8000/k8s/overview/cluster?cluster_name=prod-cluster"

# 获取Istiod工作负载详情
curl "http://localhost:8000/istio/workloads/istiod/detail?cluster_name=prod-cluster"

# 获取Gateway配置列表
curl "http://localhost:8000/api/istio/gateway/list?cluster_name=prod-cluster"
```

### Instant模式示例

```bash
# 获取集群概览（无需cluster_name参数）
curl "http://localhost:8000/k8s/overview/cluster"

# 获取Pod列表
curl "http://localhost:8000/k8s/resources/pods/list?namespace=default"

# 获取VirtualService详情
curl "http://localhost:8000/api/istio/virtualservice/detail?namespace=default&virtualservice_name=my-vs"

# 获取Istio健康摘要
curl "http://localhost:8000/istio/health/summary"
```

## 错误处理

所有API在发生错误时都会返回统一的错误格式：

```json
{
  "code": 400,
  "message": "请求参数错误",
  "data": {
    "error_type": "ValidationError",
    "details": "具体错误信息"
  }
}
```

常见错误码：
- `400`: 请求参数错误
- `404`: 资源不存在
- `500`: 服务器内部错误
- `503`: 服务不可用（如K8s集群连接失败）

## 性能优化

### 缓存机制
- 大部分查询API都支持缓存，默认TTL为30秒
- 使用`force_refresh=true`参数可以强制刷新缓存
- 缓存失效时会自动回退到直接API调用

### 并发处理
- 系统使用异步处理，支持高并发请求
- 多个资源查询会并行执行，提升响应速度
- 支持请求批处理，减少API调用次数

### 最佳实践
1. 在不需要实时数据时，避免使用`force_refresh`参数
2. 使用适当的命名空间过滤减少数据量
3. 对于频繁查询的数据，建议客户端实现本地缓存
4. 监控API响应时间，及时发现性能问题