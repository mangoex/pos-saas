"""Bounded TXT adapter using a fixed DNS-over-HTTPS provider."""

import json
import re

import httpx


class DnsUnavailable(Exception):
    pass


def lookup_txt(name: str) -> list[str]:
    try:
        with httpx.Client(timeout=4, follow_redirects=False, trust_env=False) as client:
            with client.stream(
                "GET",
                "https://dns.google/resolve",
                params={
                    "name": name,
                    "type": "TXT",
                    "edns_client_subnet": "0.0.0.0/0",
                },
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise DnsUnavailable()
        data = json.loads(body)
        if not isinstance(data, dict):
            raise DnsUnavailable()
        if data.get("Status") == 3:
            return []
        if data.get("Status") != 0 or data.get("TC"):
            raise DnsUnavailable()
        values = []
        for record in data.get("Answer", []):
            if record.get("type") == 16 and record.get("name", "").rstrip(".") == name:
                chunks = re.findall(r'"(?:[^"\\]|\\.)*"', record["data"])
                values.append("".join(json.loads(chunk) for chunk in chunks))
        return values
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise DnsUnavailable() from exc
