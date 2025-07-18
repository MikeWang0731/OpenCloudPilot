# AIOps - CloudPilot

该项目计划以 Python 作为主要语言开发一套 AIOps 系统的后端，使用 fastapi 作为后端框架保证并发时的性能表现。

该项目初期以 K8s 和 Istio 为核心，围绕云原生和微服务进行 AIOps 设计。

项目以 AI（ML/DL）+ LLM 为主要目标，计划借助人工智能的力量降低云原生的运维和运营成本，并以LLM 作为人机交互的核心卖点，设计出一套以自然语言为主，智能面板为辅的 AIOps 体系。

## 核心思考要点
由于 AI 需要频繁拉取集群信息，这里需要设计一种方法，即不能让后端频繁等待（充分利用计算资源，如多进程、异步等），也不能给 apiserver 造成太大压力，要保证集群基础服务的稳定运行。

## 代码要求
- 逻辑清晰、注释明了（主要使用中文）
- 架构合理，便于复用和迁移，以“插拔式”架构作为参考
- 充分考虑错误处理机制

## 第一阶段
一个灵活启动方式（可以分为两个文件，构建不同的镜像时采用不同的底层功能）

Case1：用户以即时 app 方式启动（Deployment 直接部署一个 Pod），此时 Pod 可以直接拿到 K8s 的cluster 权限，读取集群信息

Case2：用户以 Server 模式部署，此时需要一个轻量化数据库来存储用户保存的目标集群信息，可以支持直接输入apiserver 和密码以及 kubeconfig 自动解析。

我们需要使用 python-k8s 库的 dynamic_client 构建对集群的连接


两个主要模块

1. AI Dashboard 后端
- 集群信息概览（集群组件数量分布）
- 日志和事件
    - 重点收集Kubernetes Pod、部署、服务、节点以及istiod, istio-ingressgateway, istio-proxy(sidecar)。这些数据对于LLM进行语义分析和模式识别至关重要
- 待补充

TODO：事件信息和错误信息（例如 pod 启动失败这类）是否需要整合进概览？减少 API 请求次数，可以一次拿到的就都拿到？
TODO：Deployment 新增对应 Replicaset 的信息概览

2. AI Chat 后端
- 大模型交互
    - OpenAI 兼容（Langchain）
    - Ollama 兼容（Langchain）

3. K8s Fast Dashboard
- 待补充

4. Istio Fast Dashboard
- 待补充