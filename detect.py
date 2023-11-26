import json
import logging
from argparse import ArgumentParser
from hashlib import md5
from pathlib import Path

import requests
from natsort import natsorted
from tabulate import tabulate

log = logging.getLogger(__name__)
signatures = json.loads(Path('signatures.json').read_text())


def detect_version(domain: str, static_path: str = 'static/admin/') -> dict[str, float]:
    assert signatures

    if not domain.startswith('https'):
        domain = 'https://' + domain
    if not domain.endswith('/'):
        domain += '/'

    if not static_path.startswith('https'):
        static_path = domain + 'static/admin/'
    if not static_path.endswith('/'):
        static_path += '/'
    log.info('Searching static files in %s', static_path)

    session = requests.Session()
    signature = {}  # current website signature
    for version, hashes in signatures.items():
        log.info('Getting signatures for %s', version)
        for file in hashes.keys():
            if file in signature:
                continue

            url = static_path + file
            log.info('Fetching %s', url)
            try:
                response = session.get(url, timeout=5)
                response.raise_for_status()
                signature[file] = md5(response.content).hexdigest() if response.ok else None
            except Exception:
                signature[file] = None

    result = {}
    for version, version_signature in signatures.items():
        common = len(set(signature.items()) & set(version_signature.items()))
        closeness = common / len(version_signature)
        result[version] = round(closeness, 2)
    return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    parser = ArgumentParser()
    parser.add_argument('domain')
    parser.add_argument('--static-path', type=str, default='static/admin/')
    args = parser.parse_args()

    log.info('Loaded signatures for %s', ', '.join(signatures.keys()))
    log.info('Scanning %s', args.domain)
    versions = detect_version(args.domain, static_path=args.static_path)
    print(tabulate(
        reversed(natsorted((version, f'{likelihood*100:.2f}%') for version, likelihood in versions.items())),
        headers=['version', 'likelihood'],
        tablefmt='github',
    ))
