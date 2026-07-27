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
#   TOPIC_PARTITIONS            Number of partitions per topic (default: 1)
#   TOPIC_REPLICAS              Replication factor per topic (default: 1)
set -euo pipefail

BOOTSTRAP="${REDPANDA_BOOTSTRAP_SERVERS:-localhost:19092}"
PARTITIONS="${TOPIC_PARTITIONS:-1}"
REPLICAS="${TOPIC_REPLICAS:-1}"

TOPICS=(
    "observations.raw"
    "observations.normalized"
    "observations.dlq"
)

if ! command -v rpk &>/dev/null; then
    echo "ERROR: rpk (Redpanda CLI) is not installed or not in PATH." >&2
    exit 1
fi

create_topic() {
    local topic="$1"
    # rpk topic create exits non-zero if the topic already exists.
    # We treat that as success (idempotent).
    if rpk topic create "${topic}" \
        --partitions "${PARTITIONS}" \
        --replicas "${REPLICAS}" \
        --bootstrap "${BOOTSTRAP}" 2>/dev/null; then
        echo "Created topic: ${topic}"
    else
        echo "Topic already exists (skipped): ${topic}"
    fi
}

echo "Creating topics on ${BOOTSTRAP} (partitions=${PARTITIONS}, replicas=${REPLICAS})..."
for topic in "${TOPICS[@]}"; do
    create_topic "${topic}"
done
echo "All topics ready."
