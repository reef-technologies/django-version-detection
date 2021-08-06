# Small script to guess django verion of website

## Preparations (may be skipped)

This will fetch popular django versions in `tmp` dir and extract static files for admin application:

```sh
sh download_static.sh
```

This will generate "signatures" of those static files for each django version, and put them into `signatures.json`:

```sh
python generate_signatures.py
```

`signatures.py` already contains some signatures for popular django versions.

## Run

```sh
python detect.py domain.com
```
outputs
```
https://domain.com/
3.2 - 98.97%
3.1 - 77.23%
3.0 - 1.01%
2.2 - 1.14%
2.1 - 1.14%
2.0 - 1.14%
1.9 - 3.57%
1.8 - 0.00%
1.7 - 0.00%
1.6 - 0.00%
1.11 - 3.03%
1.10 - 3.03%
```
