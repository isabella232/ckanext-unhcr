# -*- coding: utf-8 -*-

import os
import contextlib

import pytest

from ckan.cli.db import _resolve_alembic_config
import ckan.model as model
from ckan.config import environment

from ckanext.unhcr.models import create_tables as unhcr_create_tables


# TODO: in the next CKAN release
# there will be a more elegant way to achieve this
@contextlib.contextmanager
def _repo_for_plugin(plugin):
    original = model.repo._alembic_ini
    model.repo._alembic_ini = _resolve_alembic_config(plugin)
    try:
        yield model.repo
    finally:
        model.repo._alembic_ini = original

def _apply_alembic_migrations():
    with _repo_for_plugin('unhcr') as repo:
        repo.upgrade_db('head')


@pytest.fixture
def unhcr_migrate():
    unhcr_create_tables()
    _apply_alembic_migrations()


@pytest.fixture(autouse=True, scope='session')
def use_test_env():
    # setup
    os.environ['CKAN_TESTING'] = 'True'
    environment.update_config()

    yield

    # teardown
    os.environ.pop('CKAN_TESTING', None)
