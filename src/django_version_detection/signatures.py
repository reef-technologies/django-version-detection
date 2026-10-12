from collections import defaultdict
from contextlib import suppress
from itertools import chain, zip_longest
import re
import subprocess
from hashlib import md5
from pathlib import Path

from more_itertools import one
from platformdirs import user_cache_path
import requests
import structlog
from tempfile import TemporaryDirectory

log = structlog.get_logger()

RE_DJANGO_VERSION = re.compile(r"\d+(?:\.\d+)*")
DEFAULT_SIGNATURES_PATH = user_cache_path("django_version_detection") / "signatures.json"


class Version(tuple):
    def __new__(cls, *numbers: int):
        return super().__new__(cls, numbers)

    @classmethod
    def from_str(cls, version_str: str) -> "Version":
        return cls(*map(int, version_str.split(".")))

    def __str__(self) -> str:
        return ".".join(map(str, self))


def gte(version_a: Version, version_b: Version) -> bool:
    for a, b in zip_longest(version_a, version_b, fillvalue=0):
        if a != b:
            return a > b
    return True


class NoStaticPathIncludedError(ValueError):
    ...

class MultipleStaticPathsIncludedError(ValueError):
    ...


def remove_path_to_static(path: Path) -> Path:
    return one(
        (path.relative_to(parent) for parent in path.parents if parent.name == "static"),
        too_short=NoStaticPathIncludedError,
        too_long=MultipleStaticPathsIncludedError,
    )


def fetch_releases() -> list[Version]:
    log.info("fetching releases")
    response = requests.get("https://pypi.org/pypi/Django/json", timeout=120)
    response.raise_for_status()
    return [
        Version.from_str(version)
        for version in response.json()["releases"]
        if RE_DJANGO_VERSION.fullmatch(version)
    ]


def generate_signatures(min_version: Version = Version(0,)) -> dict[str, dict[str, str]]:
    versions = [v for v in fetch_releases() if gte(v, min_version)]
    log.info("found versions", versions=len(versions))

    signatures = defaultdict(dict)
    for version in versions:
        with TemporaryDirectory() as downloads_dir:
            version_dir = Path(downloads_dir) / str(version)
            log.info("downloading", destination=version_dir)
            subprocess.run(
                [
                    "uv", "pip", "install",
                    "--exclude-newer", "false",
                    "--link-mode", "copy",
                    "--no-deps",
                    "--no-managed-python",
                    "--target", str(version_dir),
                    f"Django=={str(version)}",
                ],
                check=True,
            )

            log.info("generating signatures", version=version)
            for file in chain(version_dir.glob('**/*.js'), version_dir.glob('**/*.css')):
                if 'i18n' in str(file):
                    continue
                with suppress(NoStaticPathIncludedError):
                    relative_path = remove_path_to_static(file.relative_to(version_dir))
                    signatures[str(version)][f"/{relative_path}"] = md5(file.read_bytes()).hexdigest()

    return signatures
