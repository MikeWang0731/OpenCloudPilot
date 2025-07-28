# CloudPilot 使用示例

本文档提供了CloudPilot系统常见操作的详细使用示例，帮助用户快速上手。

## 环境准备

### 启动系统

#### Server模式启动
```bash
# 基础启动
python main.py --mode server

# 指定端口和配置
python main.py --mode server --host 0.0.0.0 --port 8000 --config config.yaml
```

#### Instant模式启动
```bash
# 在K8s集群内启动
python main.py --mode instant --port 8000

# 本地开发环境启动
python main.py --mode instant --host localhost --port 8001
```

## K8s集群管理示例

### 1. 集群配置管理 (Server模式)

#### 添加生产集群
```bash
curl -X POST http://localhost:8000/k8s/cluster/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production",
    "api_server": "https://prod-k8s.example.com:6443",
    "token": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",
    "description": "生产环境K8s集群"
  }'
```

#### 添加测试集群
```bash
curl -X POST http://localhost:8000/k8s/cluster/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "testing",
    "api_server": "https://test-k8s.example.com:6443",
    "token": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",
    "description": "测试环境K8s集群"
  }'
```

#### 查看所有集群
```bash
curl http://localhost:8000/k8s/cluster/list
```

### 2. 集群监控示例

#### 获取集群资源概览
```bash
# Server模式 - 生产集群概览
curl "http://localhost:8000/k8s/overview/cluster?cluster_name=production"

# Instant模式 - 当前集群概览
curl "http://localhost:8000/k8s/overview/cluster"
```

响应示例：
```json
{
  "code": 200,
  "message": "获取集群概览成功",
  "data": {
    "cluster_name": "production",
    "nodes": {
      "total": 5,
      "ready": 5,
      "not_ready": 0
    },
    "namespaces": 12,
    "deployments": 45,
    "services": 38,
    "pods": {
      "running": 120,
      "pending": 2,
      "failed": 1,
      "succeeded": 5
    },
    "resources": {
      "cpu_requests": "12.5",
      "cpu_limits": "25.0",
      "memory_requests": "24Gi",
      "memory_limits": "48Gi"
    },
    "last_updated": "2024-01-15T10:30:00Z"
  }
}
```

### 3. 节点管理示例

#### 获取节点列表
```bash
# Server模式
curl "http://localhost:8000/k8s/resources/nodes/list?cluster_name=production"

# Instant模式
curl "http://localhost:8000/k8s/resources/nodes/list"
```

#### 获取特定节点详情
```bash
# Server模式
curl "http://localhost:8000/k8s/resources/nodes/detail?cluster_name=production&node_name=worker-node-1"

# Instant模式
curl "http://localhost:8000/k8s/resources/nodes/detail?node_name=worker-node-1"
```

#### 获取节点容量信息
```bash
curl "http://localhost:8000/k8s/resources/nodes/capacity?cluster_name=production&node_name=worker-node-1"
```

### 4. Pod管理示例

#### 获取所有Pod
```bash
# Server模式 - 所有命名空间
curl "http://localhost:8000/k8s/resources/pods/list?cluster_name=production"

# 指定命名空间
curl "http://localhost:8000/k8s/resources/pods/list?cluster_name=production&namespace=default"

# Instant模式
curl "http://localhost:8000/k8s/resources/pods/list?namespace=kube-system"
```

#### 获取Pod详情
```bash
curl "http://localhost:8000/k8s/resources/pods/detail?cluster_name=production&namespace=default&pod_name=my-app-7d4b8c9f8-xyz12"
```

#### 获取Pod日志
```bash
# 获取最近100行日志
curl "http://localhost:8000/k8s/resources/logs/pod?cluster_name=production&namespace=default&pod_name=my-app-7d4b8c9f8-xyz12&lines=100"

# 获取最近5分钟的日志
curl "http://localhost:8000/k8s/resources/logs/pod?cluster_name=production&namespace=default&pod_name=my-app-7d4b8c9f8-xyz12&since_seconds=300"

# 获取特定容器日志
curl "http://localhost:8000/k8s/resources/logs/container?cluster_name=production&namespace=default&pod_name=my-app-7d4b8c9f8-xyz12&container_name=app-container"
```

### 5. 部署管理示例

#### 获取部署列表
```bash
curl "http://localhost:8000/k8s/resources/deployments/list?cluster_name=production&namespace=default"
```

