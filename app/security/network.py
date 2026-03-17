from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from typing import Iterable, Sequence, Union

from starlette.requests import Request

IPAddress = Union[IPv4Address, IPv6Address]
IPNetwork = Union[IPv4Network, IPv6Network]


def _parse_ip(raw_value: str | None) -> IPAddress | None:
    if not raw_value:
        return None

    candidate = raw_value.strip().strip("'").strip('"')
    if not candidate:
        return None

    if candidate.lower().startswith("for="):
        candidate = candidate[4:].strip().strip("'").strip('"')

    if candidate.startswith("[") and "]" in candidate:
        closing_index = candidate.find("]")
        candidate = candidate[1:closing_index]
    elif candidate.count(":") == 1 and "." in candidate:
        host, _, port = candidate.partition(":")
        if port.isdigit():
            candidate = host

    if "%" in candidate:
        candidate = candidate.split("%", 1)[0]

    try:
        return ip_address(candidate)
    except ValueError:
        return None


def _parse_networks(values: Sequence[str]) -> list[IPNetwork]:
    parsed: list[IPNetwork] = []
    for value in values:
        candidate = value.strip()
        if not candidate:
            continue
        try:
            parsed.append(ip_network(candidate, strict=False))
        except ValueError:
            continue
    return parsed


def _is_ip_in_networks(ip: IPAddress, networks: Iterable[IPNetwork]) -> bool:
    return any(ip in network for network in networks)


def resolve_client_ip(request: Request, *, trusted_proxy_networks: Sequence[str]) -> IPAddress | None:
    trusted_networks = _parse_networks(trusted_proxy_networks)

    remote_ip = _parse_ip(request.client.host if request.client else None)
    if remote_ip is None:
        return None

    if not trusted_networks or not _is_ip_in_networks(remote_ip, trusted_networks):
        return remote_ip

    chain: list[IPAddress] = []

    x_forwarded_for = request.headers.get("x-forwarded-for", "")
    if x_forwarded_for:
        for token in x_forwarded_for.split(","):
            forwarded_ip = _parse_ip(token)
            if forwarded_ip is not None:
                chain.append(forwarded_ip)

    if not chain:
        x_real_ip = _parse_ip(request.headers.get("x-real-ip"))
        if x_real_ip is not None:
            chain.append(x_real_ip)

    chain.append(remote_ip)

    for ip in reversed(chain):
        if not _is_ip_in_networks(ip, trusted_networks):
            return ip

    return chain[0] if chain else remote_ip


def is_request_from_internal_network(
    request: Request,
    *,
    internal_networks: Sequence[str],
    trusted_proxy_networks: Sequence[str],
) -> bool:
    client_ip = resolve_client_ip(request, trusted_proxy_networks=trusted_proxy_networks)
    if client_ip is None:
        return False
    return _is_ip_in_networks(client_ip, _parse_networks(internal_networks))
