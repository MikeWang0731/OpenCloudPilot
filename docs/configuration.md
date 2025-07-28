# CloudPilot 配置指南

本文档详细说明了CloudPilot系统的配置选项和部署注意事项。

## 配置方式

CloudPilot支持多种配置方式，按优先级从高到低：

1. 命令行参数
2. 环境变量
3. 配置文件
4. 默认值

## 基础配置

### 应用配置

```yaml
# config.yaml
app_name: "CloudPilot"
version: "1.0.0"
debug: false
log_level: "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

对应环境变量：
```bash
export APP_NAME="CloudPilot"
export VERSION="1.0.0"
export DEBUG=false
export LOG_LEVEL=INFO
```

### 服务器配置

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  workers: 1
```

环境变量：
```bash
export SERVER_HOST=0.0.0.0
export SERVER_PORT=8000
export SERVER_WORKERS=1
```

## K8s集群配置

### 集群内配置 (Instant模式)

当CloudPilot作为Pod运行在K8s集群内时：

```yaml
k8s:
  in_cluster: true
  config_path: null  # 使用集群内配置
```

环境变量：
```bash
export K8S_IN_CLUSTER=true
```

### 外部集群配置

当CloudPilot运行在集群外时：

```yaml
k8s:
  in_cluster: false
  config_path: "~/.kube/config"  # kubeconfig文件路径
```

环境变量：
```bash
export K8S_IN_CLUSTER=false
export K8S_CONFIG_PATH=~/.kube/config
```

### 直接API配置

直接使用K8s API Server：

```yaml
k8s:
  api_server: "https://k8s-api.example.com:6443"
  token: "your-bearer-token"
  verify_ssl: false  # 生产环境建议设为true
```

环境变量：
```bash
export K8S_API_SERVER=https://k8s-api.example.com:6443
export K8S_TOKEN=your-bearer-token
export K8S_VERIFY_SSL=false
```

## 数据库配置 (Server模式)

### SQLite配置 (默认)

```yaml
database:
  url: "sqlite:///./cloudpilot.db"
  echo: false  # 是否打印SQL语句
```

环境变量：
```bash
export DATABASE_URL=sqlite:///./cloudpilot.db
export DATABASE_ECHO=false
```

### PostgreSQL配置

```yaml
database:
  url: "postgresql://user:password@localhost:5432/cloudpilot"
  echo: false
  pool_size: 10
  max_overflow: 20
```

环境变量：
```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/cloudpilot
export DATABASE_POOL_SIZE=10
export DATABASE_MAX_OVERFLOW=20
```

## 缓存配置

### 内存缓存配置

```yaml
cache:
  type: "memory"  # memory, redis
  ttl: 30  # 默认TTL（秒）
  max_size: 1000  # 最大缓存条目数
```

环境变量：
```bash
export CACHE_TYPE=memory
export CACHE_TTL=30
export CACHE_MAX_SIZE=1000
```

### Redis缓存配置

```yaml
cache:
  type: "redis"
  redis_url: "redis://localhost:6379/0"
  ttl: 30
  key_prefix: "cloudpilot:"
```

环境变量：
```bash
export CACHE_TYPE=redis
export CACHE_REDIS_URL=redis://localhost:6379/0
export CACHE_TTL=30
export CACHE_KEY_PREFIX=cloudpilot:
```

## 监控配置

### 集群监控配置

```yaml
monitoring:
  enabled: true
  interval: 30  # 监控间隔（秒）
  background_tasks: true  # 是否启用后台任务
  cache_ttl: 30  # 监控数据缓存TTL
```

环境变量：
```bash
export MONITORING_ENABLED=true
export MONITORING_INTERVAL=30
export MONITORING_BACKGROUND_TASKS=true
export MONITORING_CACHE_TTL=30
```

### Istio监控配置

```yaml
istio:
  enabled: true
  default_namespace: "istio-system"
  health_check_interval: 60  # 健康检查间隔（秒）
  cache_ttl: 30
```

环境变量：
```bash
export ISTIO_ENABLED=true
export ISTIO_DEFAULT_NAMESPACE=istio-system
export ISTIO_HEALTH_CHECK_INTERVAL=60
export ISTIO_CACHE_TTL=30
```

