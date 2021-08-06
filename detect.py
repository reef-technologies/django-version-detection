from argparse import ArgumentParser
from pathlib import Path
import json
from typing import Optional
from hashlib import md5
import requests


signatures = json.loads(Path('signatures.json').read_text())
print('Loaded signatures for', ', '.join(signatures.keys()))


def detect_version(domain: str) -> dict[str, float]:
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
    args = parser.parse_args()

    print(args.domain)
    versions = detect_version(args.domain)
    for version, likelihood in versions.items():
        print(f'{version} - {likelihood*100:.2f}%')
