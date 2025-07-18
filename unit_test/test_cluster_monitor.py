#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集群监控功能测试脚本
用于验证新的集群监控API是否正常工作
"""

import asyncio
import sys
from datetime import datetime

import httpx


class ClusterMonitorTester:
    """集群监控测试器"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def test_instant_mode(self):
        """测试即时模式的集群监控功能"""
        print("=" * 60)
        print("测试即时模式集群监控功能")
        print("=" * 60)

        try:
            # 测试健康检查
            print("\n1. 测试健康检查...")
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ 健康检查通过: {data}")
            else:
                print(f"✗ 健康检查失败: {response.status_code}")
                return

            # 测试集群概览
            print("\n2. 测试集群概览...")
            response = await self.client.get(f"{self.base_url}/cluster/overview")
            if response.status_code == 200:
                data = response.json()
                print("✓ 集群概览获取成功:")
                self._print_overview(data)
            else:
                print(f"✗ 集群概览获取失败: {response.status_code} - {response.text}")

            # 测试命名空间详情
            print("\n3. 测试命名空间详情...")
            response = await self.client.get(f"{self.base_url}/cluster/namespaces")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ 命名空间详情获取成功: 共 {data['count']} 个命名空间")
                for ns in data["namespaces"][:3]:  # 只显示前3个
                    ns_info = (
                        f"  - {ns['name']}: {ns['pods']} pods, "
                        f"{ns['deployments']} deployments"
                    )
                    print(ns_info)
            else:
                error_msg = (
                    f"✗ 命名空间详情获取失败: {response.status_code} - "
                    f"{response.text}"
                )
                print(error_msg)

            # 测试节点详情
            print("\n4. 测试节点详情...")
            response = await self.client.get(f"{self.base_url}/cluster/nodes")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ 节点详情获取成功: 共 {data['count']} 个节点")
                for node in data["nodes"]:
                    node_info = (
                        f"  - {node['name']}: {node['status']} "
                        f"({', '.join(node['roles'])})"
                    )
                    print(node_info)
            else:
                error_msg = (
                    f"✗ 节点详情获取失败: {response.status_code} - " f"{response.text}"
                )
                print(error_msg)

            # 测试缓存功能
            print("\n5. 测试缓存功能...")
            start_time = datetime.now()
            response = await self.client.get(f"{self.base_url}/cluster/overview")
            first_duration = (datetime.now() - start_time).total_seconds()

            start_time = datetime.now()
            response = await self.client.get(f"{self.base_url}/cluster/overview")
            second_duration = (datetime.now() - start_time).total_seconds()

            print(f"  第一次请求耗时: {first_duration:.3f}秒")
            print(f"  第二次请求耗时: {second_duration:.3f}秒")
            if second_duration < first_duration * 0.5:
                print("✓ 缓存功能正常工作")
            else:
                print("? 缓存效果不明显，可能数据量较小")

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"✗ 测试过程中出现网络异常: {e}")
        except KeyError as e:
            print(f"✗ 响应数据格式异常: {e}")
        except Exception as e:
            print(f"✗ 测试过程中出现未知异常: {e}")

    async def test_server_mode(self, cluster_name: str = "test-cluster"):
        """测试服务器模式的集群监控功能"""
        print("=" * 60)
        print("测试服务器模式集群监控功能")
        print("=" * 60)

        try:
            # 测试健康检查
            print("\n1. 测试健康检查...")
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ 健康检查通过: {data}")
            else:
                print(f"✗ 健康检查失败: {response.status_code}")
                return

            # 测试集群列表
            print("\n2. 测试集群列表...")
            response = await self.client.get(f"{self.base_url}/list_clusters")
            if response.status_code == 200:
                data = response.json()
                clusters = data.get("clusters", [])
                print(f"✓ 集群列表获取成功: 共 {len(clusters)} 个集群")

                if not clusters:
                    print("  当前没有配置的集群，请先添加集群配置")
                    return

                # 使用第一个集群进行测试
                cluster_name = clusters[0]["name"]
                print(f"  使用集群 '{cluster_name}' 进行测试")
            else:
                print(f"✗ 集群列表获取失败: {response.status_code} - {response.text}")
                return

            # 测试集群概览
            print(f"\n3. 测试集群 '{cluster_name}' 概览...")
            response = await self.client.get(
                f"{self.base_url}/clusters/{cluster_name}/overview"
            )
            if response.status_code == 200:
                data = response.json()
                print("✓ 集群概览获取成功:")
                self._print_overview(data)
            else:
                print(f"✗ 集群概览获取失败: {response.status_code} - {response.text}")

            # 测试命名空间详情
            print(f"\n4. 测试集群 '{cluster_name}' 命名空间详情...")
            response = await self.client.get(
                f"{self.base_url}/clusters/{cluster_name}/namespaces"
            )
            if response.status_code == 200:
                data = response.json()
                print(f"✓ 命名空间详情获取成功: 共 {data['count']} 个命名空间")
                for ns in data["namespaces"][:3]:  # 只显示前3个
                    ns_info = (
                        f"  - {ns['name']}: {ns['pods']} pods, "
                        f"{ns['deployments']} deployments"
                    )
                    print(ns_info)
            else:
                error_msg = (
                    f"✗ 命名空间详情获取失败: {response.status_code} - "
                    f"{response.text}"
                )
                print(error_msg)

            # 测试节点详情
            print(f"\n5. 测试集群 '{cluster_name}' 节点详情...")
            response = await self.client.get(
                f"{self.base_url}/clusters/{cluster_name}/nodes"
            )
            if response.status_code == 200:
                data = response.json()
                print(f"✓ 节点详情获取成功: 共 {data['count']} 个节点")
                for node in data["nodes"]:
                    node_info = (
                        f"  - {node['name']}: {node['status']} "
                        f"({', '.join(node['roles'])})"
                    )
                    print(node_info)
            else:
                error_msg = (
                    f"✗ 节点详情获取失败: {response.status_code} - " f"{response.text}"
                )
                print(error_msg)

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"✗ 测试过程中出现网络异常: {e}")
        except KeyError as e:
            print(f"✗ 响应数据格式异常: {e}")
        except Exception as e:
            print(f"✗ 测试过程中出现未知异常: {e}")

    def _print_overview(self, data):
        """打印集群概览信息"""
        nodes_info = (
            f"  节点: {data.get('nodes', 0)} 个 "
            f"(就绪: {data.get('nodes_ready', 0)}, "
            f"未就绪: {data.get('nodes_not_ready', 0)})"
        )
        print(nodes_info)

        print(f"  命名空间: {data.get('namespaces', 0)} 个")

        pods_info = (
            f"  Pod: {data.get('pods', 0)} 个 "
            f"(运行: {data.get('pods_running', 0)}, "
            f"等待: {data.get('pods_pending', 0)}, "
            f"失败: {data.get('pods_failed', 0)})"
        )
        print(pods_info)

        print(f"  Deployment: {data.get('deployments', 0)} 个")
        print(f"  Service: {data.get('services', 0)} 个")
        print(f"  ConfigMap: {data.get('configmaps', 0)} 个")
        print(f"  Secret: {data.get('secrets', 0)} 个")

        cpu_requests = data.get("total_cpu_requests", 0)
        memory_requests = data.get("total_memory_requests", 0)
        if cpu_requests > 0 or memory_requests > 0:
            resource_info = (
                f"  资源请求: CPU {cpu_requests:.2f} 核, "
                f"内存 {memory_requests:.2f} GB"
            )
            print(resource_info)

        if data.get("last_updated"):
            print(f"  最后更新: {data['last_updated']}")

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()


async def main():
    """主测试函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python test_cluster_monitor.py instant    # 测试即时模式")
        print("  python test_cluster_monitor.py server     # 测试服务器模式")
        print("  python test_cluster_monitor.py both       # 测试两种模式")
        return

    mode = sys.argv[1].lower()
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"

    tester = ClusterMonitorTester(base_url)

    try:
        if mode in ["instant", "both"]:
            await tester.test_instant_mode()

        if mode in ["server", "both"]:
            if mode == "both":
                print("\n" + "=" * 60)
                print("切换到服务器模式测试...")
                print("=" * 60)
            await tester.test_server_mode()

        if mode not in ["instant", "server", "both"]:
            print(f"未知模式: {mode}")

    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