## 日志配置

### 基础日志配置

```yaml
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file_path: null  # 不写入文件，仅控制台输出
```

### 文件日志配置

```yaml
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file_path: "/var/log/cloudpilot/app.log"
  max_bytes: 10485760  # 10MB
  backup_count: 5
```

### 结构化日志配置

```yaml
logging:
  level: "INFO"
  format: "json"  # json格式输出
  include_trace: true  # 包含调用栈信息
```

环境变量：
```bash
export LOG_LEVEL=INFO
export LOG_FORMAT=json
export LOG_FILE_PATH=/var/log/cloudpilot/app.log
export LOG_MAX_BYTES=10485760
export LOG_BACKUP_COUNT=5
```

## 安全配置

### API安全配置

```yaml
security:
  cors_enabled: true
  cors_origins: ["*"]  # 生产环境应限制具体域名
  api_key_required: false  # 是否需要API密钥
  api_key: "your-secret-api-key"
```

环境变量：
```bash
export SECURITY_CORS_ENABLED=true
export SECURITY_CORS_ORIGINS=*
export SECURITY_API_KEY_REQUIRED=false
export SECURITY_API_KEY=your-secret-api-key
```

### TLS配置

```yaml
tls:
  enabled: false
  cert_file: "/path/to/cert.pem"
  key_file: "/path/to/key.pem"
```

环境变量：
```bash
export TLS_ENABLED=false
export TLS_CERT_FILE=/path/to/cert.pem
export TLS_KEY_FILE=/path/to/key.pem
```

## 性能配置

### 异步配置

```yaml
async:
  max_workers: 10  # 最大并发工作线程
  timeout: 30  # 请求超时时间（秒）
  retry_attempts: 3  # 重试次数
  retry_delay: 1  # 重试延迟（秒）
```

环境变量：
```bash
export ASYNC_MAX_WORKERS=10
export ASYNC_TIMEOUT=30
export ASYNC_RETRY_ATTEMPTS=3
export ASYNC_RETRY_DELAY=1
```

### 资源限制配置

```yaml
limits:
  max_pods_per_request: 1000  # 单次请求最大Pod数量
  max_nodes_per_request: 100  # 单次请求最大节点数量
  max_log_lines: 10000  # 最大日志行数
  request_rate_limit: 100  # 每分钟最大请求数
```

环境变量：
```bash
export LIMITS_MAX_PODS_PER_REQUEST=1000
export LIMITS_MAX_NODES_PER_REQUEST=100
export LIMITS_MAX_LOG_LINES=10000
export LIMITS_REQUEST_RATE_LIMIT=100
```

## 部署配置

### Docker部署配置

#### Dockerfile示例

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建非root用户
RUN useradd -m -u 1000 cloudpilot && chown -R cloudpilot:cloudpilot /app
USER cloudpilot

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 启动应用
CMD ["python", "main.py", "--mode", "instant", "--host", "0.0.0.0", "--port", "8000"]
```

#### docker-compose.yml示例

```yaml
version: '3.8'

services:
  cloudpilot:
    build: .
    ports:
      - "8000:8000"
    environment:
      - LOG_LEVEL=INFO
      - K8S_IN_CLUSTER=false
      - K8S_CONFIG_PATH=/root/.kube/config
      - CACHE_TYPE=redis
      - CACHE_REDIS_URL=redis://redis:6379/0
    volumes:
      - ~/.kube/config:/root/.kube/config:ro
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
```

### K8s部署配置

#### Deployment示例

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cloudpilot
  namespace: cloudpilot-system
spec:
  replicas: 2
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
        - name: LOG_LEVEL
          value: "INFO"
        - name: CACHE_TYPE
          value: "redis"
        - name: CACHE_REDIS_URL
          value: "redis://redis-service:6379/0"
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

#### ServiceAccount和RBAC

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cloudpilot
  namespace: cloudpilot-system

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cloudpilot
rules:
- apiGroups: [""]
  resources: ["nodes", "pods", "services", "events", "namespaces"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets"]
  verbs: ["get", "list", "watch", "patch"]
- apiGroups: ["networking.istio.io"]
  resources: ["gateways", "virtualservices", "destinationrules"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cloudpilot
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cloudpilot
subjects:
- kind: ServiceAccount
  name: cloudpilot
  namespace: cloudpilot-system
```

