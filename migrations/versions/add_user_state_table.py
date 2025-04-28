"""
Add UserState table for state persistence
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


# revision identifiers, used by Alembic
revision = '0004'
down_revision = '0003'  # Adjust based on your existing migration chain
branch_labels = None
depends_on = None


def upgrade():
    # Create the user_states table
    op.create_table(
        'user_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('state_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes for performance
    op.create_index(op.f('ix_user_states_id'), 'user_states', ['id'], unique=False)
    op.create_index(op.f('ix_user_states_user_id'), 'user_states', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_states_expires_at'), 'user_states', ['expires_at'], unique=False)


def downgrade():
    # Drop indexes first
    op.drop_index(op.f('ix_user_states_expires_at'), table_name='user_states')
    op.drop_index(op.f('ix_user_states_user_id'), table_name='user_states')
    op.drop_index(op.f('ix_user_states_id'), table_name='user_states')
    
    # Drop the table
    op.drop_table('user_states') 