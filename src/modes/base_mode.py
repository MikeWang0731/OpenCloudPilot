# -*- coding: utf-8 -*-
"""
基础模式类
定义通用的启动模式接口
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

from src.core.config import Settings


class BaseMode(ABC):
    """基础模式抽象类"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = logging.getLogger(f"cloudpilot.{self.__class__.__name__}")

    @abstractmethod
    async def start(self, host: str = "0.0.0.0", port: int = 8000):
        """启动服务"""
        pass

    @abstractmethod
    async def stop(self):
        """停止服务"""
        pass
