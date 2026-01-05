package com.polybot.hft.polymarket.fund;

import com.polybot.hft.polymarket.fund.model.IndexConstituent;
import com.polybot.hft.polymarket.fund.service.IndexWeightProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

/**
 * Unit tests for IndexWeightProvider.
 *
 * Tests the index constituent loading, caching, and weight retrieval logic.
 */
@ExtendWith(MockitoExtension.class)
class IndexWeightProviderTest {

    @Mock
    private JdbcTemplate jdbcTemplate;

    private IndexWeightProvider provider;

    private static final String PSI_10 = "PSI-10";
    private static final String PSI_SPORTS = "PSI-SPORTS";
    private static final Instant NOW = Instant.now();

    @BeforeEach
    void setUp() {
        provider = new IndexWeightProvider(jdbcTemplate);
    }

    @Test
    void shouldLoadConstituentsFromClickHouse() {
        // Given: Mocked JdbcTemplate returning test data
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0x123", 0.30, 1),
                createConstituent("bob", "0x456", 0.25, 2),
                createConstituent("charlie", "0x789", 0.20, 3)
        );
        mockClickHouseQuery(mockConstituents);

        // When: getConstituents("PSI-10")
        List<IndexConstituent> constituents = provider.getConstituents(PSI_10);

        // Then: Returns list of constituents with weights
        assertThat(constituents).hasSize(3);
        assertThat(constituents.get(0).username()).isEqualTo("alice");
        assertThat(constituents.get(0).weight()).isEqualTo(0.30);
        assertThat(constituents.get(1).username()).isEqualTo("bob");
        assertThat(constituents.get(2).username()).isEqualTo("charlie");
    }

    @Test
    void shouldCacheConstituentsWithTTL() {
        // Given: Cache is empty
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0x123", 0.30, 1)
        );
        mockClickHouseQuery(mockConstituents);

        // When: Call getConstituents twice within TTL (immediate second call)
        provider.getConstituents(PSI_10);
        provider.getConstituents(PSI_10);

        // Then: Only one query to ClickHouse
        verify(jdbcTemplate, times(1)).query(anyString(), any(RowMapper.class), eq(PSI_10));
    }

    @Test
    void shouldReturnCachedDataOnSubsequentCalls() {
        // Given: First call populates cache
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0x123", 0.30, 1)
        );
        mockClickHouseQuery(mockConstituents);

        // When: Multiple calls within TTL
        List<IndexConstituent> first = provider.getConstituents(PSI_10);
        List<IndexConstituent> second = provider.getConstituents(PSI_10);
        List<IndexConstituent> third = provider.getConstituents(PSI_10);

        // Then: All return same data, single query executed
        assertThat(first).isEqualTo(second);
        assertThat(second).isEqualTo(third);
        verify(jdbcTemplate, times(1)).query(anyString(), any(RowMapper.class), eq(PSI_10));
    }

    @Test
    void shouldMaintainSeparateCachesPerIndex() {
        // Given: Different indices
        List<IndexConstituent> psi10Constituents = List.of(
                createConstituent("alice", "0x123", 0.30, 1)
        );
        List<IndexConstituent> psiSportsConstituents = List.of(
                createConstituent("bob", "0x456", 0.40, 1)
        );

        // Mock different responses per index
        when(jdbcTemplate.query(anyString(), any(RowMapper.class), eq(PSI_10)))
                .thenReturn(psi10Constituents);
        when(jdbcTemplate.query(anyString(), any(RowMapper.class), eq(PSI_SPORTS)))
                .thenReturn(psiSportsConstituents);

        // When: Query both indices
        List<IndexConstituent> psi10Result = provider.getConstituents(PSI_10);
        List<IndexConstituent> sportsResult = provider.getConstituents(PSI_SPORTS);

        // Then: Each index has its own constituents
        assertThat(psi10Result.get(0).username()).isEqualTo("alice");
        assertThat(sportsResult.get(0).username()).isEqualTo("bob");

        // And both queries were made
        verify(jdbcTemplate).query(anyString(), any(RowMapper.class), eq(PSI_10));
        verify(jdbcTemplate).query(anyString(), any(RowMapper.class), eq(PSI_SPORTS));
    }

    @Test
    void shouldReturnCorrectWeight() {
        // Given: Trader "alice" has weight 0.15 in PSI-10
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0x123", 0.15, 1),
                createConstituent("bob", "0x456", 0.10, 2)
        );
        mockClickHouseQuery(mockConstituents);

        // When: getWeight("PSI-10", "alice")
        double weight = provider.getWeight(PSI_10, "alice");

        // Then: Returns 0.15
        assertThat(weight).isEqualTo(0.15);
    }

    @Test
    void shouldReturnZeroWeightForNonExistentTrader() {
        // Given: Index contains only "alice"
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0x123", 0.15, 1)
        );
        mockClickHouseQuery(mockConstituents);

        // When: getWeight for non-existent trader
        double weight = provider.getWeight(PSI_10, "unknown");

        // Then: Returns 0.0
        assertThat(weight).isEqualTo(0.0);
    }

    @Test
    void shouldGetConstituentByUsername() {
        // Given: Index contains multiple traders
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0x123", 0.30, 1),
                createConstituent("bob", "0x456", 0.25, 2)
        );
        mockClickHouseQuery(mockConstituents);

        // When: getConstituent by username
        Optional<IndexConstituent> result = provider.getConstituent(PSI_10, "bob");

        // Then: Returns correct constituent
        assertThat(result).isPresent();
        assertThat(result.get().username()).isEqualTo("bob");
        assertThat(result.get().weight()).isEqualTo(0.25);
    }

    @Test
    void shouldGetConstituentByAddress() {
        // Given: Index contains multiple traders
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0x123", 0.30, 1),
                createConstituent("bob", "0x456", 0.25, 2)
        );
        mockClickHouseQuery(mockConstituents);

        // When: getConstituentByAddress
        Optional<IndexConstituent> result = provider.getConstituentByAddress(PSI_10, "0x456");

        // Then: Returns correct constituent
        assertThat(result).isPresent();
        assertThat(result.get().username()).isEqualTo("bob");
    }

    @Test
    void shouldReturnEmptyOptionalForNonExistentConstituent() {
        // Given: Index contains only "alice"
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0x123", 0.30, 1)
        );
        mockClickHouseQuery(mockConstituents);

        // When: Query for non-existent trader
        Optional<IndexConstituent> byUsername = provider.getConstituent(PSI_10, "unknown");
        Optional<IndexConstituent> byAddress = provider.getConstituentByAddress(PSI_10, "0x999");

        // Then: Returns empty
        assertThat(byUsername).isEmpty();
        assertThat(byAddress).isEmpty();
    }

    @Test
    void shouldCheckIfTraderIsInIndex() {
        // Given: Index contains "alice" but not "bob"
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0x123", 0.30, 1)
        );
        mockClickHouseQuery(mockConstituents);

        // When/Then: Check presence
        assertThat(provider.isInIndex(PSI_10, "alice")).isTrue();
        assertThat(provider.isInIndex(PSI_10, "bob")).isFalse();
    }

    @Test
    void shouldRefreshCacheOnDemand() {
        // Given: Cache populated with initial data
        List<IndexConstituent> initialConstituents = List.of(
                createConstituent("alice", "0x123", 0.30, 1)
        );
        List<IndexConstituent> updatedConstituents = List.of(
                createConstituent("alice", "0x123", 0.35, 1),  // Updated weight
                createConstituent("bob", "0x456", 0.20, 2)    // New trader
        );

        when(jdbcTemplate.query(anyString(), any(RowMapper.class), eq(PSI_10)))
                .thenReturn(initialConstituents)
                .thenReturn(updatedConstituents);

        // Initial load
        provider.getConstituents(PSI_10);

        // When: Force refresh
        provider.refresh(PSI_10);

        // Then: New data is loaded
        List<IndexConstituent> refreshed = provider.getConstituents(PSI_10);
        assertThat(refreshed).hasSize(2);
        assertThat(refreshed.get(0).weight()).isEqualTo(0.35);

        // And: Two queries were made (initial + refresh)
        verify(jdbcTemplate, times(2)).query(anyString(), any(RowMapper.class), eq(PSI_10));
    }

    @Test
    void shouldHandleEmptyIndex() {
        // Given: Index has no constituents
        mockClickHouseQuery(List.of());

        // When: Query constituents
        List<IndexConstituent> constituents = provider.getConstituents(PSI_10);

        // Then: Returns empty list without error
        assertThat(constituents).isEmpty();
    }

    @Test
    void shouldHandleCaseInsensitiveUsernameLookup() {
        // Given: Index contains "Alice" (mixed case)
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("Alice", "0x123", 0.30, 1)
        );
        mockClickHouseQuery(mockConstituents);

        // When: Lookup with different case
        Optional<IndexConstituent> lowercase = provider.getConstituent(PSI_10, "alice");
        Optional<IndexConstituent> uppercase = provider.getConstituent(PSI_10, "ALICE");

        // Then: Both lookups succeed (case-insensitive)
        assertThat(lowercase).isPresent();
        assertThat(uppercase).isPresent();
    }

    @Test
    void shouldHandleCaseInsensitiveAddressLookup() {
        // Given: Index contains address in lowercase
        List<IndexConstituent> mockConstituents = List.of(
                createConstituent("alice", "0xabc123", 0.30, 1)
        );
        mockClickHouseQuery(mockConstituents);

        // When: Lookup with different case
        Optional<IndexConstituent> uppercase = provider.getConstituentByAddress(PSI_10, "0xABC123");

        // Then: Lookup succeeds (case-insensitive)
        assertThat(uppercase).isPresent();
    }

    // ========== Helper Methods ==========

    private IndexConstituent createConstituent(String username, String proxyAddress, double weight, int rank) {
        return new IndexConstituent(
                username,
                proxyAddress,
                weight,
                rank,
                BigDecimal.valueOf(100000),  // estimatedCapitalUsd
                85.0,  // smartMoneyScore
                "DIRECTIONAL",  // strategyType
                NOW.minusSeconds(3600),  // lastTradeAt
                NOW.minus(Duration.ofDays(30))  // indexedAt
        );
    }

    @SuppressWarnings("unchecked")
    private void mockClickHouseQuery(List<IndexConstituent> constituents) {
        when(jdbcTemplate.query(anyString(), any(RowMapper.class), eq(PSI_10)))
                .thenReturn(constituents);
    }
}
