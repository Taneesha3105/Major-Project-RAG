"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-19 23:14:01.084569
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector (embeddings) and pg_trgm. Creating `vector` needs superuser the first time; see README.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table('users',
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('admin', 'deal_lead', 'analyst', 'viewer', name='userrole', native_enum=False, length=32), nullable=False),
    sa.Column('job_title', sa.String(length=120), nullable=True),
    sa.Column('organization', sa.String(length=160), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('deals',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('code_name', sa.String(length=60), nullable=True),
    sa.Column('deal_type', sa.Enum('acquisition', 'merger', 'asset_purchase', 'joint_venture', 'divestiture', name='dealtype', native_enum=False, length=32), nullable=False),
    sa.Column('stage', sa.Enum('screening', 'loi', 'due_diligence', 'negotiation', 'closing', 'closed', 'terminated', name='dealstage', native_enum=False, length=32), nullable=False),
    sa.Column('acquirer_name', sa.String(length=160), nullable=False),
    sa.Column('target_name', sa.String(length=160), nullable=False),
    sa.Column('target_industry', sa.String(length=120), nullable=True),
    sa.Column('target_country', sa.String(length=80), nullable=True),
    sa.Column('deal_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('expected_close_date', sa.Date(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('executive_summary', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_deals_created_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deals'))
    )
    op.create_index(op.f('ix_deals_stage'), 'deals', ['stage'], unique=False)
    op.create_table('analysis_runs',
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('triggered_by_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Enum('queued', 'running', 'completed', 'failed', name='analysisstatus', native_enum=False, length=32), nullable=False),
    sa.Column('categories', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('progress', sa.Integer(), nullable=False),
    sa.Column('findings_count', sa.Integer(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_analysis_runs_deal_id_deals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['triggered_by_id'], ['users.id'], name=op.f('fk_analysis_runs_triggered_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_runs'))
    )
    op.create_index(op.f('ix_analysis_runs_deal_id'), 'analysis_runs', ['deal_id'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('summary', sa.String(length=500), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_audit_logs_deal_id_deals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_audit_logs_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_deal_id'), 'audit_logs', ['deal_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_table('checklist_items',
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('category', sa.Enum('financial', 'legal', 'tax', 'contracts', 'hr', 'intellectual_property', 'regulatory', 'operational', 'commercial', 'it', 'environmental', 'corporate', 'other', name='documentcategory', native_enum=False, length=32), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('pending', 'in_progress', 'completed', 'flagged', 'not_applicable', name='checkliststatus', native_enum=False, length=32), nullable=False),
    sa.Column('priority', sa.Enum('low', 'medium', 'high', name='priority', native_enum=False, length=32), nullable=False),
    sa.Column('assignee_id', sa.UUID(), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('ai_coverage', sa.Enum('found', 'partial', 'missing', name='evidencecoverage', native_enum=False, length=32), nullable=True),
    sa.Column('ai_note', sa.Text(), nullable=True),
    sa.Column('ai_citations', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('ai_reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], name=op.f('fk_checklist_items_assignee_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_checklist_items_deal_id_deals'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_checklist_items'))
    )
    op.create_index(op.f('ix_checklist_items_deal_id'), 'checklist_items', ['deal_id'], unique=False)
    op.create_table('conversations',
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_conversations_deal_id_deals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_conversations_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index(op.f('ix_conversations_deal_id'), 'conversations', ['deal_id'], unique=False)
    op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False)
    op.create_table('deal_members',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('member_role', sa.Enum('lead', 'member', 'observer', name='dealmemberrole', native_enum=False, length=32), nullable=False),
    sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_deal_members_deal_id_deals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_deal_members_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deal_members')),
    sa.UniqueConstraint('deal_id', 'user_id', name='uq_deal_members_deal_user')
    )
    op.create_index(op.f('ix_deal_members_deal_id'), 'deal_members', ['deal_id'], unique=False)
    op.create_index(op.f('ix_deal_members_user_id'), 'deal_members', ['user_id'], unique=False)
    op.create_table('documents',
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('uploaded_by_id', sa.UUID(), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('mime_type', sa.String(length=120), nullable=True),
    sa.Column('file_extension', sa.String(length=12), nullable=False),
    sa.Column('file_size', sa.BigInteger(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('category', sa.Enum('financial', 'legal', 'tax', 'contracts', 'hr', 'intellectual_property', 'regulatory', 'operational', 'commercial', 'it', 'environmental', 'corporate', 'other', name='documentcategory', native_enum=False, length=32), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('queued', 'processing', 'ready', 'failed', name='documentstatus', native_enum=False, length=32), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.Column('char_count', sa.Integer(), nullable=False),
    sa.Column('ocr_applied', sa.Boolean(), nullable=False),
    sa.Column('ocr_page_count', sa.Integer(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('key_facts', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('processing_ms', sa.Integer(), nullable=True),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_documents_deal_id_deals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], name=op.f('fk_documents_uploaded_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents')),
    sa.UniqueConstraint('deal_id', 'content_hash', name='uq_documents_deal_hash')
    )
    op.create_index(op.f('ix_documents_category'), 'documents', ['category'], unique=False)
    op.create_index(op.f('ix_documents_deal_id'), 'documents', ['deal_id'], unique=False)
    op.create_index(op.f('ix_documents_status'), 'documents', ['status'], unique=False)
    op.create_table('document_chunks',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('section', sa.String(length=300), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('char_count', sa.Integer(), nullable=False),
    sa.Column('is_ocr', sa.Boolean(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("setweight(to_tsvector('english', coalesce(section, '')), 'A') || setweight(to_tsvector('english', coalesce(content, '')), 'B')", persisted=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_document_chunks_deal_id_deals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_chunks_document_id_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_chunks')),
    sa.UniqueConstraint('document_id', 'chunk_index', name='uq_document_chunks_doc_index')
    )
    op.create_index(op.f('ix_document_chunks_deal_id'), 'document_chunks', ['deal_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.create_index('ix_document_chunks_embedding_hnsw', 'document_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_document_chunks_search_vector', 'document_chunks', ['search_vector'], unique=False, postgresql_using='gin')
    op.create_table('messages',
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.Enum('user', 'assistant', name='messagerole', native_enum=False, length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('citations', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('retrieval_meta', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('feedback', sa.SmallInteger(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_table('risk_findings',
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('analysis_run_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('category', sa.Enum('financial', 'legal', 'tax', 'contracts', 'hr', 'intellectual_property', 'regulatory', 'operational', 'commercial', 'it', 'environmental', 'corporate', 'other', name='documentcategory', native_enum=False, length=32), nullable=False),
    sa.Column('finding_type', sa.Enum('risk', 'contradiction', 'missing_information', 'opportunity', name='findingtype', native_enum=False, length=32), nullable=False),
    sa.Column('severity', sa.Enum('low', 'medium', 'high', 'critical', name='severity', native_enum=False, length=32), nullable=False),
    sa.Column('status', sa.Enum('open', 'under_review', 'mitigated', 'accepted', 'dismissed', name='findingstatus', native_enum=False, length=32), nullable=False),
    sa.Column('source', sa.Enum('ai', 'manual', name='findingsource', native_enum=False, length=32), nullable=False),
    sa.Column('recommendation', sa.Text(), nullable=True),
    sa.Column('financial_impact', sa.String(length=255), nullable=True),
    sa.Column('citations', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('resolution_note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], name=op.f('fk_risk_findings_analysis_run_id_analysis_runs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_risk_findings_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_risk_findings_deal_id_deals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_risk_findings_owner_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_findings'))
    )
    op.create_index(op.f('ix_risk_findings_analysis_run_id'), 'risk_findings', ['analysis_run_id'], unique=False)
    op.create_index(op.f('ix_risk_findings_deal_id'), 'risk_findings', ['deal_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_risk_findings_deal_id'), table_name='risk_findings')
    op.drop_index(op.f('ix_risk_findings_analysis_run_id'), table_name='risk_findings')
    op.drop_table('risk_findings')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_document_chunks_search_vector', table_name='document_chunks', postgresql_using='gin')
    op.drop_index('ix_document_chunks_embedding_hnsw', table_name='document_chunks', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_deal_id'), table_name='document_chunks')
    op.drop_table('document_chunks')
    op.drop_index(op.f('ix_documents_status'), table_name='documents')
    op.drop_index(op.f('ix_documents_deal_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_category'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_deal_members_user_id'), table_name='deal_members')
    op.drop_index(op.f('ix_deal_members_deal_id'), table_name='deal_members')
    op.drop_table('deal_members')
    op.drop_index(op.f('ix_conversations_user_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_deal_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_checklist_items_deal_id'), table_name='checklist_items')
    op.drop_table('checklist_items')
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_deal_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_analysis_runs_deal_id'), table_name='analysis_runs')
    op.drop_table('analysis_runs')
    op.drop_index(op.f('ix_deals_stage'), table_name='deals')
    op.drop_table('deals')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
