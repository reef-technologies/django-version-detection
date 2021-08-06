from argparse import ArgumentParser
from pathlib import Path
import json
from typing import Optional
from hashlib import md5
import requests


signatures = json.loads(Path('signatures.json').read_text())
print('Loaded signatures for', ', '.join(signatures.keys()))


def detect_version(domain: str) -> Optional[str]:
    if not domain.startswith('https'):
        domain = 'https://' + domain
    if not domain.endswith('/'):
        domain += '/'
    static_base = domain + 'static/admin/'
    print('Searching static files in', static_base)

    session = requests.Session()
    signature = {}  # current website signature
    for version, hashes in signatures.items():
        print('Checking signatures for', version)
        for file in hashes.keys():

            if file not in signature:
                url = static_base + file
                print('Fetching', url)
                response = session.get(url, timeout=5)
                if not response.ok:
                    if response.status_code == 404:
                        signature[file] = None
                    else:
                        response.raise_for_status()
                else:
                    signature[file] = md5(response.content).hexdigest()

    print(domain)
    for version, version_signature in signatures.items():
        common = len(set(signature.items()) & set(version_signature.items()))
        closeness = common * 100 / len(version_signature)
        print(f'{version} - {closeness:.2f}%')


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('domain')
    args = parser.parse_args()

    detect_version(args.domain)
