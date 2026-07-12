"""In-app ACME (Let's Encrypt) certificate issuance and renewal.

Certificates and keys live in CERT_DIR. The separate ops-event-tools-ssl
gunicorn unit serves HTTPS on :8443 once fullchain.pem exists; after renewal
we SIGHUP it via its pidfile so workers reload the new certificate.
"""
import logging
import os
import signal
import time
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings

log = logging.getLogger(__name__)

LE_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
LE_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
USER_AGENT = "ops-event-tools"
RENEW_BEFORE_DAYS = 30
DNS_PROPAGATION_WAIT = 30  # seconds before asking LE to validate a TXT record


def cert_dir():
    settings.CERT_DIR.mkdir(parents=True, exist_ok=True)
    return settings.CERT_DIR


def fullchain_path():
    return cert_dir() / "fullchain.pem"


def privkey_path():
    return cert_dir() / "privkey.pem"


def cert_expiry() -> datetime | None:
    """Expiry of the current certificate, or None if absent/unreadable."""
    from cryptography import x509

    path = fullchain_path()
    if not path.exists():
        return None
    try:
        cert = x509.load_pem_x509_certificate(path.read_bytes())
        return cert.not_valid_after_utc
    except Exception:
        log.warning("Could not parse existing certificate", exc_info=True)
        return None


def _account_key():
    """Load or create the ACME account key."""
    import josepy
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    path = cert_dir() / "account_key.pem"
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        os.chmod(path, 0o600)
    return josepy.JWKRSA(key=key)


def _make_client(cfg):
    from acme import client, messages

    directory_url = LE_STAGING if cfg.acme_staging else LE_PRODUCTION
    account_key = _account_key()
    net = client.ClientNetwork(account_key, user_agent=USER_AGENT)
    directory = client.ClientV2.get_directory(directory_url, net)
    acme_client = client.ClientV2(directory, net=net)

    from acme import errors as acme_errors

    registration = messages.NewRegistration.from_data(
        email=cfg.acme_contact_email or None,
        terms_of_service_agreed=True,
    )
    try:
        net.account = acme_client.new_account(registration)
    except acme_errors.ConflictError as exc:
        # Account already exists for this key; reuse it
        net.account = messages.RegistrationResource(body=messages.Registration(), uri=exc.location)
    return acme_client