#### Service和Ingress

```yaml
apiVersion: v1
kind: Service
metadata:
  name: cloudpilot-service
  namespace: cloudpilot-system
spec:
  selector:
    app: cloudpilot
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: cloudpilot-ingress
  namespace: cloudpilot-system
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: cloudpilot.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: cloudpilot-service
            port:
              number: 80
```

## 配置文件示例

### 完整配置文件示例

```yaml
# config.yaml - 生产环境配置示例
app_name: "CloudPilot"
version: "1.0.0"
debug: false
log_level: "INFO"

server:
  host: "0.0.0.0"
  port: 8000
  workers: 4

database:
  url: "postgresql://cloudpilot:password@postgres:5432/cloudpilot"
  echo: false
  pool_size: 20
  max_overflow: 30

cache:
  type: "redis"
  redis_url: "redis://redis:6379/0"
  ttl: 60
  key_prefix: "cloudpilot:prod:"

k8s:
  in_cluster: true
  verify_ssl: true

istio:
  enabled: true
  default_namespace: "istio-system"
  health_check_interval: 60
  cache_ttl: 60

monitoring:
  enabled: true
  interval: 30
  background_tasks: true
  cache_ttl: 60

logging:
  level: "INFO"
  format: "json"
  include_trace: false

security:
  cors_enabled: true
  cors_origins: ["https://dashboard.example.com"]
  api_key_required: true
  api_key: "${API_KEY}"  # 从环境变量读取

async:
  max_workers: 20
  timeout: 60
  retry_attempts: 3
  retry_delay: 2

limits:
  max_pods_per_request: 2000
  max_nodes_per_request: 200
  max_log_lines: 20000
  request_rate_limit: 200
```

### 开发环境配置示例

```yaml
# config.dev.yaml - 开发环境配置示例
app_name: "CloudPilot-Dev"
version: "1.0.0-dev"
debug: true
log_level: "DEBUG"

server:
  host: "localhost"
  port: 8001
  workers: 1

database:
  url: "sqlite:///./cloudpilot_dev.db"
  echo: true

cache:
  type: "memory"
  ttl: 10
  max_size: 100

k8s:
  in_cluster: false
  config_path: "~/.kube/config"
  verify_ssl: false

istio:
  enabled: true
  default_namespace: "istio-system"
  health_check_interval: 30
  cache_ttl: 10

monitoring:
  enabled: true
  interval: 10
  background_tasks: false
  cache_ttl: 10

logging:
  level: "DEBUG"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file_path: "./logs/cloudpilot_dev.log"

security:
  cors_enabled: true
  cors_origins: ["*"]
  api_key_required: false

async:
  max_workers: 5
  timeout: 30
  retry_attempts: 2
  retry_delay: 1

limits:
  max_pods_per_request: 100
  max_nodes_per_request: 10
  max_log_lines: 1000
  request_rate_limit: 50
```

## 配置验证

系统启动时会自动验证配置的有效性。如果配置有误，会输出详细的错误信息。

### 常见配置错误

1. **K8s连接配置错误**
   ```
   错误: 无法连接到K8s集群
   解决: 检查kubeconfig文件路径或集群内权限配置
   ```

2. **数据库连接错误**
   ```
   错误: 数据库连接失败
   解决: 检查数据库URL、用户名密码和网络连接
   ```

3. **Redis缓存连接错误**
   ```
   错误: Redis连接失败
   解决: 检查Redis URL和网络连接
   ```

4. **端口占用错误**
   ```
   错误: 端口8000已被占用
   解决: 更改端口配置或停止占用端口的进程
   ```

### 配置测试命令

```bash
# 测试配置文件语法
python -c "from src.core.config import Settings; Settings()"

# 测试K8s连接
python -c "
from src.core.config import Settings
from src.core.k8s_utils import test_k8s_connection
settings = Settings()
test_k8s_connection(settings)
"

# 测试数据库连接
python -c "
from src.core.config import Settings
settings = Settings()
print(f'数据库URL: {settings.database_url}')
"
```

这个配置指南涵盖了CloudPilot系统的所有主要配置选项，可以根据不同的部署环境和需求进行调整。