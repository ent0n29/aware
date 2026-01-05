-- Market WS trade prints (continuous, low-latency).
--
-- Produced by polybot-core's ClobMarketWebSocketClient as event type: market_ws.trade
-- This is the preferred trade tape for simulator fill modeling vs the laggier REST/Data-API paths.

CREATE TABLE IF NOT EXISTS polybot.market_ws_trades (
  ts DateTime64(3),
  captured_at DateTime64(3),
  market_id String,
  asset_id String,
  side LowCardinality(String),
  price Float64,
  size Float64,
  fee_rate_bps Int64,
  transaction_hash String,
  event_key String,
  ingested_at DateTime64(3),
  kafka_partition Int32,
  kafka_offset Int64,
  kafka_timestamp DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toDate(ts)
ORDER BY (asset_id, ts, event_key);

CREATE MATERIALIZED VIEW IF NOT EXISTS polybot.market_ws_trades_mv
TO polybot.market_ws_trades
AS
SELECT
  ts,
  ifNull(parseDateTime64BestEffortOrNull(JSONExtractString(data, 'capturedAt')), ts) AS captured_at,
  JSONExtractString(data, 'market') AS market_id,
  JSONExtractString(data, 'assetId') AS asset_id,
  upper(ifNull(JSONExtractString(data, 'side'), '')) AS side,
  JSONExtractFloat(data, 'price') AS price,
  JSONExtractFloat(data, 'size') AS size,
  toInt64OrZero(JSONExtractString(data, 'feeRateBps')) AS fee_rate_bps,
  JSONExtractString(data, 'transactionHash') AS transaction_hash,
  kafka_key AS event_key,
  ingested_at,
  kafka_partition,
  kafka_offset,
  kafka_timestamp
FROM polybot.analytics_events
WHERE type = 'market_ws.trade';

