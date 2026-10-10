#!/usr/bin/env bash
# create_topics.sh — Create Kafka/Redpanda topics for the disaster pipeline.
#
# Idempotent: safe to re-run. Topics that already exist are skipped.
# Creates: observations.raw, observations.normalized, observations.dlq
#
# Usage:
#   ./scripts/create_topics.sh
#   REDPANDA_BOOTSTRAP_SERVERS=redpanda:9092 ./scripts/create_topics.sh
#
# Environment variables:
#   REDPANDA_BOOTSTRAP_SERVERS  Kafka bootstrap servers (default: localhost:19092)
#   TOPIC_PARTITIONS            Number of partitions per topic (default: 6)
#   TOPIC_REPLICAS              Replication factor per topic (default: 1)
set -euo pipefail

BOOTSTRAP="${REDPANDA_BOOTSTRAP_SERVERS:-localhost:19092}"
PARTITIONS="${TOPIC_PARTITIONS:-6}"
REPLICAS="${TOPIC_REPLICAS:-1}"
DLQ_RETENTION_DAYS="${DLQ_RETENTION_DAYS:-30}"
DLQ_RETENTION_MS=$((DLQ_RETENTION_DAYS * 24 * 60 * 60 * 1000))

TOPICS=(
    "observations.raw"
    "observations.normalized"
    "observations.dlq"
)

# rpk in the redpanda container auto-discovers the broker via the config file.
# Host-installed rpk needs REDPANDA_BROKERS env var or a profile to find the broker.
# The --bootstrap flag was removed in newer rpk versions; use env var instead.
if command -v rpk &>/dev/null; then
    RPK_CMD=(env REDPANDA_BROKERS="${BOOTSTRAP}" rpk)
elif docker compose exec -T redpanda rpk version >/dev/null 2>&1; then
    RPK_CMD=(docker compose exec -T redpanda rpk)
else
    echo "ERROR: rpk is not installed on the host and redpanda container is not running." >&2
    echo "       Install rpk or start redpanda: docker compose up -d redpanda" >&2
    exit 1
fi

create_topic() {
    local topic="$1"
    # rpk topic create exits non-zero if the topic already exists.
    # We treat that as success (idempotent).
    local config_args=()
    if [[ "${topic}" == "observations.dlq" ]]; then
        config_args+=(--config "retention.ms=${DLQ_RETENTION_MS}")
    fi
    if "${RPK_CMD[@]}" topic create "${topic}" \
        --partitions "${PARTITIONS}" \
        --replicas "${REPLICAS}" "${config_args[@]}" 2>&1; then
        echo "Created topic: ${topic}"
    else
        if [[ "${topic}" == "observations.dlq" ]] && "${RPK_CMD[@]}" topic alter-config "${topic}" --set "retention.ms=${DLQ_RETENTION_MS}" 2>&1; then
            echo "Topic already exists; configured DLQ retention: ${DLQ_RETENTION_DAYS} days"
        else
            echo "Topic already exists; DLQ retention provisioning is DEFERRED_EXTERNAL" >&2
        fi
    fi
}

echo "Creating topics (partitions=${PARTITIONS}, replicas=${REPLICAS})..."
for topic in "${TOPICS[@]}"; do
    create_topic "${topic}"
done
echo "All topics ready."
