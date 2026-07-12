"""Minimal Cloudflare DNS API client for ACME DNS-01 TXT records."""
import logging

import requests

log = logging.getLogger(__name__)

API = "https://api.cloudflare.com/client/v4"


class CloudflareError(Exception):
    pass


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _check(resp: requests.Response) -> dict:
    data = resp.json()
    if not data.get("success"):
        raise CloudflareError(f"Cloudflare API error: {data.get('errors')}")
    return data


def find_zone_id(token: str, domain: str) -> str:
    """Find the zone containing `domain` (walks up: a.b.example.com -> example.com)."""
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        data = _check(requests.get(
            f"{API}/zones", headers=_headers(token), params={"name": candidate}, timeout=30,
        ))
        if data["result"]:
            return data["result"][0]["id"]
    raise CloudflareError(f"No Cloudflare zone found for {domain} (token needs Zone:Read + DNS:Edit)")


def create_txt_record(token: str, zone_id: str, name: str, content: str) -> str:
    data = _check(requests.post(
        f"{API}/zones/{zone_id}/dns_records",
        headers=_headers(token),
        json={"type": "TXT", "name": name, "content": content, "ttl": 60},
        timeout=30,
    ))
    record_id = data["result"]["id"]
    log.info("Created TXT %s (record %s)", name, record_id)
    return record_id


def delete_record(token: str, zone_id: str, record_id: str) -> None:
    try:
        _check(requests.delete(
            f"{API}/zones/{zone_id}/dns_records/{record_id}",
            headers=_headers(token), timeout=30,
        ))
        log.info("Deleted DNS record %s", record_id)
    except Exception:
        log.warning("Failed to clean up DNS record %s", record_id, exc_info=True)
