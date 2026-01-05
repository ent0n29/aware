package com.polybot.hft.events.payload;

import java.math.BigDecimal;
import java.time.Instant;

public record MarketTradeEvent(
    String market,
    String assetId,
    BigDecimal price,
    BigDecimal size,
    String side,
    Long feeRateBps,
    String transactionHash,
    Instant tradeAt,
    Instant capturedAt
) {
}

