from abc import ABC, abstractmethod
from pathlib import Path

from app.models.certificate import Certificate
from app.models.target import Target


class InstallationAdapter(ABC):
    @abstractmethod
    def install(
        self,
        certificate: Certificate,
        target: Target,
        pfx_path: Path,
        pfx_password: str,
    ) -> dict[str, str | bool]:
        raise NotImplementedError
