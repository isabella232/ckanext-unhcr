# -*- coding: utf-8 -*-

import os
import contextlib
import sqlalchemy as sa
import pytest

from ckan.cli.db import _resolve_alembic_config
import ckan.model as model
from ckan.common import config
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

    # it's seam the DB is cleared and we lose this custom record
    # This should be added in 009_f671e76f1a39_create_a_general_geography migration
    engine = sa.create_engine(config.get('sqlalchemy.url'))
    sql = """INSERT INTO geography 
             (pcode, iso3, gis_name, gis_status, layer, hierarchy_pcode, last_modified, secondary_territory) VALUES 
             ('UNSPECIFIED', 'UNSPECIFIED', 'UNSPECIFIED', 'active', 'wrl_polbnd_int_1m_a_unhcr', 'UNSPECIFIED', '2022-01-27 17:22:38.694909', 'f')
             ON CONFLICT DO NOTHING
          """
    engine.execute(sql)


@pytest.fixture(autouse=True, scope='session')
def use_test_env():
    # setup
    os.environ['CKAN_TESTING'] = 'True'
    environment.update_config()

    yield

    # teardown
    os.environ.pop('CKAN_TESTING', None)
