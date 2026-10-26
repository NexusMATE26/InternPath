"""mission_idempotency

Revision ID: e1f4c78a9d20
Revises: 8b93f9329d0a
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f4c78a9d20'
down_revision: Union[str, Sequence[str], None] = '8b93f9329d0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to include mission idempotency records table."""
    op.create_table(
        'mission_idempotency_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('payload_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('mission_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['mission_id'], ['career_missions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mission_idempotency_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mission_idempotency_records_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mission_idempotency_records_idempotency_key'), ['idempotency_key'], unique=True)
        batch_op.create_index(batch_op.f('ix_mission_idempotency_records_mission_id'), ['mission_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mission_idempotency_records_student_id'), ['student_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema by dropping mission idempotency records table."""
    with op.batch_alter_table('mission_idempotency_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mission_idempotency_records_student_id'))
        batch_op.drop_index(batch_op.f('ix_mission_idempotency_records_mission_id'))
        batch_op.drop_index(batch_op.f('ix_mission_idempotency_records_idempotency_key'))
        batch_op.drop_index(batch_op.f('ix_mission_idempotency_records_id'))
    op.drop_table('mission_idempotency_records')
