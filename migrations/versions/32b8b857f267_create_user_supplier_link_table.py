"""create_user_supplier_link_table

Creates a many-to-many relationship table between users and suppliers,
similar to user_customer_link. This allows users to be associated with
multiple suppliers and tracks their role within each supplier.
"""

revision = '32b8b857f267'
down_revision = '06f5f9908d45'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Role values for user-supplier relationships
USER_SUPPLIER_LINK_ROLE_VALUES = ('admin', 'helpdesk', 'viewer')


def upgrade() -> None:
    # Create user_supplier_link table
    op.create_table(
        'user_supplier_link',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('supplier_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'role',
            sa.String(),
            nullable=False,
            server_default=sa.text("'viewer'"),
        ),
        sa.CheckConstraint(
            "role in ('admin','helpdesk','viewer')",
            name='role_valid',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['user.id'],
            name=op.f('fk_user_supplier_link_user_id_user'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['supplier_id'],
            ['supplier.id'],
            name=op.f('fk_user_supplier_link_supplier_id_supplier'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('user_id', 'supplier_id', name=op.f('pk_user_supplier_link')),
    )

    # Create index on user_id for efficient lookups
    op.create_index(
        'idx_user_supplier_user',
        'user_supplier_link',
        ['user_id'],
        unique=False,
    )

    # Create index on supplier_id for reverse lookups
    op.create_index(
        'idx_user_supplier_supplier',
        'user_supplier_link',
        ['supplier_id'],
        unique=False,
    )


def downgrade() -> None:
    # Drop indices
    op.drop_index('idx_user_supplier_supplier', table_name='user_supplier_link')
    op.drop_index('idx_user_supplier_user', table_name='user_supplier_link')

    # Drop table
    op.drop_table('user_supplier_link')
