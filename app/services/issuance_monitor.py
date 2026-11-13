"""Automatic, read-only CertCentral issuance polling with persisted retries.

UTC is stored as naive datetime for SQLite compatibility and marked UTC in the API.
Claims are atomic across workers sharing the same SQLite database. No orders are
submitted by this monitor.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from uuid import uuid4

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import DigiCertApiError, GovernanceError
from app.database.session import SessionFactory
from app.models.certificate import Certificate
from app.models.issuance_check import IssuanceCheck
from app.models.job import Job
from app.services.new_order_service import new_order_service

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def public_error(error: Exception) -> str:
    """Do not persist or expose arbitrary CA response bodies, URLs, or credentials."""
    if isinstance(error, DigiCertApiError):
        match = re.search(r"DigiCert API returned (\d{3})", str(error))
        if match:
            return f"DigiCert API returned HTTP {match.group(1)}; check order access and DigiCert status."
        if "DIGICERT_API_KEY is required" in str(error):
            return "DigiCert API key is not configured."
        return "Could not reach DigiCert or interpret its response; check connectivity and server logs."
    return "Issuance check failed unexpectedly; check server logs."


class IssuanceMonitor:
    def schedule_existing(self, session: Session) -> None:
        """Backfill pending records created before this table was added."""
        ids = session.query(Certificate.id).filter(
            Certificate.management_state == "Pending issuance",
            Certificate.external_order_id.isnot(None),
        ).all()
        for (certificate_id,) in ids:
            if session.get(IssuanceCheck, certificate_id) is None:
                session.add(IssuanceCheck(
                    certificate_id=certificate_id,
                    status="Pending",
                    next_check_at=utcnow(),
                ))
                try:
                    session.commit()
                except IntegrityError:  # Another process already scheduled it.
                    session.rollback()

    def check_one(
        self, session: Session, certificate_id: int, actor: str,
        *, force: bool = False, now: datetime | None = None,
    ) -> Certificate:
        now = now or utcnow()
        certificate = session.get(Certificate, certificate_id)
        if not certificate or certificate.management_state != "Pending issuance" or not certificate.external_order_id:
            raise GovernanceError("Only pending new orders can be checked")
        check = session.get(IssuanceCheck, certificate_id)
        if check is None:
            # Compatible with pending records written before polling was introduced.
            self.schedule_existing(session)
            check = session.get(IssuanceCheck, certificate_id)
        if check is None:
            raise GovernanceError("Issuance check could not be scheduled")

        token = str(uuid4())
        lease_seconds = max(
            300, settings.digicert_timeout_seconds * max(1, settings.digicert_max_retries) + 60
        )
        conditions = [
            IssuanceCheck.certificate_id == certificate_id,
            or_(IssuanceCheck.lease_until.is_(None), IssuanceCheck.lease_until <= now),
        ]
        if not force:
            conditions += [
                IssuanceCheck.status.in_(("Pending", "Retrying")),
                IssuanceCheck.next_check_at <= now,
            ]
        claimed = session.execute(update(IssuanceCheck).where(*conditions).values(
            lease_token=token, lease_until=now + timedelta(seconds=lease_seconds),
        )).rowcount
        session.commit()  # Claim must be visible before any remote request.
        session.expire_all()  # SessionFactory uses expire_on_commit=False.
        if not claimed:
            raise GovernanceError("Check is running, not due yet, or needs manual retry")
        try:
            # Re-read under this session after claiming; only the order-detail GET is called.
            certificate = session.get(Certificate, certificate_id)
            if certificate.management_state != "Pending issuance":
                raise GovernanceError("Order is no longer pending")
            result = new_order_service.check_issuance(session, certificate, actor)
            check = session.get(IssuanceCheck, certificate_id)
            if check.lease_token != token:
                return result  # Lease expired; a different worker now owns this check.
            check.last_checked_at = now
            check.last_error = None
            check.consecutive_failures = 0
            if result.management_state == "Managed":
                check.status = "Issued"
                check.next_check_at = None
            elif result.management_state == "Order failed":
                check.status = "Failed"
                check.next_check_at = None
                check.last_error = f"DigiCert order {result.status.lower()}."
            else:
                check.status = "Pending"
                check.next_check_at = now + timedelta(
                    seconds=max(1, settings.issuance_check_interval_seconds)
                )
                job = session.query(Job).filter(
                    Job.certificate_id == certificate_id, Job.job_type == "NewOrder"
                ).order_by(Job.id.desc()).first()
                if job:
                    job.status = "Pending"
                    job.message = "Order not issued yet; automatic checks continue."
            check.lease_token = None
            check.lease_until = None
            session.commit()
            return result
        except Exception as error:
            session.rollback()
            # This includes malformed responses and database errors. Retry is bounded,
            # but keep pending orders visible until a human retries or resolves them.
            check = session.get(IssuanceCheck, certificate_id)
            if check and check.lease_token == token:
                check.last_checked_at = now
                check.last_error = public_error(error)
                failures = (0 if force and check.status == "Needs attention"
                            else check.consecutive_failures) + 1
                check.consecutive_failures = failures
                if failures >= max(1, settings.issuance_check_max_failures):
                    check.status = "Needs attention"
                    check.next_check_at = None
                else:
                    check.status = "Retrying"
                    delay = min(
                        max(1, settings.issuance_check_max_backoff_seconds),
                        max(1, settings.issuance_check_interval_seconds) * 2 ** (failures - 1),
                    )
                    check.next_check_at = now + timedelta(seconds=delay)
                check.lease_token = None
                check.lease_until = None
                job = session.query(Job).filter(
                    Job.certificate_id == certificate_id, Job.job_type == "NewOrder"
                ).order_by(Job.id.desc()).first()
                if job:
                    job.status = "Failed" if check.status == "Needs attention" else "Retrying"
                    job.message = f"Issuance check: {check.last_error} ({failures} failed checks)."
                session.commit()
            logger.warning("Issuance check failed for certificate %s: %s",
                           certificate_id, public_error(error))
            if force:
                raise DigiCertApiError(public_error(error)) from error
            return certificate

    def run_due_checks(self, *, now: datetime | None = None) -> int:
        now = now or utcnow()
        with SessionFactory() as session:
            certificate_ids = [id_ for (id_,) in session.query(IssuanceCheck.certificate_id).join(
                Certificate, Certificate.id == IssuanceCheck.certificate_id
            ).filter(
                Certificate.management_state == "Pending issuance",
                IssuanceCheck.status.in_(("Pending", "Retrying")),
                IssuanceCheck.next_check_at <= now,
                or_(IssuanceCheck.lease_until.is_(None), IssuanceCheck.lease_until <= now),
            ).order_by(IssuanceCheck.next_check_at).limit(25).all()]
        for certificate_id in certificate_ids:
            try:
                with SessionFactory() as session:
                    self.check_one(session, certificate_id, "system", now=now)
            except GovernanceError:
                pass  # Another worker may have claimed or completed this check.
            except Exception:
                logger.exception("Issuance monitor could not process certificate %s", certificate_id)
        return len(certificate_ids)

    def start(self) -> None:
        if not settings.issuance_check_enabled:
            return
        self._stop = Event()
        self._thread = Thread(target=self._run, name="issuance-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if hasattr(self, "_stop"):
            self._stop.set()
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_due_checks()
            except Exception:
                logger.exception("Issuance monitor cycle failed")
            self._stop.wait(max(1, settings.issuance_check_tick_seconds))


issuance_monitor = IssuanceMonitor()