def _make_csr(domain: str) -> bytes:
    """Generate (and store) the certificate private key, return a CSR (PEM)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tmp = privkey_path().with_suffix(".pem.new")
    tmp.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    os.chmod(tmp, 0o600)

    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM)


def _select_challenge(authorization, challenge_type):
    for challenge_body in authorization.body.challenges:
        if challenge_body.typ == challenge_type:
            return challenge_body
    raise RuntimeError(f"ACME server offered no {challenge_type} challenge")


def _respond_dns01(cfg, challenge_body, account_key):
    from . import cloudflare_dns as cf

    validation = challenge_body.chall.validation(account_key)
    record_name = f"_acme-challenge.{cfg.ssl_domain}"
    zone_id = cf.find_zone_id(cfg.cloudflare_api_token, cfg.ssl_domain)
    record_id = cf.create_txt_record(cfg.cloudflare_api_token, zone_id, record_name, validation)

    def cleanup():
        cf.delete_record(cfg.cloudflare_api_token, zone_id, record_id)

    time.sleep(DNS_PROPAGATION_WAIT)
    return cleanup


def _respond_http01(cfg, challenge_body, account_key):
    from accounts.models import AcmeChallenge

    token = challenge_body.chall.encode("token")
    key_authorization = challenge_body.chall.key_authorization(account_key)
    AcmeChallenge.objects.update_or_create(
        token=token, defaults={"key_authorization": key_authorization},
    )

    def cleanup():
        AcmeChallenge.objects.filter(token=token).delete()

    return cleanup


def issue_certificate() -> None:
    """Order a certificate for cfg.ssl_domain. Records status on SiteConfig."""
    from accounts.models import SiteConfig

    cfg = SiteConfig.load()
    SiteConfig.objects.filter(pk=1).update(acme_last_status="running", acme_last_error="")

    cleanups = []
    try:
        if not cfg.ssl_domain:
            raise RuntimeError("No domain configured")
        if cfg.acme_method == "dns01" and not cfg.cloudflare_api_token:
            raise RuntimeError("DNS-01 selected but no Cloudflare API token configured")

        acme_client = _make_client(cfg)
        account_key = acme_client.net.key
        csr_pem = _make_csr(cfg.ssl_domain)
        order = acme_client.new_order(csr_pem)

        challenge_type = "dns-01" if cfg.acme_method == "dns01" else "http-01"
        for authorization in order.authorizations:
            challenge_body = _select_challenge(authorization, challenge_type)
            if cfg.acme_method == "dns01":
                cleanups.append(_respond_dns01(cfg, challenge_body, account_key))
            else:
                cleanups.append(_respond_http01(cfg, challenge_body, account_key))
            acme_client.answer_challenge(
                challenge_body, challenge_body.chall.response(account_key))

        finalized = acme_client.poll_and_finalize(order)

        # Atomic swap: key written by _make_csr as privkey.pem.new
        fullchain_tmp = fullchain_path().with_suffix(".pem.new")
        fullchain_tmp.write_text(finalized.fullchain_pem)
        os.replace(privkey_path().with_suffix(".pem.new"), privkey_path())
        os.replace(fullchain_tmp, fullchain_path())

        expiry = cert_expiry()
        SiteConfig.objects.filter(pk=1).update(
            acme_last_status="success", acme_last_error="", cert_expires_at=expiry,
        )
        log.info("Certificate issued for %s (expires %s)", cfg.ssl_domain, expiry)
        reload_ssl_server()
    except Exception as exc:
        log.exception("Certificate issuance failed")
        SiteConfig.objects.filter(pk=1).update(
            acme_last_status="error", acme_last_error=f"{type(exc).__name__}: {exc}"[:2000],
        )
        raise
    finally:
        for cleanup in cleanups:
            try:
                cleanup()
            except Exception:
                log.warning("Challenge cleanup failed", exc_info=True)


def renewal_due() -> bool:
    expiry = cert_expiry()
    if expiry is None:
        return True
    return expiry - datetime.now(dt_timezone.utc) < timedelta(days=RENEW_BEFORE_DAYS)


def renew_if_needed() -> bool:
    """Issue/renew when enabled and due. Returns True if issuance ran."""
    from accounts.models import SiteConfig

    cfg = SiteConfig.load()
    if not cfg.ssl_ready:
        return False
    if not renewal_due():
        return False
    issue_certificate()
    return True


def reload_ssl_server() -> None:
    """SIGHUP the SSL gunicorn (same user) so workers pick up the new cert."""
    pid_file = cert_dir() / "ssl.pid"
    if not pid_file.exists():
        return
    try:
        os.kill(int(pid_file.read_text().strip()), signal.SIGHUP)
        log.info("Reloaded SSL server")
    except (ValueError, ProcessLookupError, PermissionError):
        log.warning("Could not signal SSL server", exc_info=True)


RENEWAL_CHECK_SECONDS = 12 * 60 * 60


def _renewal_loop():
    from django.db import connection

    while True:
        try:
            renew_if_needed()
        except Exception:
            log.exception("Certificate renewal failed (will retry next cycle)")
        finally:
            connection.close()
        time.sleep(RENEWAL_CHECK_SECONDS)


def start_renewal_scheduler():
    import threading

    t = threading.Thread(target=_renewal_loop, daemon=True, name="acme-renewal")
    t.start()
    log.info("ACME renewal scheduler started (checks every %dh)", RENEWAL_CHECK_SECONDS // 3600)


def issue_in_thread() -> None:
    """Entry point for the Site Settings 'Issue Certificate Now' button."""
    from django.db import connection

    try:
        issue_certificate()
    except Exception:
        pass  # status already recorded on SiteConfig
    finally:
        connection.close()
