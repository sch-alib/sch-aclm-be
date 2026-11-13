from app.adapters.ca.digicert import DigiCertAdapter
from app.adapters.installation.generic import GenericInstallationAdapter
from app.adapters.installation.iis import IisInstallationAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._ca_adapters = {
            "digicert": DigiCertAdapter(),
        }
        self._installation_adapters = {
            "iis": IisInstallationAdapter(),
            "generic": GenericInstallationAdapter(),
        }

    def get_ca_adapter(self, adapter_name: str):
        adapter = self._ca_adapters.get(adapter_name)
        if adapter is None:
            raise ValueError(f"Unknown CA adapter: {adapter_name}")
        return adapter

    def get_installation_adapter(self, adapter_name: str):
        adapter = self._installation_adapters.get(adapter_name)
        if adapter is None:
            raise ValueError(f"Unknown installation adapter: {adapter_name}")
        return adapter


adapter_registry = AdapterRegistry()
