"""Streaming module — async Kafka producer and consumer for Redpanda.

ProducerManager: async producer writing JSON messages to Redpanda topics.
ConsumerManager: async consumer reading observations.normalized → PostgreSQL.
"""

from app.streaming.consumer import ConsumerManager
from app.streaming.producer import ProducerManager

__all__ = ["ConsumerManager", "ProducerManager"]
