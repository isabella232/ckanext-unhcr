"""Fuzzy search with pg_trgm

Based on this tutorial: http://www.postgresonline.com/journal/archives/169-Fuzzy-string-matching-with-Trigram-and-Trigraphs.html
Allow using the % operator and the similarity function

Revision ID: 295a1905e9a6
Revises: 392dac5349ff
Create Date: 2022-02-01 21:17:45.553088

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '295a1905e9a6'
down_revision = 'f671e76f1a39'
branch_labels = None
depends_on = None


def upgrade():
    print("Adding an index for gis_name")
    op.execute("""CREATE INDEX idx_geos_trgm_gin_gis_name 
                  ON geography 
                  USING gin(gis_name gin_trgm_ops)""")

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_geos_trgm_gin_gis_name")
