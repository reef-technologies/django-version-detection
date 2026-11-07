from collections.abc import Iterator
from dataclasses import dataclass
from itertools import product
import re
from collections import defaultdict
from contextlib import suppress
from functools import cache
from hashlib import md5
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
import structlog
from bs4 import BeautifulSoup
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


@cache
def fetch(url: str) -> str:
    response = session.get(url, timeout=5)
    response.raise_for_status()
    return response.text


@dataclass
class Page:
    url: str

    def __post_init__(self) -> None:
        assert re.match(r"^https?://", self.url), f"Invalid URL: {self.url}"

    @property
    def content(self) -> str:
        return fetch(self.url)

    def has_django_signs(self) -> bool:
        return "csrfmiddlewaretoken" in self.content

    def has_wordpress_signs(self) -> bool:
        return bool(re.search(r"\bwp-", self.content))

    def iter_links(self) -> Iterator[str]:
        soup = BeautifulSoup(self.content, "html.parser")
        for tag in soup.find_all(True):
            for attr in ("href", "src"):
                link = tag.get(attr)
                if not isinstance(link, str):
                    continue
                yield urljoin(self.url, link)


@dataclass
class Detector:
    domain: str
    signatures: dict[str, dict[str, str]]

    def __post_init__(self) -> None:
        if re.match(r"^https?://", self.domain):
            self.domain = urlsplit(self.domain).netloc

    def iter_pages_to_probe(self) -> Iterator[Page]:
        yield Page(url=f"https://{self.domain}/")
        yield Page(url=f"https://{self.domain}/admin/login/")
        yield Page(url=f"https://{self.domain}/accounts/login/")
        yield Page(url=f"https://{self.domain}/account/login/")

    def is_django(self) -> bool | None:
        for page in self.iter_pages_to_probe():
            with suppress(requests.RequestException):
                if page.has_django_signs():
                    return True
                if page.has_wordpress_signs():
                    return False

    @classmethod
    def _extract_static_root_from_link(cls, link: str) -> str:
        with suppress(ValueError):
            static_root, _ = re.split(r"/admin/(?:css|js)/", link, maxsplit=1, flags=re.IGNORECASE)
            return static_root

        with suppress(ValueError):
            static_root, separator, _ = re.split(r"(/static)/", link, maxsplit=1, flags=re.IGNORECASE)
            return static_root + separator

        raise StaticRootNotFound(link)

    def get_static_root(self) -> str:
        possible_static_roots = {f"https://{self.domain}/static"}

        for page in self.iter_pages_to_probe():
            with suppress(requests.RequestException):
                for link in page.iter_links():
                    with suppress(StaticRootNotFound):
                        possible_static_roots.add(self._extract_static_root_from_link(link))

        # TODO: probe manifest static files
        files_to_probe = get_files_to_probe(self.signatures)
        for static_root, file in product(possible_static_roots, files_to_probe):
            url = f"{static_root}{file}"
            with bound_contextvars(url=url):
                try:
                    response = session.head(url, timeout=5)
                except requests.RequestException as exc:
                    log.warning("probe failed", error=str(exc))
                    continue
                if response.status_code == 200:
                    with suppress(ContentTypeMissing):
                        if not content_type_matches(response):
                            log.warning("unexpected content type")
                            continue
                    log.info("static root found", url=url)
                    return static_root

        raise StaticRootNotFound(self.domain)

    def detect_version(self, static_root: str) -> dict[str, float]:
        with bound_contextvars(domain=self.domain, static_root=static_root):
            log.info("searching static files")
            observed: dict[str, str | None] = {}
            for _, hashes in self.signatures.items():
                for file in hashes:
                    if file in observed:
                        continue

                    url = f"{static_root}{file}" if urlsplit(static_root).scheme else f"https://{self.domain}{static_root}{file}"
                    log.info("probing", url=url)
                    try:
                        response = session.get(url, timeout=5)
                    except requests.RequestException as exc:
                        log.warning("probe failed", url=url, error=str(exc))
                        observed[file] = None
                        continue

                    if not response.ok:
                        observed[file] = None
                        continue

                    with suppress(ContentTypeMissing):
                        if not content_type_matches(response):
                            log.warning("unexpected content type")
                            observed[file] = None
                            continue

                    observed[file] = md5(response.content).hexdigest()

        return {
            version: round(len(set(observed.items()) & set(hashes.items())) / len(hashes), 2)
            for version, hashes in self.signatures.items()
        }
