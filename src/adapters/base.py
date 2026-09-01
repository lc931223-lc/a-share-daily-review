
from abc import ABC, abstractmethod
from typing import Any

class BaseDataAdapter(ABC):
    """所有数据源适配器必须返回标准化 dict/list，不允许上层依赖某一家供应商字段。"""

    @abstractmethod
    def healthcheck(self) -> bool:
        ...

    @abstractmethod
    def source_name(self) -> str:
        ...

    def normalize(self, payload: Any) -> Any:
        return payload
