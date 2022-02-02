# -*- coding: utf-8 -*-

import datetime
import logging

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql.expression import func, false
from sqlalchemy.sql.sqltypes import Boolean
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
    'display_name': 'Pop. of Concern Location',
}
PRP = {
    'layer_name': 'wrl_prp_p_unhcr_ALL',
    'display_name': 'Reference Place',
}
LAYER_TO_DISPLAY_NAME = {
    l['layer_name']: l['display_name'] for l in [COUNTRY, ADMIN1, ADMIN2, POC, PRP]
}


class Geography(Base):
    __tablename__ = u'geography'

    pcode = Column(UnicodeText, primary_key=True)
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
    # some territories have the same ISO code as a country
    # These "secondary territories" must be treated as no-countries
    secondary_territory=Column(Boolean, default=False)
    
    # TODO: PostGIS geometry column

    @property
    def layer_nice_name(self):
        return LAYER_TO_DISPLAY_NAME[self.layer]

    @hybrid_property
    def display_name(self):
        return f'{self.gis_name} ({self.hierarchy_pcode})'

    @property
    def display_full_name(self):
        parent_names = [parent.gis_name for parent in self.parents]
        if len(parent_names) > 0:
            parent_names_str = ', '.join(parent_names)
            return f'{self.gis_name} ({parent_names_str})'
        else:
            return self.gis_name

    @hybrid_property
    def parents(self):
        # see diagram in https://github.com/okfn/ckanext-unhcr/issues/618 for pcode structure
        parent_pcodes = [
            self.hierarchy_pcode[0:11] if len(self.hierarchy_pcode) >= 14 else None, # admin2
            self.hierarchy_pcode[0:8] if len(self.hierarchy_pcode) >= 11 else None, # admin1
            self.hierarchy_pcode[2:5] if len(self.hierarchy_pcode) >= 8 else None, # country
        ]
        parent_pcodes = list(filter(lambda x: x is not None, parent_pcodes))
        if len(parent_pcodes) == 0:
            return []

        parents = model.Session.query(
            Geography
        ).filter(
            Geography.pcode.in_(parent_pcodes),
            Geography.gis_status == GisStatus.ACTIVE,
            # secondary terrirories are not counted as countries
            Geography.secondary_territory == false(),
        ).order_by(  # ADMIN2 > ADMIN1 > COUNTRY
            func.length(Geography.pcode).desc()
        ).all()

        return parents

    def __str__(self):
        return f'{LAYER_TO_DISPLAY_NAME[self.layer]}: {self.gis_name} ({self.pcode})'

    @classmethod
    def get_country_by_iso3(cls, iso3):
        return model.Session.query(
            Geography
        ).filter(
            Geography.iso3 == iso3,
            Geography.gis_status == GisStatus.ACTIVE,
            # secondary terrirories are not counted as countries
            Geography.secondary_territory == false(),
            Geography.layer == COUNTRY['layer_name']
        ).one_or_none()


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