#### 获取部署详情
```bash
curl "http://localhost:8000/k8s/resources/deployments/detail?cluster_name=production&namespace=default&deployment_name=my-app"
```

#### 部署扩缩容
```bash
# 扩容到5个副本
curl -X POST http://localhost:8000/k8s/resources/deployments/scaling \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "production",
    "namespace": "default",
    "deployment_name": "my-app",
    "replicas": 5
  }'

# 缩容到2个副本
curl -X POST http://localhost:8000/k8s/resources/deployments/scaling \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "production",
    "namespace": "default",
    "deployment_name": "my-app",
    "replicas": 2
  }'
```

## Istio服务网格管理示例

### 1. Istio工作负载监控

#### 监控Istiod状态
```bash
# Server模式
curl "http://localhost:8000/istio/workloads/istiod/detail?cluster_name=production"

# Instant模式
curl "http://localhost:8000/istio/workloads/istiod/detail"

# 强制刷新缓存
curl "http://localhost:8000/istio/workloads/istiod/detail?cluster_name=production&force_refresh=true"
```

响应示例：
```json
{
  "code": 200,
  "message": "获取Istiod工作负载详情成功",
  "data": {
    "name": "istiod",
    "namespace": "istio-system",
    "status": "Running",
    "replicas": {
      "desired": 1,
      "current": 1,
      "ready": 1,
      "available": 1
    },
    "containers": [
      {
        "name": "discovery",
        "image": "docker.io/istio/pilot:1.19.0",
        "status": "Running",
        "resources": {
          "requests": {"cpu": "500m", "memory": "2Gi"},
          "limits": {"cpu": "1", "memory": "4Gi"}
        }
      }
    ],
    "health_score": 95.5,
    "error_indicators": [],
    "last_updated": "2024-01-15T10:30:00Z"
  }
}
```

#### 获取Istiod日志
```bash
# 获取最近200行日志
curl "http://localhost:8000/istio/workloads/istiod/logs?cluster_name=production&lines=200"

# 获取最近10分钟的日志
curl "http://localhost:8000/istio/workloads/istiod/logs?cluster_name=production&since_seconds=600"
```

#### 监控Gateway工作负载
```bash
# 获取istio-ingressgateway状态
curl "http://localhost:8000/istio/workloads/gateway/detail?cluster_name=production"

# 获取Gateway工作负载日志
curl "http://localhost:8000/istio/workloads/gateway/logs?cluster_name=production&lines=100"

# 获取Gateway相关事件
curl "http://localhost:8000/istio/workloads/gateway/events?cluster_name=production"
```

### 2. Istio流量管理

#### Gateway配置管理
```bash
# 获取所有Gateway配置
curl "http://localhost:8000/api/istio/gateway/list?cluster_name=production"

# 获取特定命名空间的Gateway
curl "http://localhost:8000/api/istio/gateway/list?cluster_name=production&namespace=default"

# 获取Gateway详细配置
curl "http://localhost:8000/api/istio/gateway/detail?cluster_name=production&namespace=default&gateway_name=my-gateway"
```

Gateway详情响应示例：
```json
{
  "code": 200,
  "message": "获取Gateway详情成功",
  "data": {
    "name": "my-gateway",
    "namespace": "default",
    "servers": [
      {
        "port": {"number": 80, "name": "http", "protocol": "HTTP"},
        "hosts": ["example.com"]
      },
      {
        "port": {"number": 443, "name": "https", "protocol": "HTTPS"},
        "hosts": ["example.com"],
        "tls": {
          "mode": "SIMPLE",
          "credentialName": "example-tls"
        }
      }
    ],
    "selector": {"istio": "ingressgateway"},
    "validation_status": {
      "valid": true,
      "issues": []
    },
    "health_score": 98.0
  }
}
```

#### VirtualService路由管理
```bash
# 获取所有VirtualService
curl "http://localhost:8000/api/istio/virtualservice/list?cluster_name=production"

# 获取VirtualService详情
curl "http://localhost:8000/api/istio/virtualservice/detail?cluster_name=production&namespace=default&virtualservice_name=my-app-vs"
```

VirtualService详情响应示例：
```json
{
  "code": 200,
  "message": "获取VirtualService详情成功",
  "data": {
    "name": "my-app-vs",
    "namespace": "default",
    "hosts": ["my-app.example.com"],
    "gateways": ["my-gateway"],
    "http_routes": [
      {
        "match": [{"uri": {"prefix": "/api"}}],
        "route": [
          {
            "destination": {"host": "my-app-service", "port": {"number": 8080}},
            "weight": 100
          }
        ]
      }
    ],
    "validation_status": {
      "valid": true,
      "issues": []
    },
    "health_score": 96.5
  }
}
```

