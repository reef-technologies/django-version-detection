import json
import logging
from operator import itemgetter
import sys
from pathlib import Path
from typing import Any

import click
import structlog
from tabulate import tabulate
from natsort import natsorted

from .detect import detect_static_root, detect_version
from .signatures import RE_DJANGO_VERSION, generate_signatures, Version, DEFAULT_SIGNATURES_PATH

DEFAULT_MIN_VERSION = "3.0"

log = structlog.get_logger()


def parse_version(ctx: click.Context, param: click.Parameter, value: str) -> Version:
    if not RE_DJANGO_VERSION.fullmatch(value):
        raise click.BadParameter(f"Invalid version: {value}")
    return Version.from_str(value)


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


@click.group()
@click.option(
    "--signatures-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_SIGNATURES_PATH,
    show_default=True,
    help="Path to signatures file",
)
@click.pass_context
def cli(ctx: click.Context, signatures_path: Path) -> None:
    configure_logging()
    ctx.obj = {"signatures_path": signatures_path}


@cli.command()
@click.option(
    "--min-version",
    default=DEFAULT_MIN_VERSION,
    callback=parse_version,
    show_default=True,
    help="Ignore Django releases older than this",
)
@click.pass_obj
def generate(obj: dict[str, Any], min_version: Version) -> None:
    """ Download Django releases and write signatures. """
    signatures_path = obj["signatures_path"]
    signatures = generate_signatures(min_version=min_version)
    signatures_path.parent.mkdir(parents=True, exist_ok=True)
    signatures_path.write_text(json.dumps(signatures, indent=2))
    log.info("wrote signatures", path=str(signatures_path), versions=list(signatures.keys()))


@cli.command()
@click.argument("domain")
@click.option("--static-root", default=None, help="Static root to use, autodetected if not provided")
@click.pass_context
def detect(ctx: click.Context, domain: str, static_root: str) -> None:
    """ Compare a website's admin static files with known Django signatures. """
    signatures_path: Path = ctx.obj["signatures_path"]
    if not signatures_path.exists():
        log.info("signatures file not found, generating")
        ctx.invoke(generate)

    signatures = json.loads(signatures_path.read_text())
    log.info("loaded signatures", versions=list(signatures.keys()))

    if not static_root:
        log.info("autodetecting static root")
        static_root = detect_static_root(domain=domain, signatures=signatures)

    log.info("scanning", domain=domain)
    versions = detect_version(domain=domain, static_root=static_root, signatures=signatures)
    click.echo(tabulate(
        [(version, f"{likelihood * 100:.2f}%") for version, likelihood in natsorted(versions.items(), key=itemgetter(0))],
        headers=["version", "likelihood"],
        tablefmt="github",
    ))
