from abc import ABC, abstractmethod
from typing import Any


class CertificateAuthorityAdapter(ABC):
    @abstractmethod
    def list_certificates(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_order_details(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def order_certificate(
        self, common_name: str, dns_names: list[str], csr_pem: str,
        product_name_id: str, organization_id: int, validity_days: int,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def reissue_certificate(
        self,
        order_id: str,
        common_name: str,
        dns_names: list[str],
        csr_pem: str | None,
        reason: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def revoke_certificate(
        self,
        certificate_id: str,
        reason: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def download_certificate(self, certificate_id: str) -> bytes:
        raise NotImplementedError
