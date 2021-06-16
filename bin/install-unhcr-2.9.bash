#!/bin/bash
set -euo pipefail

python3 setup.py develop
pip install --upgrade -r requirements.txt
pip install --upgrade -r dev-requirements.txt
