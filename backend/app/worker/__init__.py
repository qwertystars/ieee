"""Worker package — dedicated Kafka consumer process.

Runs ConsumerManager in its own container, consuming from
`observations.normalized` and persisting observations to PostgreSQL.
"""
