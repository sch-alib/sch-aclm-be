from datetime import datetime, timedelta, timezone
import time
import uuid
from typing import Any

import httpx

from app.adapters.ca.base import CertificateAuthorityAdapter
from app.core.config import settings
from app.core.exceptions import DigiCertApiError


class DigiCertAdapter(CertificateAuthorityAdapter):
    transient_status_codes = {429, 500, 502, 503, 504}
    supported_order_products = {
        "ssl_plus", "ssl_multi_domain", "ssl_wildcard",
    }

    def __init__(self) -> None:
        self._mock_orders: dict[str, dict[str, Any]] = {}


    def list_certificates(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        if self._is_mock_mode():
            return self._mock_certificate_list()

        parameters: dict[str, Any] = {
            "filters[status]": "active_issued",
            "limit": filters.get("limit", 100),
            "offset": filters.get("offset", 0),
            "sort": "-date_created",
        }

        for filter_name in ("common_name", "domain_name", "valid_till"):
            filter_value = filters.get(filter_name)
            if filter_value:
                parameters[f"filters[{filter_name}]"] = filter_value

        response = self._request(
            method="GET",
            path="/order/certificate",
            parameters=parameters,
        )
        orders = response.json().get("orders", [])
        return [self._normalize_order(order) for order in orders]

    def get_order_details(self, order_id: str) -> dict[str, Any]:
        if self._is_mock_mode():
            if str(order_id) in self._mock_orders:
                record = self._mock_orders[str(order_id)]
                record["checks"] += 1
                if record["checks"] >= 2:
                    record["status"] = "issued"
                    record["certificate"]["id"] = record["certificate_id"]
                    record["certificate"]["valid_till"] = (
                        datetime.now(timezone.utc) + timedelta(days=record["validity_days"])
                    ).date().isoformat()
                return {key: value for key, value in record.items() if key != "checks"}
            matching_order = next(
                (
                    item
                    for item in self._mock_certificate_list()
                    if item["order_id"] == str(order_id)
                ),
                None,
            )
            if matching_order is None:
                raise DigiCertApiError("Mock DigiCert order was not found")

            return {
                **matching_order,
                "certificate": {
                    "id": matching_order["certificate_id"],
                    "common_name": matching_order["common_name"],
                    "dns_names": matching_order["dns_names"],
                    "valid_till": matching_order["valid_till"],
                    "csr": "MOCK_CSR",
                    "server_platform": {
                        "id": 2,
                        "name": "Microsoft IIS",
                    },
                },
                "requests": [
                    {
                        "id": "MOCK-REQUEST-1",
                        "type": "new",
                        "status": "completed",
                    }
                ],
            }

        response = self._request(
            method="GET",
            path=f"/order/certificate/{order_id}",
        )
        return response.json()

    def order_certificate(
        self, common_name: str, dns_names: list[str], csr_pem: str,
        product_name_id: str, organization_id: int, validity_days: int,
    ) -> dict[str, Any]:
        if product_name_id not in self.supported_order_products:
            raise DigiCertApiError("Unsupported order product for this form")
        if self._is_mock_mode():
            order_id = str(uuid.uuid4().int % 1000000000)
            certificate_id = str(uuid.uuid4().int % 1000000000)
            self._mock_orders[order_id] = {
                "id": order_id, "status": "pending", "checks": 0,
                "certificate_id": certificate_id, "validity_days": validity_days,
                "certificate": {
                    "id": None, "common_name": common_name,
                    "dns_names": dns_names, "valid_till": None,
                },
            }
            return {"id": order_id, "requests": [{"status": "pending"}]}

        payload = {
            "certificate": {
                "common_name": common_name,
                "dns_names": dns_names,
                "csr": csr_pem,
                "server_platform": {"id": settings.digicert_server_platform_id},
                "signature_hash": "sha256",
            },
            "order_validity": {"days": validity_days},
            "organization": {"id": organization_id},
            # Keep the CertCentral approval and validation process in place.
            "skip_approval": False,
        }
        # Do not retry a potentially chargeable order after an ambiguous response.
        result = self._request(
            method="POST", path=f"/order/certificate/{product_name_id}",
            json_body=payload, retry=False,
        ).json()
        if not result.get("id"):
            raise DigiCertApiError("DigiCert did not return an order ID; reconcile before retrying")
        return result

    def reissue_certificate(
        self,
        order_id: str,
        common_name: str,
        dns_names: list[str],
        csr_pem: str | None,
        reason: str,
    ) -> dict[str, Any]:
        if self._is_mock_mode():
            return {
                "request_id": f"MOCK-{uuid.uuid4().hex[:8]}",
                "order_id": str(order_id),
                "certificate_id": str(uuid.uuid4().int % 1000000),
                "status": "issued",
            }

        if not csr_pem:
            raise DigiCertApiError("A CSR is required for real-mode reissue")

        payload = {
            "certificate": {
                "common_name": common_name,
                "dns_names": dns_names,
                "csr": csr_pem,
                "server_platform": {
                    "id": settings.digicert_server_platform_id,
                },
                "signature_hash": "sha256",
            },
            "comments": reason,
        }

        response = self._request(
            method="POST",
            path=f"/order/certificate/{order_id}/reissue",
            json_body=payload,
        )
        result = response.json()

        for _ in range(settings.digicert_poll_attempts):
            order_details = self.get_order_details(order_id)
            certificate = order_details.get("certificate") or {}

            if order_details.get("status") == "issued" and certificate.get("id"):
                result["certificate_id"] = str(certificate["id"])
                result["status"] = "issued"
                result["order_details"] = order_details
                return result

            time.sleep(settings.digicert_poll_seconds)

        raise DigiCertApiError(
            "The reissue was submitted, but issuance did not complete within the polling window"
        )

    def revoke_certificate(
        self,
        certificate_id: str,
        reason: str,
    ) -> dict[str, Any]:
        if self._is_mock_mode():
            return {"status": "revoked"}

        payload = {
            "skip_approval": True,
            "comments": reason,
        }
        self._request(
            method="PUT",
            path=f"/certificate/{certificate_id}/revoke",
            json_body=payload,
        )
        return {"status": "revoked"}

    def download_certificate(self, certificate_id: str) -> bytes:
        if self._is_mock_mode():
            return f"MOCK CERTIFICATE {certificate_id}".encode("utf-8")

        response = self._request(
            method="GET",
            path=f"/certificate/{certificate_id}/download/platform",
        )
        return response.content

    def _request(
        self,
        method: str,
        path: str,
        parameters: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> httpx.Response:
        if not settings.digicert_api_key:
            raise DigiCertApiError("DIGICERT_API_KEY is required in real mode")

        headers = {
            "X-DC-DEVKEY": settings.digicert_api_key,
            "Accept": "application/json",
            "User-Agent": "certificate-automation/1.0",
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        url = f"{settings.digicert_api_base.rstrip('/')}{path}"

        max_attempts = settings.digicert_max_retries if retry else 1
        for attempt in range(1, max_attempts + 1):
            try:
                response = httpx.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=parameters,
                    json=json_body,
                    timeout=settings.digicert_timeout_seconds,
                )

                if response.status_code in self.transient_status_codes:
                    if attempt < max_attempts:
                        self._sleep_before_retry(response, attempt)
                        continue

                response.raise_for_status()
                return response
            except httpx.HTTPError as error:
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code not in self.transient_status_codes:
                    raise DigiCertApiError(self._format_http_error(error)) from error
                if attempt == max_attempts:
                    raise DigiCertApiError(
                        self._format_http_error(error)
                    ) from error

                time.sleep(settings.digicert_retry_backoff_seconds * attempt)

        raise DigiCertApiError("DigiCert request failed unexpectedly")

    def _sleep_before_retry(self, response: httpx.Response, attempt: int) -> None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = settings.digicert_retry_backoff_seconds * attempt
        else:
            delay = settings.digicert_retry_backoff_seconds * attempt

        time.sleep(delay)

    def _format_http_error(self, error: httpx.HTTPError) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            response = error.response
            try:
                details = response.json()
            except ValueError:
                details = response.text
            return f"DigiCert API returned {response.status_code}: {details}"

        return f"DigiCert transport error: {error}"

    def _normalize_order(self, order: dict[str, Any]) -> dict[str, Any]:
        certificate = order.get("certificate") or {}
        organization = order.get("organization") or {}

        return {
            "order_id": str(order.get("id")),
            "certificate_id": (
                str(certificate.get("id")) if certificate.get("id") else None
            ),
            "common_name": certificate.get("common_name") or "",
            "dns_names": certificate.get("dns_names") or [],
            "status": order.get("status") or "unknown",
            "valid_till": certificate.get("valid_till"),
            "days_remaining": certificate.get("days_remaining"),
            "product_name_id": order.get("product_name_id"),
            "organization_name": (
                organization.get("name")
                if isinstance(organization, dict)
                else None
            ),
        }

    def _is_mock_mode(self) -> bool:
        return settings.digicert_mode.lower() == "mock"

    def _mock_certificate_list(self) -> list[dict[str, Any]]:
        valid_till = (
            datetime.now(timezone.utc) + timedelta(days=20)
        ).date().isoformat()

        return [
            {
                "order_id": "9001",
                "certificate_id": "9101",
                "common_name": "managed.company.com",
                "dns_names": ["managed.company.com"],
                "status": "issued",
                "valid_till": valid_till,
                "days_remaining": 20,
                "product_name_id": "ssl_plus",
                "organization_name": "Example Corp",
            },
            {
                "order_id": "9002",
                "certificate_id": "9102",
                "common_name": "discovered.company.com",
                "dns_names": [
                    "discovered.company.com",
                    "www.discovered.company.com",
                ],
                "status": "issued",
                "valid_till": valid_till,
                "days_remaining": 20,
                "product_name_id": "ssl_plus",
                "organization_name": "Example Corp",
            },
        ]
