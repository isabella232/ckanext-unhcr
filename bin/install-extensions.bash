#!/bin/bash
set -euo pipefail

pip install setuptools-rust


git clone --depth 1 --branch release-2.1.0 https://github.com/ckan/ckanext-scheming
(cd ckanext-scheming && python3 setup.py develop)

git clone --depth 1 --branch v0.2.4 https://github.com/okfn/ckanext-hierarchy
(cd ckanext-hierarchy && python3 setup.py develop && pip install -r requirements.txt)

git clone --depth 1 --branch v1.0.0 https://github.com/keitaroinc/ckanext-s3filestore
(cd ckanext-s3filestore && python3 setup.py develop && pip install -r requirements.txt)

git clone --depth 1 --branch v1.1.1 https://github.com/keitaroinc/ckanext-saml2auth
(cd ckanext-saml2auth && python3 setup.py develop)