#### DestinationRule流量策略
```bash
# 获取所有DestinationRule
curl "http://localhost:8000/api/istio/destinationrule/list?cluster_name=production"

# 获取DestinationRule详情
curl "http://localhost:8000/api/istio/destinationrule/detail?cluster_name=production&namespace=default&destinationrule_name=my-app-dr"
```

### 3. Istio健康分析

#### 获取整体健康摘要
```bash
# Server模式
curl "http://localhost:8000/istio/health/summary?cluster_name=production"

# Instant模式
curl "http://localhost:8000/istio/health/summary"

# 强制刷新健康数据
curl "http://localhost:8000/istio/health/summary?cluster_name=production&force_refresh=true"
```

健康摘要响应示例：
```json
{
  "code": 200,
  "message": "获取Istio健康摘要成功",
  "data": {
    "overall_health_score": 94.2,
    "workloads": {
      "istiod": {
        "health_score": 95.5,
        "status": "Healthy",
        "issues": []
      },
      "istio_ingressgateway": {
        "health_score": 92.8,
        "status": "Healthy",
        "issues": ["High memory usage"]
      }
    },
    "components": {
      "gateways": {
        "total": 3,
        "healthy": 3,
        "issues": 0
      },
      "virtualservices": {
        "total": 12,
        "healthy": 11,
        "issues": 1
      },
      "destinationrules": {
        "total": 8,
        "healthy": 8,
        "issues": 0
      }
    },
    "recommendations": [
      "考虑增加istio-ingressgateway的内存限制",
      "检查VirtualService 'problematic-vs' 的路由配置"
    ],
    "last_updated": "2024-01-15T10:30:00Z"
  }
}
```

## 高级使用场景

### 1. 多集群监控脚本

创建一个监控脚本来检查多个集群的状态：

```bash
#!/bin/bash

# 多集群健康检查脚本
CLUSTERS=("production" "staging" "testing")
BASE_URL="http://localhost:8000"

echo "=== 多集群健康检查报告 ==="
echo "时间: $(date)"
echo

for cluster in "${CLUSTERS[@]}"; do
    echo "--- 集群: $cluster ---"
    
    # 获取集群概览
    overview=$(curl -s "$BASE_URL/k8s/overview/cluster?cluster_name=$cluster")
    echo "K8s概览: $overview" | jq '.data.nodes, .data.pods'
    
    # 获取Istio健康状态
    istio_health=$(curl -s "$BASE_URL/istio/health/summary?cluster_name=$cluster")
    echo "Istio健康分数: $istio_health" | jq '.data.overall_health_score'
    
    echo
done
```

### 2. 自动化部署扩缩容

根据负载情况自动调整部署副本数：

```python
import requests
import json

def auto_scale_deployment(cluster_name, namespace, deployment_name, target_cpu_percent=70):
    base_url = "http://localhost:8000"
    
    # 获取部署详情
    detail_url = f"{base_url}/k8s/resources/deployments/detail"
    params = {
        "cluster_name": cluster_name,
        "namespace": namespace,
        "deployment_name": deployment_name
    }
    
    response = requests.get(detail_url, params=params)
    if response.status_code != 200:
        print(f"获取部署详情失败: {response.text}")
        return
    
    deployment = response.json()["data"]
    current_replicas = deployment["replicas"]["current"]
    
    # 这里可以添加CPU使用率检查逻辑
    # 假设当前CPU使用率为85%，需要扩容
    current_cpu_percent = 85
    
    if current_cpu_percent > target_cpu_percent:
        new_replicas = min(current_replicas + 1, 10)  # 最多10个副本
        
        # 执行扩容
        scale_url = f"{base_url}/k8s/resources/deployments/scaling"
        scale_data = {
            "cluster_name": cluster_name,
            "namespace": namespace,
            "deployment_name": deployment_name,
            "replicas": new_replicas
        }
        
        scale_response = requests.post(scale_url, json=scale_data)
        if scale_response.status_code == 200:
            print(f"成功扩容 {deployment_name} 从 {current_replicas} 到 {new_replicas} 个副本")
        else:
            print(f"扩容失败: {scale_response.text}")

# 使用示例
auto_scale_deployment("production", "default", "my-app")
```

