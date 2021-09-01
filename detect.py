from argparse import ArgumentParser
from pathlib import Path
import json
from typing import Optional
from hashlib import md5
import requests
from tabulate import tabulate
from natsort import natsorted


signatures = json.loads(Path('signatures.json').read_text())
print('Loaded signatures for', ', '.join(signatures.keys()))


def detect_version(domain: str, static_path: str = 'static/admin/') -> dict[str, float]:
    if not domain.startswith('https'):
        domain = 'https://' + domain
    if not domain.endswith('/'):
        domain += '/'

    if not static_path.startswith('https'):
        static_path = domain + 'static/admin/'
    if not static_path.endswith('/'):
        static_path += '/'
    print('Searching static files in', static_path)

    session = requests.Session()
    signature = {}  # current website signature
    for version, hashes in signatures.items():
        print('Checking signatures for', version)
        for file in hashes.keys():
            if file not in signature:
                url = static_path + file
                print('Fetching', url)
                try:
                    response = session.get(url, timeout=5)
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
    parser = ArgumentParser()
    parser.add_argument('domain')
    parser.add_argument('--static-path', type=str, default=None)
    args = parser.parse_args()

    print(args.domain)
    versions = detect_version(args.domain, static_path=args.static_path)
    print(tabulate(
        reversed(natsorted((version, f'{likelihood*100:.2f}%') for version, likelihood in versions.items())),
        headers=['version', 'likelihood'],
        tablefmt='github',
    ))
