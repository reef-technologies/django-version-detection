from collections import defaultdict
from contextlib import suppress
from functools import cache
from hashlib import md5
from pathlib import Path

import requests
import structlog
from structlog.contextvars import bound_contextvars

log = structlog.get_logger()
session = requests.Session()

EXPECTED_CONTENT_TYPES = {
    ".css": {"text/css"},
    ".js": {
        "application/javascript",
        "text/javascript",
        "application/x-javascript",
    },
}


class ContentTypeMissing(Exception):
    ...


def content_type_matches(response: requests.Response) -> bool:
    try:
        content_type = response.headers["Content-Type"]
    except KeyError as exc:
        raise ContentTypeMissing from exc

    media_type = content_type.split(";", 1)[0].strip().lower()
    suffix = Path(response.request.url).suffix.lower()
    return media_type in EXPECTED_CONTENT_TYPES[suffix]


class StaticRootNotFound(Exception):
    ...


def get_files_to_probe(signatures: dict[str, dict[str, str]]) -> tuple[str, ...]:
    _signatures = tuple((version, tuple(sorted(hashes.items()))) for version, hashes in signatures.items())
    return _get_files_to_probe(_signatures)


@cache
def _get_files_to_probe(
    signatures: tuple[tuple[str, tuple[tuple[str, str], ...]], ...],
) -> tuple[str, ...]:
    """ Find files which altogether cover all versions. """

    file_to_versions = defaultdict(set)
    for version, hashes in signatures:
        for file, _ in hashes:
            file_to_versions[file].add(version)

    to_probe = []
    covered_versions = set()
    for file, versions in sorted(file_to_versions.items(), key=lambda x: len(x[1]), reverse=True):
        if (new_covered_versions := versions - covered_versions):
            to_probe.append(file)
            covered_versions.update(new_covered_versions)

    return tuple(to_probe)


def detect_static_root(
    domain: str,
    signatures: dict[str, dict[str, str]],
    request_timeout: float = 5,
) -> str:
    to_probe = get_files_to_probe(signatures)
    static_root = "/static"
    for file in to_probe:
        url = f"https://{domain}{static_root}{file}"
        with bound_contextvars(url=url):
            try:
                response = session.head(url, timeout=request_timeout)
            except requests.RequestException as exc:
                log.warning("probe failed", error=str(exc))
                continue
            if response.status_code == 200:
                with suppress(ContentTypeMissing):
                    if not content_type_matches(response):
                        log.warning("unexpected content type")
                        continue
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
                try:
                    response = session.get(url, timeout=request_timeout)
                except requests.RequestException as exc:
                    log.warning("probe failed", url=url, error=str(exc))
                    observed[file] = None
                    continue
                
                if response.ok:
                    with suppress(ContentTypeMissing):
                        if not content_type_matches(response):
                            log.warning("unexpected content type")
                            observed[file] = None
                            continue
                    observed[file] = md5(response.content).hexdigest()
                    continue

                observed[file] = None

    return {
        version: round(len(set(observed.items()) & set(hashes.items())) / len(hashes), 2)
        for version, hashes in signatures.items()
    }
