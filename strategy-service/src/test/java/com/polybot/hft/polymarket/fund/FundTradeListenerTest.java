package com.polybot.hft.polymarket.fund;

import com.polybot.hft.config.HftProperties;
import com.polybot.hft.polymarket.fund.config.FundConfig;
import com.polybot.hft.polymarket.fund.model.IndexConstituent;
import com.polybot.hft.polymarket.fund.model.TraderSignal;
import com.polybot.hft.polymarket.fund.service.FundPositionMirror;
import com.polybot.hft.polymarket.fund.service.FundTradeListener;
import com.polybot.hft.polymarket.fund.service.IndexWeightProvider;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

/**
 * Unit tests for FundTradeListener.
 *
 * Tests the trade polling and signal generation logic for PSI index funds.
 */
@ExtendWith(MockitoExtension.class)
class FundTradeListenerTest {

    @Mock
    private IndexWeightProvider weightProvider;

    @Mock
    private FundPositionMirror positionMirror;

    @Mock
    private JdbcTemplate jdbcTemplate;

    private Clock fixedClock;
    private FundConfig config;
    private FundTradeListener listener;
    private SimpleMeterRegistry meterRegistry;

    private static final Instant NOW = Instant.parse("2024-01-15T10:00:00Z");
    private static final String PSI_10 = "PSI-10";

    @BeforeEach
    void setUp() {
        fixedClock = Clock.fixed(NOW, ZoneId.of("UTC"));
        meterRegistry = new SimpleMeterRegistry();
        config = new FundConfig(
                true,                    // enabled
                PSI_10,                  // indexType
                BigDecimal.valueOf(10000), // capitalUsd
                0.10,                    // maxPositionPct
                BigDecimal.valueOf(5),   // minTradeUsd
                5,                       // signalDelaySeconds
                0.02,                    // maxSlippagePct
                HftProperties.FundExecutionMode.LIMIT_THEN_MARKET,
                FundConfig.RiskLimits.defaults()
        );
        listener = new FundTradeListener(config, weightProvider, positionMirror, jdbcTemplate, fixedClock, meterRegistry);
    }

    @Test
    void shouldGenerateSignalWhenPSI10TraderTrades() {
        // Given: PSI-10 index contains trader with address "0x123"
        IndexConstituent constituent = createConstituent("alice", "0x123", 0.15);
        when(weightProvider.getConstituents(PSI_10)).thenReturn(List.of(constituent));

        // Mock ClickHouse returning a trade from "0x123"
        mockTradeQuery(List.of(createMockTrade("0x123", "alice", "BUY", "btc-100k", 1000, 0.55)));

        // When: Poll for trades
        listener.pollForTrades();

        // Then: Signal is generated and queued
        ArgumentCaptor<TraderSignal> signalCaptor = ArgumentCaptor.forClass(TraderSignal.class);
        verify(positionMirror, times(1)).queueSignal(signalCaptor.capture());

        TraderSignal signal = signalCaptor.getValue();
        assertThat(signal.username()).isEqualTo("alice");
        assertThat(signal.type()).isEqualTo(TraderSignal.SignalType.BUY);
        assertThat(signal.marketSlug()).isEqualTo("btc-100k");
        assertThat(signal.shares()).isEqualByComparingTo(BigDecimal.valueOf(1000));
        assertThat(signal.traderWeight()).isEqualTo(0.15);
    }

    @Test
    void shouldNotGenerateSignalForNonIndexedTrader() {
        // Given: PSI-10 index contains only trader "alice" with address "0x123"
        IndexConstituent constituent = createConstituent("alice", "0x123", 0.15);
        when(weightProvider.getConstituents(PSI_10)).thenReturn(List.of(constituent));

        // Mock ClickHouse returning a trade from non-indexed address "0x999"
        mockTradeQuery(List.of(createMockTrade("0x999", "bob", "BUY", "eth-10k", 500, 0.60)));

        // When: Poll for trades
        listener.pollForTrades();

        // Then: No signal generated (trader not in index)
        verify(positionMirror, never()).queueSignal(any());
    }

