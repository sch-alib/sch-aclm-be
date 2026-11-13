param(
    [Parameter(Mandatory = $true)]
    [string]$PfxPath,

    [Parameter(Mandatory = $true)]
    [string]$PfxPassword,

    [Parameter(Mandatory = $true)]
    [string]$SiteName,

    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [Parameter(Mandatory = $true)]
    [int]$Port,

    [Parameter(Mandatory = $false)]
    [string]$DryRun = "$true"
)

$ErrorActionPreference = "Stop"

if ($DryRun -eq "$true") {
    Write-Output "DRY RUN: would install $PfxPath on $SiteName for $HostName:$Port"
    exit 0
}

Import-Module WebAdministration

$SecurePassword = ConvertTo-SecureString `
    -String $PfxPassword `
    -AsPlainText `
    -Force

$Certificate = Import-PfxCertificate `
    -FilePath $PfxPath `
    -CertStoreLocation "Cert:\LocalMachine\My" `
    -Password $SecurePassword `
    -Exportable

if (-not $Certificate) {
    throw "Certificate import failed."
}

$ExistingBinding = Get-WebBinding `
    -Name $SiteName `
    -Protocol "https" `
    -Port $Port `
    -HostHeader $HostName `
    -ErrorAction SilentlyContinue

if (-not $ExistingBinding) {
    New-WebBinding `
        -Name $SiteName `
        -Protocol "https" `
        -Port $Port `
        -HostHeader $HostName | Out-Null
}

$BindingPath = "IIS:\SslBindings\0.0.0.0!$Port!$HostName"
if (Test-Path $BindingPath) {
    Remove-Item $BindingPath -Force
}

New-Item `
    $BindingPath `
    -Thumbprint $Certificate.Thumbprint `
    -SSLFlags 1 | Out-Null

Write-Output "IIS binding updated with thumbprint $($Certificate.Thumbprint)."
