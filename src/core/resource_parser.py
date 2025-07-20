# -*- coding: utf-8 -*-
"""
资源解析模块
提供K8s资源单位转换和LLM格式化功能
"""

import re
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import logging


class ResourceParser:
    """资源解析器，提供资源单位转换和LLM格式化功能"""

    def __init__(self):
        self.logger = logging.getLogger("cloudpilot.ResourceParser")

    def parse_resource_usage(
        self, resource_str: str, resource_type: str
    ) -> float:
        """
        解析K8s资源字符串为标准单位

        Args:
            resource_str: 资源字符串，如 "100m", "1Gi", "2.5"
            resource_type: 资源类型，"cpu" 或 "memory"

        Returns:
            float: 标准化后的资源值
                - CPU: 返回核心数 (cores)
                - Memory: 返回GB
        """
        if not resource_str:
            return 0.0

        try:
            resource_str = str(resource_str).strip()

            if resource_type.lower() == "cpu":
                return self._parse_cpu(resource_str)
            elif resource_type.lower() == "memory":
                return self._parse_memory(resource_str)
            else:
                # 尝试解析为数字
                return float(resource_str)

        except Exception as e:
            self.logger.warning(f"解析资源字符串失败: {resource_str}, 错误: {e}")
            return 0.0

    def _parse_cpu(self, cpu_str_input: str) -> float:
        """解析CPU资源字符串为核心数"""
        cpu_str = cpu_str_input.strip()

        # 处理毫核心 (millicores)
        if cpu_str.endswith("m"):
            return float(cpu_str[:-1]) / 1000
        # 处理微核心 (microcores)
        elif cpu_str.endswith("u"):
            return float(cpu_str[:-1]) / 1000000
        # 处理纳核心 (nanocores)
        elif cpu_str.endswith("n"):
            return float(cpu_str[:-1]) / 1000000000
        else:
            # 直接的核心数
            return float(cpu_str)

    def _parse_memory(self, memory_str_input: str) -> float:
        """解析内存资源字符串为GB"""
        memory_str = memory_str_input.strip().upper()

        # 二进制单位 (1024进制)
        if memory_str.endswith("KI"):
            return float(memory_str[:-2]) / (1024 * 1024)
        elif memory_str.endswith("MI"):
            return float(memory_str[:-2]) / 1024
        elif memory_str.endswith("GI"):
            return float(memory_str[:-2])
        elif memory_str.endswith("TI"):
            return float(memory_str[:-2]) * 1024
        elif memory_str.endswith("PI"):
            return float(memory_str[:-2]) * 1024 * 1024
        # 十进制单位 (1000进制)
        elif memory_str.endswith("K"):
            return float(memory_str[:-1]) / (1000 * 1000)
        elif memory_str.endswith("M"):
            return float(memory_str[:-1]) / 1000
        elif memory_str.endswith("G"):
            return float(memory_str[:-1])
        elif memory_str.endswith("T"):
            return float(memory_str[:-1]) * 1000
        elif memory_str.endswith("P"):
            return float(memory_str[:-1]) * 1000 * 1000
        else:
            # 字节数，转换为GB
            return float(memory_str) / (1024 * 1024 * 1024)

    def calculate_resource_percentages(
        self,
        used: Union[str, float],
        total: Union[str, float],
        resource_type: str = "cpu",
    ) -> float:
        """
        计算资源使用百分比

        Args:
            used: 已使用资源
            total: 总资源
            resource_type: 资源类型

        Returns:
            float: 使用百分比 (0-100)
        """
        try:
            if isinstance(used, str):
                used_val = self.parse_resource_usage(used, resource_type)
            else:
                used_val = float(used)

            if isinstance(total, str):
                total_val = self.parse_resource_usage(total, resource_type)
            else:
                total_val = float(total)

            if total_val == 0:
                return 0.0

            return (used_val / total_val) * 100

        except Exception as e:
            self.logger.warning(f"计算资源百分比失败: {e}")
            return 0.0

    def format_for_llm(self, resource_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化资源数据供LLM分析使用

        Args:
            resource_data: 原始资源数据

        Returns:
            Dict: LLM友好的格式化数据
        """
        formatted_data = {
            "summary": self._generate_summary(resource_data),
            "details": resource_data,
            "analysis_hints": self._generate_analysis_hints(resource_data),
            "error_indicators": self.extract_error_indicators(resource_data),
            "relationships": self._extract_relationships(resource_data),
        }

        return formatted_data

    def extract_error_indicators(self, resource_data: Dict[str, Any]) -> List[str]:
        """
        提取错误指示器和异常模式

        Args:
            resource_data: 资源数据

        Returns:
            List[str]: 错误指示器列表
        """
        indicators = []

        try:
            # 检查状态相关错误
            status = resource_data.get("status", "").lower()
            if status in [
                "failed",
                "error",
                "crashloopbackoff",
                "imagepullbackoff",
                "pending",
            ]:
                indicators.append(f"状态异常: {status}")

            # 检查重启次数
            restart_count = resource_data.get("restart_count", 0)
            if restart_count > 5:
                indicators.append(f"频繁重启: {restart_count}次")
            elif restart_count > 0:
                indicators.append(f"有重启记录: {restart_count}次")

            # 检查资源使用率
            cpu_usage = resource_data.get("cpu_usage_percent", 0)
            memory_usage = resource_data.get("memory_usage_percent", 0)

            if cpu_usage > 90:
                indicators.append(f"CPU使用率过高: {cpu_usage:.1f}%")
            if memory_usage > 90:
                indicators.append(f"内存使用率过高: {memory_usage:.1f}%")

            # 检查健康检查失败
            if resource_data.get("readiness_probe_failed"):
                indicators.append("就绪探针失败")
            if resource_data.get("liveness_probe_failed"):
                indicators.append("存活探针失败")

            # 检查节点状态
            if resource_data.get("node_status") == "NotReady":
                indicators.append("节点未就绪")

            # 检查副本数不匹配
            desired_replicas = resource_data.get("desired_replicas", 0)
            available_replicas = resource_data.get("available_replicas", 0)
            if desired_replicas > 0 and available_replicas < desired_replicas:
                indicators.append(
                    f"副本数不足: {available_replicas}/{desired_replicas}"
                )

        except Exception as e:
            self.logger.warning(f"提取错误指示器失败: {e}")

        return indicators

    def _generate_summary(self, resource_data: Dict[str, Any]) -> str:
        """生成资源摘要"""
        resource_type = resource_data.get("kind", "Resource")
        name = resource_data.get("name", "Unknown")
        namespace = resource_data.get("namespace", "")
        status = resource_data.get("status", "Unknown")

        summary = f"{resource_type} '{name}'"
        if namespace:
            summary += f" (namespace: {namespace})"
        summary += f" - 状态: {status}"

        return summary

    def _generate_analysis_hints(self, resource_data: Dict[str, Any]) -> List[str]:
        """生成分析提示"""
        hints = []

        # 基于资源类型提供分析提示
        resource_type = resource_data.get("kind", "").lower()

        if resource_type == "pod":
            hints.extend(
                ["检查容器状态和重启次数", "分析资源使用情况", "查看探针配置和状态"]
            )
        elif resource_type == "deployment":
            hints.extend(
                ["检查副本数和可用性", "分析滚动更新状态", "查看关联的ReplicaSet"]
            )
        elif resource_type == "service":
            hints.extend(
                ["检查端点和后端Pod", "验证端口配置", "分析服务类型和访问方式"]
            )
        elif resource_type == "node":
            hints.extend(
                ["检查节点条件和状态", "分析资源容量和分配", "查看系统信息和版本"]
            )

        return hints

    def _extract_relationships(
        self, resource_data: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """提取资源关系"""
        relationships = {"owns": [], "owned_by": [], "related_to": []}

        try:
            # 提取所有者引用
            owner_refs = resource_data.get("owner_references", [])
            for owner in owner_refs:
                relationships["owned_by"].append(
                    f"{owner.get('kind')}/{owner.get('name')}"
                )

            # 提取标签选择器关系
            labels = resource_data.get("labels", {})
            selectors = resource_data.get("selectors", {})

            if selectors:
                relationships["related_to"].append(f"选择器匹配的资源")

        except Exception as e:
            self.logger.warning(f"提取资源关系失败: {e}")

        return relationships

    def format_resource_units(self, value: float, unit_type: str = "cpu") -> str:
        """
        格式化资源单位为人类可读格式

        Args:
            value: 数值
            unit_type: 单位类型 ("cpu", "memory", "storage")

        Returns:
            str: 格式化后的字符串
        """
        if unit_type == "cpu":
            if value < 1:
                return f"{int(value * 1000)}m"
            else:
                return f"{value:.2f}"
        elif unit_type in ["memory", "storage"]:
            if value < 1:
                return f"{int(value * 1024)}Mi"
            elif value < 1024:
                return f"{value:.2f}Gi"
            else:
                return f"{value / 1024:.2f}Ti"
        else:
            return str(value)

    def validate_resource_limits(
        self, requests: Dict[str, str], limits: Dict[str, str]
    ) -> List[str]:
        """
        验证资源请求和限制的合理性

        Args:
            requests: 资源请求
            limits: 资源限制

        Returns:
            List[str]: 验证问题列表
        """
        issues = []

        try:
            for resource_type in ["cpu", "memory"]:
                if resource_type in requests and resource_type in limits:
                    request_val = self.parse_resource_usage(
                        requests[resource_type], resource_type
                    )
                    limit_val = self.parse_resource_usage(
                        limits[resource_type], resource_type
                    )

                    if request_val > limit_val:
                        issues.append(
                            f"{resource_type}请求({requests[resource_type]})大于限制({limits[resource_type]})"
                        )

                    # 检查是否过大或过小
                    if resource_type == "cpu":
                        if request_val > 8:
                            issues.append(f"CPU请求过大: {requests[resource_type]}")
                        if limit_val > 16:
                            issues.append(f"CPU限制过大: {limits[resource_type]}")
                    elif resource_type == "memory":
                        if request_val > 32:  # 32GB
                            issues.append(f"内存请求过大: {requests[resource_type]}")
                        if limit_val > 64:  # 64GB
                            issues.append(f"内存限制过大: {limits[resource_type]}")

        except Exception as e:
            self.logger.warning(f"验证资源限制失败: {e}")
            issues.append(f"资源限制验证失败: {e}")

        return issues
