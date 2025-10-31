from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        id_col = postgresql.UUID(as_uuid=True)
    else:
        id_col = sa.String(36)

    op.create_table(
        'molecules',
        sa.Column('id', id_col, primary_key=True),
        sa.Column('smiles', sa.String(length=4096), nullable=False, unique=True),
    )


def downgrade() -> None:
    op.drop_table('molecules')

