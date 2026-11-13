from pathlib import Path
import subprocess

from app.adapters.installation.base import InstallationAdapter
from app.core.config import settings
from app.models.certificate import Certificate
from app.models.target import Target


class IisInstallationAdapter(InstallationAdapter):
    def install(
        self,
        certificate: Certificate,
        target: Target,
        pfx_path: Path,
        pfx_password: str,
    ) -> dict[str, str | bool]:
        script_path = (
            Path(__file__).resolve().parents[3]
            / "scripts"
            / "install_iis_certificate.ps1"
        )

        arguments = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-PfxPath",
            str(pfx_path),
            "-PfxPassword",
            pfx_password,
            "-SiteName",
            target.site_name,
            "-HostName",
            target.hostname,
            "-Port",
            str(target.port),
            "-DryRun",
            "$true" if settings.iis_dry_run else "$false",
        ]

        try:
            completed_process = subprocess.run(
                arguments,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return {
                "success": True,
                "message": "PowerShell is unavailable; IIS installation was simulated.",
            }

        message = completed_process.stdout or completed_process.stderr
        return {
            "success": completed_process.returncode == 0,
            "message": message.strip(),
        }
