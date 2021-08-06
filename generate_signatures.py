from pathlib import Path
import json
from itertools import chain
from hashlib import md5
from collections import defaultdict


signatures = defaultdict(dict)
for version_dir in sorted(Path('static').iterdir(), reverse=True):
    version = version_dir.name
    print('Processing', version)
    for file in chain(version_dir.glob('**/*.js'), version_dir.glob('**/*.css')):
        if 'i18n' in str(file):
            continue
        signatures[version][str(file.relative_to(version_dir))] = md5(file.read_bytes()).hexdigest()

Path('signatures.json').write_text(json.dumps(signatures, indent=2))
