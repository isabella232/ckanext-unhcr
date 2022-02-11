"""create a general geography

Now geographies field is mandatory and it is necessary to
create a general geography for testing and for datasets that have no specific geography.

Revision ID: f671e76f1a39
Revises: 392dac5349ff
Create Date: 2022-01-27 17:34:13.015923

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f671e76f1a39'
down_revision = '392dac5349ff'
branch_labels = None
depends_on = None


def upgrade():
    """ Create a UNSPECIFIED geography (as a country layer) as a fallback"""
    op.execute(
        "INSERT INTO geography "
        "(pcode, iso3, gis_name, gis_status, layer, hierarchy_pcode, last_modified, secondary_territory) VALUES "
        "('UNSPECIFIED', 'UNSPECIFIED', 'UNSPECIFIED', 'active', 'wrl_polbnd_int_1m_a_unhcr', 'UNSPECIFIED', '2022-01-27 17:22:38.694909', 'f') "
        "ON CONFLICT DO NOTHING"
    )
    # update all datasets to have the default UNSPECIFIED geography
    op.execute(
        "UPDATE package_extra "
        "SET value = 'UNSPECIFIED' "
        "WHERE key = 'geographies' "
        "AND (value is NULL or value = '')"
    )


def downgrade():
    op.execute("DELETE FROM geography WHERE pcode = 'UNSPECIFIED'")
    op.execute(
        "UPDATE package_extra "
        "SET value = '' "
        "WHERE key = 'geographies' "
        "AND value = 'UNSPECIFIED'"
    )
