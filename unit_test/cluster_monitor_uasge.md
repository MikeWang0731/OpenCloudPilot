# 集群监控功能使用指南

## 概述

新的集群监控功能为 AIOps CloudPilot 提供了高效的 Kubernetes 集群资源监控能力。该功能支持：

- **资源概览**: 获取集群中各种资源的数量统计
- **缓存机制**: 减少对 apiserver 的压力，提高查询效率
- **异步处理**: 并发获取多种资源信息，提升性能
- **详细信息**: 提供节点、命名空间等详细信息

## 核心特性

### 1. 资源概览统计
- 节点数量和状态分布
- 命名空间数量
- Pod 数量和状态分布
- Deployment、Service、ConfigMap、Secret 数量
- 资源请求和限制统计

### 2. 缓存机制
- 默认缓存时间：30秒
- 支持强制刷新
- 减少 API 调用频率

### 3. 异步并发
- 并发获取多种资源信息
- 提高数据收集效率
- 错误隔离处理

## API 端点

### 即时模式 (Instant Mode)

#### 1. 集群概览
```http
GET /cluster/overview?force_refresh=false
```

**响应示例:**
```json
{
  "nodes": 3,
  "nodes_ready": 3,
  "nodes_not_ready": 0,
  "namespaces": 12,
  "pods": 45,
  "pods_running": 42,
  "pods_pending": 2,
  "pods_failed": 1,
  "pods_succeeded": 0,
  "deployments": 15,
  "services": 20,
  "configmaps": 25,
  "secrets": 18,
  "total_cpu_requests": 12.5,
  "total_memory_requests": 24.0,
  "total_cpu_limits": 20.0,
  "total_memory_limits": 40.0,
  "last_updated": "2025-01-16T10:30:00"
}
```

#### 2. 命名空间详情
```http
GET /cluster/namespaces?force_refresh=false
```

**响应示例:**
```json
{
  "count": 12,
  "namespaces": [
    {
      "name": "default",
      "status": "Active",
      "pods": 5,
      "deployments": 2,
      "services": 3,
      "created_at": "2025-01-01T00:00:00Z"
    },
    {
      "name": "kube-system",
      "status": "Active",
      "pods": 15,
      "deployments": 8,
      "services": 5,
      "created_at": "2025-01-01T00:00:00Z"
    }
  ]
}
```

#### 3. 节点详情
```http
GET /cluster/nodes?force_refresh=false
```

**响应示例:**
```json
{
  "count": 3,
  "nodes": [
    {
      "name": "master-node",
      "status": "Ready",
      "roles": ["control-plane", "master"],
      "version": "v1.28.0",
      "os_image": "Ubuntu 20.04.6 LTS",
      "kernel_version": "5.4.0-150-generic",
      "container_runtime": "containerd://1.6.20",
      "cpu_capacity": "4",
      "memory_capacity": "8Gi",
      "pods_capacity": "110",
      "cpu_allocatable": "4",
      "memory_allocatable": "7Gi",
      "pods_allocatable": "110",
      "created_at": "2025-01-01T00:00:00Z"
    }
  ]
}
```

### 服务器模式 (Server Mode)

#### 1. 集群概览
```http
GET /clusters/{cluster_name}/overview?force_refresh=false
```

#### 2. 命名空间详情
```http
GET /clusters/{cluster_name}/namespaces?force_refresh=false
```

#### 3. 节点详情
```http
GET /clusters/{cluster_name}/nodes?force_refresh=false
```

## 使用示例

### Python 客户端示例

```python
import asyncio
import httpx

async def get_cluster_overview():
    async with httpx.AsyncClient() as client:
        # 获取集群概览
        response = await client.get("http://localhost:8000/cluster/overview")
        if response.status_code == 200:
            data = response.json()
            print(f"集群节点数: {data['nodes']}")
            print(f"运行中的Pod: {data['pods_running']}")
            print(f"CPU请求总量: {data['total_cpu_requests']} 核")
        
        # 获取命名空间详情
        response = await client.get("http://localhost:8000/cluster/namespaces")
        if response.status_code == 200:
            data = response.json()
            print(f"命名空间数量: {data['count']}")
            for ns in data['namespaces']:
                print(f"  {ns['name']}: {ns['pods']} pods")

# 运行示例
asyncio.run(get_cluster_overview())
```

### curl 示例

```bash
# 获取集群概览
curl -X GET "http://localhost:8000/cluster/overview"

# 强制刷新缓存
curl -X GET "http://localhost:8000/cluster/overview?force_refresh=true"

# 获取命名空间详情
curl -X GET "http://localhost:8000/cluster/namespaces"

# 获取节点详情
curl -X GET "http://localhost:8000/cluster/nodes"
```

## 性能优化

### 1. 缓存策略
- 默认缓存时间：30秒
- 可通过 `force_refresh=true` 强制刷新
- 缓存失效时自动刷新

### 2. 并发处理
- 使用 `asyncio.gather()` 并发获取多种资源
- 错误隔离，单个资源获取失败不影响其他资源
- 异步处理，不阻塞其他请求

### 3. 资源解析优化
- CPU 和内存资源单位自动转换
- 支持多种 Kubernetes 资源单位格式
- 错误处理和默认值设置

## 监控建议

### 1. 定期监控
建议每30秒到1分钟获取一次集群概览，用于：
- 实时监控集群状态
- 资源使用趋势分析
- 异常情况告警

### 2. 按需详情查询
对于详细信息（节点、命名空间），建议：
- 按需查询，避免频繁调用
- 使用缓存机制减少 API 压力
- 在需要详细分析时才强制刷新

### 3. 错误处理
- 监控 API 响应状态
- 处理网络超时和连接错误
- 实现重试机制

## 故障排除

### 1. 连接问题
```bash
# 检查服务状态
curl -X GET "http://localhost:8000/health"

# 检查集群连接
curl -X GET "http://localhost:8000/cluster/info"
```

### 2. 权限问题
确保 Kubernetes 客户端具有以下权限：
- 读取节点信息
- 读取所有命名空间的 Pod、Deployment、Service 等资源
- 读取集群级别的资源

### 3. 性能问题
- 检查缓存是否正常工作
- 监控 API 响应时间
- 调整缓存时间设置

## 扩展开发

### 1. 添加新的资源类型
在 `ClusterMonitor` 类中添加新的资源获取方法：

```python
async def _get_ingresses_info(self) -> int:
    """获取Ingress数量"""
    try:
        networking_v1 = client.NetworkingV1Api(self.dynamic_client.client)
        ingresses = networking_v1.list_ingress_for_all_namespaces()
        return len(ingresses.items)
    except Exception as e:
        self.logger.error("获取Ingress信息失败: %s", e)
        return 0
```

### 2. 自定义缓存时间
```python
# 创建监控器时指定缓存时间
monitor = ClusterMonitor(dynamic_client, cache_ttl=60)  # 60秒缓存
```

### 3. 添加监控指标
扩展 `ResourceOverview` 数据结构，添加新的监控指标。

## 测试

使用提供的测试脚本验证功能：

```bash
# 测试即时模式
python test_cluster_monitor.py instant

# 测试服务器模式
python test_cluster_monitor.py server

# 测试两种模式
python test_cluster_monitor.py both
```