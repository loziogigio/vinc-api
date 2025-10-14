"""add_audit_fields_to_user_supplier_link

Add status tracking and audit fields to user_supplier_link table:
- status: Track link state (pending, active, suspended, revoked)
- is_active: Quick boolean filter
- created_by, created_at: Track who created and when
- approved_by, approved_at: Track approval workflow
- updated_at: Track last modification
- notes: Admin notes about the link
"""

revision = 'd49400943636'
down_revision = '32b8b857f267'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    # Add status enum type
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_link_status AS ENUM ('pending', 'active', 'suspended', 'revoked');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Add audit and status columns to user_supplier_link
    op.add_column('user_supplier_link',
        sa.Column('status', sa.String(), nullable=False, server_default='active'))

    op.add_column('user_supplier_link',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))

    op.add_column('user_supplier_link',
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True))

    op.add_column('user_supplier_link',
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')))

    op.add_column('user_supplier_link',
        sa.Column('approved_by', postgresql.UUID(as_uuid=True), nullable=True))

    op.add_column('user_supplier_link',
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column('user_supplier_link',
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()'), onupdate=sa.text('now()')))

    op.add_column('user_supplier_link',
        sa.Column('notes', sa.Text(), nullable=True))

    # Add check constraint for status
    op.create_check_constraint(
        'status_valid',
        'user_supplier_link',
        "status in ('pending','active','suspended','revoked')"
    )

    # Add foreign key for created_by
    op.create_foreign_key(
        op.f('fk_user_supplier_link_created_by_user'),
        'user_supplier_link',
        'user',
        ['created_by'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add foreign key for approved_by
    op.create_foreign_key(
        op.f('fk_user_supplier_link_approved_by_user'),
        'user_supplier_link',
        'user',
        ['approved_by'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add indexes for performance
    op.create_index(
        'idx_user_supplier_link_status',
        'user_supplier_link',
        ['status']
    )

    op.create_index(
        'idx_user_supplier_link_is_active',
        'user_supplier_link',
        ['is_active']
    )

    op.create_index(
        'idx_user_supplier_link_created_at',
        'user_supplier_link',
        ['created_at']
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_user_supplier_link_created_at', table_name='user_supplier_link')
    op.drop_index('idx_user_supplier_link_is_active', table_name='user_supplier_link')
    op.drop_index('idx_user_supplier_link_status', table_name='user_supplier_link')

    # Drop foreign keys
    op.drop_constraint(op.f('fk_user_supplier_link_approved_by_user'), 'user_supplier_link', type_='foreignkey')
    op.drop_constraint(op.f('fk_user_supplier_link_created_by_user'), 'user_supplier_link', type_='foreignkey')

    # Drop check constraint
    op.drop_constraint('status_valid', 'user_supplier_link', type_='check')

    # Drop columns
    op.drop_column('user_supplier_link', 'notes')
    op.drop_column('user_supplier_link', 'updated_at')
    op.drop_column('user_supplier_link', 'approved_at')
    op.drop_column('user_supplier_link', 'approved_by')
    op.drop_column('user_supplier_link', 'created_at')
    op.drop_column('user_supplier_link', 'created_by')
    op.drop_column('user_supplier_link', 'is_active')
    op.drop_column('user_supplier_link', 'status')

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS user_link_status")
