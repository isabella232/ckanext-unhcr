# -*- coding: utf-8 -*-

import datetime
import logging

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.types import Enum, UnicodeText

from ckan.model.meta import metadata
import ckan.model as model
from ckan.model.types import make_uuid


log = logging.getLogger(__name__)

Base = declarative_base(metadata=metadata)
USER_REQUEST_TYPE_NEW = 'new-user'
USER_REQUEST_TYPE_RENEWAL = 'renewal'


class TimeSeriesMetric(Base):
    __tablename__ = u'time_series_metrics'

    timestamp = Column(DateTime, primary_key=True, default=datetime.datetime.utcnow)
    datasets_count = Column(Integer)
    deposits_count = Column(Integer)
    containers_count = Column(Integer)


class AccessRequest(Base):
    __tablename__ = u'access_requests'

    id = Column(UnicodeText, primary_key=True, default=make_uuid)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    user_id = Column(UnicodeText, nullable=False)
    message = Column(UnicodeText, nullable=False)
    role = Column(
        Enum('member', 'editor', 'admin', name='access_request_role_enum'),
        nullable=False,
    )
    status = Column(
        Enum('requested', 'approved', 'rejected', name='access_request_status_enum'),
        default='requested',
        nullable=False,
    )
    object_type = Column(
        Enum('package', 'organization', 'user', name='access_request_object_type_enum'),
        nullable=False,
    )
    object_id = Column(UnicodeText, nullable=False)
    data = Column(MutableDict.as_mutable(JSONB), nullable=True)
    actioned_by = Column(UnicodeText, nullable=True)  # user who approved or rejected the request


class GisStatus(object):
    ACTIVE = 'active'
    INACTIVE = 'inactive'


ADMIN1 = {
    'layer_name': 'wrl_polbnd_adm1_a_unhcr',
    'display_name': 'Admin 1',
}
ADMIN2 = {
    'layer_name': 'wrl_polbnd_adm2_a_unhcr',
    'display_name': 'Admin 2',
}
COUNTRY = {
    'layer_name': 'wrl_polbnd_int_1m_a_unhcr',
    'display_name': 'Country',
}
POC = {
    'layer_name': 'wrl_prp_p_unhcr_PoC',
    'display_name': 'Pop. of Concern',
}
PRP = {
    'layer_name': 'wrl_prp_p_unhcr_ALL',
    'display_name': 'Reference Place',
}
LAYER_TO_DISPLAY_NAME = {
    l['layer_name']: l['display_name'] for l in [ADMIN1, ADMIN2, COUNTRY, POC, PRP]
}


class Geography(Base):
    __tablename__ = u'geography'

    globalid = Column(UnicodeText, primary_key=True)
    pcode = Column(UnicodeText, nullable=False)
    iso3 = Column(UnicodeText, nullable=False)
    gis_name = Column(UnicodeText, nullable=False)
    gis_status = Column(
        Enum(GisStatus.ACTIVE, GisStatus.INACTIVE, name='geography_gis_statuse_enum'),
        nullable=False
    )
    layer = Column(UnicodeText, nullable=False)
    hierarchy_pcode = Column(UnicodeText, nullable=False)
    last_modified = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow
    )
    # TODO: PostGIS geometry column

    @hybrid_property
    def display_name(self):
        return f'{LAYER_TO_DISPLAY_NAME[self.layer]}: {self.gis_name} ({self.hierarchy_pcode})'


def create_metric_columns():
    cols = ['datasets_count', 'deposits_count', 'containers_count']
    table = TimeSeriesMetric.__tablename__
    for col in cols:
        model.Session.execute(
            u"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} INTEGER;".format(
                table=table,
                col=col
            )
        )
    model.Session.commit()


def extend_access_request_object_type_enum():
    # We can't modify the enum in-place inside a transaction on Postgres < 12
    # it will throw 'ALTER TYPE ... ADD cannot run inside a transaction block'
    # so we're going to..

    # swtich to isolation_level = AUTOCOMMIT
    model.Session.connection().connection.set_isolation_level(0)

    # modify the enum in-place
    model.Session.execute(
        u"ALTER TYPE access_request_object_type_enum ADD VALUE IF NOT EXISTS 'user';"
    )

    # switch back to isolation_level = READ_COMMITTED
    model.Session.connection().connection.set_isolation_level(1)


def add_access_request_data_column():
    table = AccessRequest.__tablename__
    model.Session.execute(
        u"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS data JSONB;".format(
            table=table
        )
    )
    model.Session.commit()

def add_access_request_actioned_by_column():
    table = AccessRequest.__tablename__
    model.Session.execute(
        u"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS actioned_by text;".format(
            table=table
        )
    )
    model.Session.commit()

def create_tables():
    if not TimeSeriesMetric.__table__.exists():
        TimeSeriesMetric.__table__.create()
        log.info(u'TimeSeriesMetric database table created')

    create_metric_columns()


    if not AccessRequest.__table__.exists():
        AccessRequest.__table__.create()
        log.info(u'AccessRequest database table created')

    add_access_request_data_column()
    add_access_request_actioned_by_column()
    extend_access_request_object_type_enum()
