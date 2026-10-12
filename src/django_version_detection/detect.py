from collections import defaultdict
from hashlib import md5

import requests
import structlog
from structlog.contextvars import bound_contextvars

log = structlog.get_logger()
session = requests.Session()


class StaticRootNotFound(Exception):
    ...


def get_files_to_probe(signatures: dict[str, dict[str, str]]) -> list[str]:
    """ Find files which altogether cover all versions. """

    file_to_versions = defaultdict(set)
    for version, hashes in signatures.items():
        for file in hashes.keys():
            file_to_versions[file].add(version)

    to_probe = []
    covered_versions = set()
    for file, versions in sorted(file_to_versions.items(), key=lambda x: len(x[1]), reverse=True):
        if (new_covered_versions := versions - covered_versions):
            to_probe.append(file)
            covered_versions.update(new_covered_versions)

    return to_probe


def detect_static_root(
    domain: str,
    signatures: dict[str, dict[str, str]],
    request_timeout: float = 5,
) -> str:
    to_probe = get_files_to_probe(signatures)
    static_root = "/static"
    for file in to_probe:
        url = f"https://{domain}{static_root}{file}"
        response = session.head(url, timeout=request_timeout)
        if response.ok:
            return static_root

    raise StaticRootNotFound


def detect_version(
    domain: str,
    static_root: str,
    signatures: dict[str, dict[str, str]],
    request_timeout: float = 5,
) -> dict[str, float]:
    with bound_contextvars(domain=domain, static_root=static_root):
        log.info("searching static files")
        observed: dict[str, str | None] = {}
        for _, hashes in signatures.items():
            for file in hashes:
                if file in observed:
                    continue
                url = f"https://{domain}{static_root}{file}"
                log.info("probing", url=url)
                response = session.get(url, timeout=request_timeout)
                if response.ok:
                    observed[file] = md5(response.content).hexdigest()
                else:
                    observed[file] = None

    return {
        version: round(len(set(observed.items()) & set(hashes.items())) / len(hashes), 2)
        for version, hashes in signatures.items()
    }


def probe_django(domain: str, request_timeout: float = 5) -> bool:
    url = f"https://{domain}/"
    log.info("probing", url=url)
    response = session.get(url, timeout=request_timeout)
    return "csrftoken" in response.cookies
