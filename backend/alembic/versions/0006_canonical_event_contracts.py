import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    event_columns = (
        ("event_type", sa.String(), True),
        ("source_id", sa.String(), True),
        ("external_id", sa.String(), True),
        ("source_time_ms", sa.BigInteger(), True),
        ("receipt_time_ms", sa.BigInteger(), True),
        ("sequence", sa.BigInteger(), True),
        ("payload", JSONB(), True),
        ("provenance", JSONB(), True),
        ("visibility", sa.String(), True),
        ("review_status", sa.String(), True),
        ("schema_version", sa.String(), True),
        ("serialization_version", sa.String(), True),
    )
    for name, column_type, nullable in event_columns:
        op.add_column("events", sa.Column(name, column_type, nullable=nullable))
    op.execute(
        sa.text(
            "UPDATE events SET sequence = ranked.sequence, "
            "serialization_version = 'legacy-v1' "
            "FROM (SELECT id, row_number() OVER (PARTITION BY org_id ORDER BY ts, id) AS sequence "
            "FROM events) AS ranked WHERE events.id = ranked.id"
        )
    )
    op.execute(sa.text("UPDATE events SET schema_version = '1.0' WHERE schema_version IS NULL"))
    op.execute(sa.text("UPDATE events SET event_type = 'audit' WHERE event_type IS NULL"))
    op.execute(sa.text("UPDATE events SET source_id = actor WHERE source_id IS NULL"))
    op.execute(sa.text("UPDATE events SET source_time_ms = ts WHERE source_time_ms IS NULL"))
    op.execute(sa.text("UPDATE events SET receipt_time_ms = ts WHERE receipt_time_ms IS NULL"))
    op.execute(sa.text("UPDATE events SET visibility = 'internal' WHERE visibility IS NULL"))
    op.execute(sa.text("UPDATE events SET review_status = 'official' WHERE review_status IS NULL"))
    op.alter_column("events", "sequence", nullable=False)
    op.alter_column("events", "serialization_version", nullable=False)
    op.create_index("ix_events_org_sequence", "events", ["org_id", "sequence"])
    op.create_unique_constraint("uq_events_org_sequence", "events", ["org_id", "sequence"])

    observation_columns = (
        ("raw_event_id", sa.String(26)),
        ("source_time_ms", sa.BigInteger()),
        ("receipt_time_ms", sa.BigInteger()),
        ("sequence", sa.BigInteger()),
        ("payload_hash", sa.String(71)),
        ("provenance", JSONB()),
        ("visibility", sa.String()),
        ("review_status", sa.String()),
        ("schema_version", sa.String()),
    )
    for name, column_type in observation_columns:
        op.add_column("observations", sa.Column(name, column_type, nullable=True))
    op.create_index(
        "ix_observations_org_source_sequence",
        "observations",
        ["org_id", "source_id", "sequence"],
    )

    op.add_column("idempotency_keys", sa.Column("org_id", sa.String(), nullable=True))
    op.add_column("idempotency_keys", sa.Column("incident_id", sa.String(), nullable=True))
    op.add_column("idempotency_keys", sa.Column("request_hash", sa.String(64), nullable=True))
    op.add_column("idempotency_keys", sa.Column("payload", JSONB(), nullable=True))
    op.add_column("idempotency_keys", sa.Column("schema_version", sa.String(), nullable=True))
    op.execute(sa.text("UPDATE idempotency_keys SET org_id = '', incident_id = '', schema_version = '1.0'"))
    op.alter_column("idempotency_keys", "org_id", nullable=False)
    op.alter_column("idempotency_keys", "incident_id", nullable=False)
    op.alter_column("idempotency_keys", "schema_version", nullable=False)
    op.drop_constraint("uq_idempotency_source_external", "idempotency_keys", type_="unique")
    op.create_unique_constraint(
        "uq_idempotency_org_source_external",
        "idempotency_keys",
        ["org_id", "source", "external_id"],
    )

    op.create_table(
        "raw_events",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("incident_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("source_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("receipt_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("provenance", JSONB(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("review_status", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("canonical_hash", sa.String(71), nullable=False),
        sa.UniqueConstraint("org_id", "source_id", "external_id", name="uq_raw_events_source_external"),
    )
    op.create_index("ix_raw_events_org_incident", "raw_events", ["org_id", "incident_id"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("incident_id", sa.String(), nullable=False),
        sa.Column("source_event_ids", JSONB(), nullable=False),
        sa.Column("source_observation_ids", JSONB(), nullable=False),
        sa.Column("generated_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("valid_from_ms", sa.BigInteger(), nullable=False),
        sa.Column("valid_until_ms", sa.BigInteger(), nullable=True),
        sa.Column("output", JSONB(), nullable=False),
        sa.Column("provenance", JSONB(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("review_status", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("canonical_hash", sa.String(71), nullable=False),
    )
    op.create_index("ix_predictions_org_incident", "predictions", ["org_id", "incident_id"])

    op.create_table(
        "canonical_decisions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("incident_id", sa.String(), nullable=False),
        sa.Column("input_event_ids", JSONB(), nullable=False),
        sa.Column("input_observation_ids", JSONB(), nullable=False),
        sa.Column("prediction_ids", JSONB(), nullable=False),
        sa.Column("decision_type", sa.String(), nullable=False),
        sa.Column("decision", JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("decided_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("provenance", JSONB(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("review_status", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("canonical_hash", sa.String(71), nullable=False),
    )
    op.create_index(
        "ix_canonical_decisions_org_incident",
        "canonical_decisions",
        ["org_id", "incident_id"],
    )

    op.create_table(
        "audit_chain_heads",
        sa.Column("org_id", sa.String(), primary_key=True),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_hash", sa.String(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.execute(
        sa.text(
            "INSERT INTO audit_chain_heads (org_id, last_sequence, last_hash, updated_at) "
            "SELECT org_id, max(sequence), (array_agg(hash ORDER BY sequence DESC))[1], "
            "max(ts) FROM events GROUP BY org_id"
        )
    )


def downgrade() -> None:
    raise RuntimeError("0006 is irreversible: refusing to delete canonical event data")
