#!/bin/bash
set -euo pipefail

pip install setuptools-rust


git clone --depth 1 --branch release-2.1.0 https://github.com/ckan/ckanext-scheming
(cd ckanext-scheming && python3 setup.py develop)

git clone --depth 1 --branch v0.2.4 https://github.com/okfn/ckanext-hierarchy
(cd ckanext-hierarchy && python3 setup.py develop && pip install -r requirements.txt)

git clone --depth 1 --branch v1.0.0 https://github.com/keitaroinc/ckanext-s3filestore
(cd ckanext-s3filestore && python3 setup.py develop && pip install -r requirements.txt)

git clone --depth 1 --branch v1.2.2 https://github.com/keitaroinc/ckanext-saml2auth
(cd ckanext-saml2auth && python3 setup.py develop)

git clone --depth 1 --branch v2.0.2 https://github.com/okfn/ckanext-ddi
(cd ckanext-ddi && python3 setup.py develop && pip install -r requirements.txt)

git clone --depth 1 --branch 0.0.7 https://github.com/ckan/ckanext-pdfview
(cd ckanext-pdfview && python3 setup.py develop)

git clone --depth 1 --branch v0.0.3 https://github.com/okfn/ckanext-facetcollapse
(cd ckanext-facetcollapse && python3 setup.py develop)

git clone --depth 1 --branch v1.3.2 https://github.com/ckan/ckanext-harvest
(cd ckanext-harvest && python3 setup.py develop && pip install -r pip-requirements.txt)
