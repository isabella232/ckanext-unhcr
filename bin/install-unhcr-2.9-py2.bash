#!/bin/bash
set -euo pipefail

python setup.py develop
pip install --upgrade -r requirements.txt
pip install --upgrade -r dev-requirements.txt
