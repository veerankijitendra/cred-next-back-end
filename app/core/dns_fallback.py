import json
import logging
import socket
import sys
import urllib.request

logger = logging.getLogger(__name__)

_orig_getaddrinfo = socket.getaddrinfo
_dns_cache: dict[str, str] = {}


def _resolve_with_public_dns(host: str) -> str | None:
    if host in _dns_cache:
        return _dns_cache[host]

    for dns_url in (
        f"https://dns.google/resolve?name={host}&type=A",
        f"https://cloudflare-dns.com/dns-query?name={host}&type=A",
    ):
        try:
            req = urllib.request.Request(
                dns_url,
                headers={"Accept": "application/dns-json", "User-Agent": "crednexa-api"},
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for answer in data.get("Answer", []):
                    # Type 1 is DNS A record (IPv4 address)
                    if answer.get("type") == 1 and answer.get("data"):
                        ip = answer["data"]
                        _dns_cache[host] = ip
                        return ip
        except Exception:
            continue
    return None


def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror as exc:
        if isinstance(host, str) and ("neon.tech" in host or "aws." in host):
            ip = _resolve_with_public_dns(host)
            if ip:
                return _orig_getaddrinfo(ip, port, family, type, proto, flags)
        raise exc


def setup_dns_fallback() -> None:
    """Setup fallback public DNS resolution for ISPs that refuse cloud DB domains."""
    socket.getaddrinfo = patched_getaddrinfo

