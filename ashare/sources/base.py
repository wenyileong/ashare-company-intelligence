from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SourceRecord:
    source: str
    url: str
    company_key: str | None
    content_type: str | None
    payload: bytes
    metadata: dict


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    def get_universe(self):
        raise NotImplementedError

    def close(self):
        pass