### 3. Istio配置健康检查

定期检查Istio配置的健康状态：

```python
import requests
import json
from datetime import datetime

def check_istio_health(cluster_name):
    base_url = "http://localhost:8000"
    
    # 获取健康摘要
    health_url = f"{base_url}/istio/health/summary"
    params = {"cluster_name": cluster_name, "force_refresh": "true"}
    
    response = requests.get(health_url, params=params)
    if response.status_code != 200:
        print(f"获取健康摘要失败: {response.text}")
        return
    
    health_data = response.json()["data"]
    overall_score = health_data["overall_health_score"]
    
    print(f"=== Istio健康检查报告 - {cluster_name} ===")
    print(f"时间: {datetime.now()}")
    print(f"整体健康分数: {overall_score}")
    
    # 检查工作负载健康
    print("\n工作负载状态:")
    for workload, info in health_data["workloads"].items():
        status = "✅" if info["status"] == "Healthy" else "❌"
        print(f"  {status} {workload}: {info['health_score']} ({info['status']})")
        if info["issues"]:
            for issue in info["issues"]:
                print(f"    ⚠️  {issue}")
    
    # 检查组件状态
    print("\n组件状态:")
    for component, info in health_data["components"].items():
        healthy_ratio = f"{info['healthy']}/{info['total']}"
        status = "✅" if info["issues"] == 0 else "⚠️"
        print(f"  {status} {component}: {healthy_ratio}")
    
    # 显示建议
    if health_data["recommendations"]:
        print("\n优化建议:")
        for rec in health_data["recommendations"]:
            print(f"  💡 {rec}")
    
    return overall_score

# 使用示例
clusters = ["production", "staging"]
for cluster in clusters:
    score = check_istio_health(cluster)
    if score < 90:
        print(f"⚠️  集群 {cluster} 健康分数较低，需要关注！")
    print("-" * 50)
```

## 故障排查示例

### 1. Pod故障排查流程

```bash
# 1. 获取Pod状态
curl "http://localhost:8000/k8s/resources/pods/detail?cluster_name=production&namespace=default&pod_name=problematic-pod"

# 2. 获取Pod日志
curl "http://localhost:8000/k8s/resources/logs/pod?cluster_name=production&namespace=default&pod_name=problematic-pod&lines=200"

# 3. 获取Pod相关事件
curl "http://localhost:8000/k8s/resources/events/resource?cluster_name=production&namespace=default&resource_name=problematic-pod&resource_kind=Pod"

# 4. 检查节点状态
curl "http://localhost:8000/k8s/resources/nodes/detail?cluster_name=production&node_name=worker-node-1"
```

### 2. Istio流量问题排查

```bash
# 1. 检查Gateway配置
curl "http://localhost:8000/api/istio/gateway/detail?cluster_name=production&namespace=default&gateway_name=my-gateway"

# 2. 检查VirtualService路由
curl "http://localhost:8000/api/istio/virtualservice/detail?cluster_name=production&namespace=default&virtualservice_name=my-app-vs"

# 3. 检查DestinationRule策略
curl "http://localhost:8000/api/istio/destinationrule/detail?cluster_name=production&namespace=default&destinationrule_name=my-app-dr"

# 4. 检查istio-proxy日志
curl "http://localhost:8000/istio/workloads/gateway/logs?cluster_name=production&lines=500"

# 5. 获取整体健康状态
curl "http://localhost:8000/istio/health/summary?cluster_name=production&force_refresh=true"
```

## 性能优化建议

### 1. 缓存使用策略
- 对于不经常变化的数据（如节点信息），可以依赖默认缓存
- 对于需要实时数据的场景（如Pod状态监控），使用`force_refresh=true`
- 在批量查询时，避免频繁使用`force_refresh`

### 2. 请求优化
```bash
# 好的做法：使用命名空间过滤
curl "http://localhost:8000/k8s/resources/pods/list?cluster_name=production&namespace=default"

# 避免：获取所有命名空间的Pod（数据量大）
curl "http://localhost:8000/k8s/resources/pods/list?cluster_name=production"
```

### 3. 监控频率建议
- 集群概览：每5分钟查询一次
- 节点状态：每10分钟查询一次
- Pod状态：每1-2分钟查询一次
- Istio健康状态：每5分钟查询一次
- 日志查询：按需查询，避免频繁调用

这些示例涵盖了CloudPilot系统的主要使用场景，可以根据实际需求进行调整和扩展。