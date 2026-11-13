from pathlib import Path

from app.adapters.installation.base import InstallationAdapter
from app.models.certificate import Certificate
from app.models.target import Target


class GenericInstallationAdapter(InstallationAdapter):
    def install(
        self,
        certificate: Certificate,
        target: Target,
        pfx_path: Path,
        pfx_password: str,
    ) -> dict[str, str | bool]:
        return {
            "success": True,
            "message": (
                f"Generic stub installed {certificate.common_name} "
                f"on {target.host} using {pfx_path.name}."
            ),
        }