    @Test
    void shouldDeduplicateTradesFromSameTrader() {
        // Given: PSI-10 index contains trader "alice"
        IndexConstituent constituent = createConstituent("alice", "0x123", 0.15);
        when(weightProvider.getConstituents(PSI_10)).thenReturn(List.of(constituent));

        // First poll - trade at T
        Instant tradeTime = NOW.minusSeconds(5);
        mockTradeQuery(List.of(createMockTradeWithTimestamp("0x123", "alice", "BUY", "btc-100k", 1000, 0.55, tradeTime)));

        listener.pollForTrades();
        verify(positionMirror, times(1)).queueSignal(any());
        reset(positionMirror);

        // Second poll - same trade polled again (same timestamp)
        mockTradeQuery(List.of(createMockTradeWithTimestamp("0x123", "alice", "BUY", "btc-100k", 1000, 0.55, tradeTime)));

        // When: Poll again
        listener.pollForTrades();

        // Then: No duplicate signal (trade already processed)
        verify(positionMirror, never()).queueSignal(any());
    }

    @Test
    void shouldHandleEmptyIndexGracefully() {
        // Given: No constituents in index
        when(weightProvider.getConstituents(PSI_10)).thenReturn(List.of());

        // When: Poll for trades
        listener.pollForTrades();

        // Then: No error, no queries, no signals
        verify(jdbcTemplate, never()).query(anyString(), any(RowMapper.class));
        verify(positionMirror, never()).queueSignal(any());
    }

    @Test
    void shouldNotPollWhenDisabled() {
        // Given: Fund is disabled
        FundConfig disabledConfig = new FundConfig(
                false,  // disabled
                PSI_10,
                BigDecimal.valueOf(10000),
                0.10,
                BigDecimal.valueOf(5),
                5,
                0.02,
                HftProperties.FundExecutionMode.LIMIT_THEN_MARKET,
                FundConfig.RiskLimits.defaults()
        );
        FundTradeListener disabledListener = new FundTradeListener(
                disabledConfig, weightProvider, positionMirror, jdbcTemplate, fixedClock, meterRegistry);

        // When: Poll for trades
        disabledListener.pollForTrades();

        // Then: No queries made
        verify(weightProvider, never()).getConstituents(any());
        verify(jdbcTemplate, never()).query(anyString(), any(RowMapper.class));
        verify(positionMirror, never()).queueSignal(any());
    }

    @Test
    void shouldGenerateSellSignalForSellTrades() {
        // Given: PSI-10 index contains trader "alice"
        IndexConstituent constituent = createConstituent("alice", "0x123", 0.15);
        when(weightProvider.getConstituents(PSI_10)).thenReturn(List.of(constituent));

        // Mock ClickHouse returning a SELL trade
        mockTradeQuery(List.of(createMockTrade("0x123", "alice", "SELL", "btc-100k", 500, 0.70)));

        // When: Poll for trades
        listener.pollForTrades();

        // Then: SELL signal is generated
        ArgumentCaptor<TraderSignal> signalCaptor = ArgumentCaptor.forClass(TraderSignal.class);
        verify(positionMirror, times(1)).queueSignal(signalCaptor.capture());

        TraderSignal signal = signalCaptor.getValue();
        assertThat(signal.type()).isEqualTo(TraderSignal.SignalType.SELL);
    }

    @Test
    void shouldProcessMultipleTradesFromDifferentTraders() {
        // Given: PSI-10 index contains two traders
        IndexConstituent alice = createConstituent("alice", "0x123", 0.15);
        IndexConstituent bob = createConstituent("bob", "0x456", 0.10);
        when(weightProvider.getConstituents(PSI_10)).thenReturn(List.of(alice, bob));

        // Mock ClickHouse returning trades from both
        mockTradeQuery(List.of(
                createMockTrade("0x123", "alice", "BUY", "btc-100k", 1000, 0.55),
                createMockTrade("0x456", "bob", "BUY", "eth-10k", 500, 0.40)
        ));

        // When: Poll for trades
        listener.pollForTrades();

        // Then: Two signals generated
        verify(positionMirror, times(2)).queueSignal(any());
    }

