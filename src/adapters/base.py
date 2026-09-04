
from abc import ABC, abstractmethod
from typing import Any


class AdapterError(RuntimeError):
    def __init__(
        self,
        source: str,
        dataset: str,
        category: str,
        status_code: int | None = None,
        message: str | None = None,
    ):
        self.source = source
        self.dataset = dataset
        self.category = category
        self.status_code = status_code
        detail = message or category
        status = f" status={status_code}" if status_code is not None else ""
        super().__init__(f"{source}.{dataset} {detail}{status}")


class AdapterTimeout(AdapterError):
    def __init__(self, source: str, dataset: str | None = None, message: str | None = None):
        if dataset is None:
            source, dataset = "adapter", source
        super().__init__(source, dataset, "timeout", message=message)


class AdapterPermissionError(AdapterError):
    def __init__(self, source: str, dataset: str | None = None, message: str | None = None):
        if dataset is None:
            source, dataset = "adapter", source
        super().__init__(source, dataset, "permission_denied", message=message)


class AdapterSchemaError(AdapterError):
    def __init__(self, source: str, dataset: str | None = None, message: str | None = None):
        if dataset is None:
            source, dataset = "adapter", source
        super().__init__(source, dataset, "schema_error", message=message)


class AdapterDataError(AdapterError):
    def __init__(self, source: str, dataset: str | None = None, message: str | None = None):
        if dataset is None:
            source, dataset = "adapter", source
        super().__init__(source, dataset, "data_error", message=message)


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
