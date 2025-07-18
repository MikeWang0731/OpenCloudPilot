# FastAPI 路由重构说明

## 重构概述

已成功将原本集中在 `server_mode.py` 和 `instant_app.py` 中的所有API接口，按照功能模块拆分到独立的路由文件中，实现了类似 Flask Blueprint 的功能。

## 新的目录结构

```
src/modes/
├── base_mode.py
├── server_mode.py          # 主要的Server模式类
├── instant_app.py          # 主要的Instant模式类
├── k8s/                    # Kubernetes相关API
│   ├── __init__.py
│   ├── cluster_api.py      # 集群管理相关接口
│   ├── overview_api.py     # 集群概览相关接口
│   └── resource_api.py     # 资源管理相关接口（Pod、Node、Namespace）
└── istio/                  # Istio服务网格相关API
    ├── __init__.py
    └── gateway_api.py      # Gateway相关接口
```

## API路由结构

### Server模式 API 路径

#### K8s 集群管理
- `POST /k8s/cluster/add` - 添加集群配置
- `GET /k8s/cluster/list` - 获取所有集群列表
- `POST /k8s/cluster/info` - 获取指定集群信息

#### K8s 概览信息
- `POST /k8s/overview/cluster` - 获取指定集群的资源概览

#### K8s 资源管理
- `POST /k8s/resource/pods` - 列出指定集群和命名空间的Pod
- `POST /k8s/resource/namespaces` - 获取指定集群的命名空间详细信息
- `POST /k8s/resource/nodes` - 获取指定集群的节点详细信息

#### Istio 服务网格
- `POST /istio/gateway/list` - 列出指定集群和命名空间的Gateway

### Instant模式 API 路径

#### K8s 集群信息
- `GET /k8s/cluster/info` - 获取集群基本信息

#### K8s 概览信息
- `POST /k8s/overview/cluster` - 获取集群资源概览

#### K8s 资源管理
- `POST /k8s/resource/pods` - 列出指定命名空间的Pod
- `POST /k8s/resource/namespaces` - 获取命名空间详细信息
- `POST /k8s/resource/nodes` - 获取节点详细信息

#### Istio 服务网格
- `POST /istio/gateway/list` - 列出Gateway

## 路由创建函数

每个API文件都提供了两个函数：
- `create_server_xxx_router(server_mode_instance)` - 为Server模式创建路由
- `create_instant_xxx_router(instant_mode_instance)` - 为Instant模式创建路由

## 使用示例

### 添加新的API模块

1. 在相应目录下创建新的API文件（如 `src/modes/k8s/deployment_api.py`）
2. 实现路由创建函数：

```python
def create_server_deployment_router(server_mode_instance) -> APIRouter:
    router = APIRouter(prefix="/k8s/deployment", tags=["K8s Deployment - Server"])
    
    @router.post("/list")
    async def list_deployments(request: DeploymentRequest):
        # 实现逻辑
        pass
    
    return router
```

3. 在主模式文件中导入并注册路由：

```python
from .k8s.deployment_api import create_server_deployment_router

# 在 _create_app 方法中
app.include_router(create_server_deployment_router(self))
```

### 添加新的服务模块

1. 创建新目录（如 `src/modes/prometheus/`）
2. 创建相应的API文件
3. 按照相同的模式实现路由函数
4. 在主模式文件中注册

## 优势

1. **模块化**: 每个功能模块独立，便于维护
2. **可扩展**: 轻松添加新的API模块
3. **清晰的结构**: 按功能和模式分离，代码组织清晰
4. **复用性**: 路由逻辑可以在不同模式间复用
5. **标签化**: 每个路由组都有明确的标签，便于API文档分类

## 注意事项

- 每个路由创建函数都接收对应的模式实例作为参数
- 模型类定义在各自的API文件中，避免重复
- 路由前缀和标签要保持一致的命名规范
- 异常处理保持统一的风格