"""add_audit_fields_to_user_address_link

Add status tracking and audit fields to user_address_link table
"""

revision = 'e8a3b4c1f5d2'
down_revision = '46fcd05dbd07'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    # Add audit and status columns to user_address_link
    op.add_column('user_address_link',
        sa.Column('status', sa.String(), nullable=False, server_default='active'))

    op.add_column('user_address_link',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))

    op.add_column('user_address_link',
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True))

    op.add_column('user_address_link',
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')))

    op.add_column('user_address_link',
        sa.Column('approved_by', postgresql.UUID(as_uuid=True), nullable=True))

    op.add_column('user_address_link',
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column('user_address_link',
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()'), onupdate=sa.text('now()')))

    op.add_column('user_address_link',
        sa.Column('notes', sa.Text(), nullable=True))

    # Add check constraint for status
    op.execute("""
        ALTER TABLE user_address_link DROP CONSTRAINT IF EXISTS role_valid;
        ALTER TABLE user_address_link ADD CONSTRAINT user_address_link_role_valid
            CHECK (role in ('buyer','viewer'));
        ALTER TABLE user_address_link ADD CONSTRAINT user_address_link_status_valid
            CHECK (status in ('pending','active','suspended','revoked'));
    """)

    # Add foreign keys
    op.create_foreign_key(
        op.f('fk_user_address_link_created_by_user'),
        'user_address_link',
        'user',
        ['created_by'],
        ['id'],
        ondelete='SET NULL'
    )

    op.create_foreign_key(
        op.f('fk_user_address_link_approved_by_user'),
        'user_address_link',
        'user',
        ['approved_by'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add indexes
    op.create_index(
        'idx_user_address_link_status',
        'user_address_link',
        ['status']
    )

    op.create_index(
        'idx_user_address_link_is_active',
        'user_address_link',
        ['is_active']
    )

    op.create_index(
        'idx_user_address_link_created_at',
        'user_address_link',
        ['created_at']
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_user_address_link_created_at', table_name='user_address_link')
    op.drop_index('idx_user_address_link_is_active', table_name='user_address_link')
    op.drop_index('idx_user_address_link_status', table_name='user_address_link')

    # Drop foreign keys
    op.drop_constraint(op.f('fk_user_address_link_approved_by_user'), 'user_address_link', type_='foreignkey')
    op.drop_constraint(op.f('fk_user_address_link_created_by_user'), 'user_address_link', type_='foreignkey')

    # Drop check constraints
    op.execute("""
        ALTER TABLE user_address_link DROP CONSTRAINT IF EXISTS user_address_link_status_valid;
        ALTER TABLE user_address_link DROP CONSTRAINT IF EXISTS user_address_link_role_valid;
        ALTER TABLE user_address_link ADD CONSTRAINT role_valid CHECK (role in ('buyer','viewer'));
    """)

    # Drop columns
    op.drop_column('user_address_link', 'notes')
    op.drop_column('user_address_link', 'updated_at')
    op.drop_column('user_address_link', 'approved_at')
    op.drop_column('user_address_link', 'approved_by')
    op.drop_column('user_address_link', 'created_at')
    op.drop_column('user_address_link', 'created_by')
    op.drop_column('user_address_link', 'is_active')
    op.drop_column('user_address_link', 'status')
