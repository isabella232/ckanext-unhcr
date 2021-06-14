#!/bin/bash
set -euo pipefail


git clone --depth 1 --branch release-2.1.0 https://github.com/ckan/ckanext-scheming
(cd ckanext-scheming && python setup.py develop)

git clone --depth 1 --branch 0.2.3 https://github.com/okfn/ckanext-hierarchy
(cd ckanext-hierarchy && python setup.py develop && pip install -r requirements.txt)

git clone --depth 1 --branch v1.0.0 https://github.com/keitaroinc/ckanext-s3filestore
(cd ckanext-s3filestore && python setup.py develop && pip install -r requirements.txt)

git clone --depth 1 --branch v1.1.1 https://github.com/keitaroinc/ckanext-saml2auth
(
    cd ckanext-saml2auth &&
    # workaround for Python 2
    # TODO: remove when we move to Py3
    sed -i -e "s/install_requires=\['pysaml2>=6.3.0'\],//" setup.py &&
    pip install pysaml2==4.9.0 python2-secrets==1.0.5 &&
    python setup.py develop
)
