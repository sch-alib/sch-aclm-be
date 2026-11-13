class AdapterError(RuntimeError):
    """Base exception for external adapters."""


class DigiCertApiError(AdapterError):
    """Raised when DigiCert returns an error or cannot be reached."""


class GovernanceError(RuntimeError):
    """Raised when an operation violates a governance rule."""