    @Test
    void shouldReportMetricsCorrectly() {
        // Given: PSI-10 index contains trader "alice"
        IndexConstituent constituent = createConstituent("alice", "0x123", 0.15);
        when(weightProvider.getConstituents(PSI_10)).thenReturn(List.of(constituent));
        mockTradeQuery(List.of(createMockTrade("0x123", "alice", "BUY", "btc-100k", 1000, 0.55)));

        // When: Poll for trades
        listener.pollForTrades();

        // Then: Metrics are updated
        Map<String, Object> metrics = listener.getMetrics();
        assertThat(metrics.get("tradesProcessed")).isEqualTo(1L);
        assertThat(metrics.get("signalsGenerated")).isEqualTo(1L);
        assertThat(metrics.get("trackedTraders")).isEqualTo(1);
    }

    // ========== Helper Methods ==========

    private IndexConstituent createConstituent(String username, String proxyAddress, double weight) {
        return new IndexConstituent(
                username,
                proxyAddress,
                weight,
                1,  // rank
                BigDecimal.valueOf(100000),  // estimatedCapitalUsd
                85.0,  // smartMoneyScore
                "DIRECTIONAL",  // strategyType
                NOW.minusSeconds(3600),  // lastTradeAt
                NOW.minus(Duration.ofDays(30))  // indexedAt
        );
    }

    private MockTrade createMockTrade(String proxyAddress, String username, String side,
                                       String marketSlug, double size, double price) {
        return createMockTradeWithTimestamp(proxyAddress, username, side, marketSlug, size, price, NOW.minusSeconds(2));
    }

    private MockTrade createMockTradeWithTimestamp(String proxyAddress, String username, String side,
                                                    String marketSlug, double size, double price, Instant ts) {
        return new MockTrade(
                ts,
                "trade-" + System.nanoTime(),
                username,
                proxyAddress,
                marketSlug,
                "token-" + marketSlug,
                side,
                "Yes",
                price,
                size,
                size * price
        );
    }

    @SuppressWarnings("unchecked")
    private void mockTradeQuery(List<MockTrade> trades) {
        when(jdbcTemplate.query(anyString(), any(RowMapper.class))).thenAnswer(invocation -> {
            RowMapper<Object> mapper = invocation.getArgument(1);
            return trades.stream()
                    .map(t -> {
                        try {
                            ResultSet rs = mock(ResultSet.class);
                            when(rs.getTimestamp("ts")).thenReturn(Timestamp.from(t.ts));
                            when(rs.getString("trade_id")).thenReturn(t.tradeId);
                            when(rs.getString("username")).thenReturn(t.username);
                            when(rs.getString("proxy_address")).thenReturn(t.proxyAddress);
                            when(rs.getString("market_slug")).thenReturn(t.marketSlug);
                            when(rs.getString("token_id")).thenReturn(t.tokenId);
                            when(rs.getString("side")).thenReturn(t.side);
                            when(rs.getString("outcome")).thenReturn(t.outcome);
                            when(rs.getDouble("price")).thenReturn(t.price);
                            when(rs.getDouble("size")).thenReturn(t.size);
                            when(rs.getDouble("notional")).thenReturn(t.notional);
                            return mapper.mapRow(rs, 0);
                        } catch (SQLException e) {
                            throw new RuntimeException(e);
                        }
                    })
                    .toList();
        });
    }

    private record MockTrade(
            Instant ts,
            String tradeId,
            String username,
            String proxyAddress,
            String marketSlug,
            String tokenId,
            String side,
            String outcome,
            double price,
            double size,
            double notional
    ) {}
}
