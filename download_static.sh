#!/bin/sh
versions=( 3.2  3.1 3.0 2.2 2.1 2.0 1.11 1.10 1.9 1.8 1.7 1.6 1.5 )

mkdir -p tmp
rm -rf static && mkdir -p static
for version in "${versions[@]}"
do
    echo "Fetching $version"
    rm -rf tmp/*
    PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring pip install --target tmp --no-deps --force "django==$version"
    echo "Copying files"
    mkdir -p "static/$version"
    cp -r "tmp/django/contrib/admin/static/admin/." "static/$version"
done

rm -rf tmp/*
