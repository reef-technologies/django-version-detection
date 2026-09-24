# Django version detection

Guess a website's Django version by comparing its admin static files with hashes from Django releases.

## Setup

```sh
uv tool install git+https://github.com/reef-technologies/django-version-detection
```

## Generate signatures

```sh
django-version-detection generate
```

Downloads stable Django releases, hashes their static files, and writes signatures to a local cache.

`--min-version` raises that floor. `--signatures-path` is a global option and chooses another file:

```sh
django-version-detection --signatures-path ./signatures.json generate --min-version 4.2
```

## Detect

```sh
django-version-detection detect domain.com
```

Probes `https://domain.com/static/` and prints how closely each release matches:

```
| version | likelihood |
|---------|------------|
| 4.2.3   | 91.00%     |
| 4.2.7   | 98.00%     |
```

Pass `--static-root` when the site serves those files under another prefix:

```sh
django-version-detection detect domain.com --static-root /assets
```
