package com.polybot.hft.polymarket.fund.service;

import com.polybot.hft.polymarket.fund.model.IndexConstituent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Provides index weights for PSI funds from ClickHouse.
 *
 * Caches weights with configurable TTL to avoid hammering ClickHouse.
 * Supports multiple index types (PSI-10, PSI-SPORTS, etc.).
 */
@Slf4j
@RequiredArgsConstructor
public class IndexWeightProvider {

    private static final long CACHE_TTL_MS = 60_000; // 1 minute cache

    private final JdbcTemplate jdbcTemplate;

    // Cache: indexName -> (constituents, loadedAt)
    private final Map<String, CachedIndex> cache = new ConcurrentHashMap<>();

    /**
     * Get all constituents for an index.
     */
    public List<IndexConstituent> getConstituents(String indexName) {
        CachedIndex cached = cache.get(indexName);
        if (cached != null && !cached.isExpired()) {
            return cached.constituents;
        }

        List<IndexConstituent> constituents = loadFromClickHouse(indexName);
        cache.put(indexName, new CachedIndex(constituents, System.currentTimeMillis()));
        log.info("Loaded {} constituents for index {}", constituents.size(), indexName);
        return constituents;
    }

    /**
     * Get a specific constituent by username.
     */
    public Optional<IndexConstituent> getConstituent(String indexName, String username) {
        return getConstituents(indexName).stream()
                .filter(c -> c.username().equalsIgnoreCase(username))
                .findFirst();
    }

    /**
     * Get constituent by proxy address.
     */
    public Optional<IndexConstituent> getConstituentByAddress(String indexName, String proxyAddress) {
        return getConstituents(indexName).stream()
                .filter(c -> c.proxyAddress().equalsIgnoreCase(proxyAddress))
                .findFirst();
    }

    /**
     * Check if a trader is in the index.
     */
    public boolean isInIndex(String indexName, String username) {
        return getConstituent(indexName, username).isPresent();
    }

    /**
     * Get weight for a trader (0.0 if not in index).
     */
    public double getWeight(String indexName, String username) {
        return getConstituent(indexName, username)
                .map(IndexConstituent::weight)
                .orElse(0.0);
    }

    /**
     * Force refresh the cache.
     */
    public void refresh(String indexName) {
        cache.remove(indexName);
        getConstituents(indexName);
    }

    private List<IndexConstituent> loadFromClickHouse(String indexName) {
        // Uses 200_fund_schema.sql aware_psi_index structure
        // Columns: index_type, username, proxy_address, weight, total_score, sharpe_ratio, strategy_type
        // Note: ClickHouse doesn't allow "table FINAL AS alias" syntax, so we use subqueries
        String sql = """
            SELECT
                i.username,
                i.proxy_address,
                i.weight,
                row_number() OVER (ORDER BY i.weight DESC) AS rank_in_index,
                COALESCE(p.total_volume_usd, 0) AS estimated_capital,
                i.total_score AS smart_money_score,
                COALESCE(i.strategy_type, 'UNKNOWN') AS strategy_type,
                p.last_trade_at
            FROM (SELECT * FROM polybot.aware_psi_index FINAL WHERE index_type = ?) AS i
            LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p ON i.proxy_address = p.proxy_address
            ORDER BY i.weight DESC
            """;

        return jdbcTemplate.query(sql, (rs, rowNum) -> IndexConstituent.fromIndexQuery(
                rs.getString("username"),
                rs.getString("proxy_address"),
                rs.getDouble("weight"),
                rs.getInt("rank_in_index"),
                BigDecimal.valueOf(rs.getDouble("estimated_capital")),
                rs.getDouble("smart_money_score"),
                rs.getString("strategy_type"),
                rs.getTimestamp("last_trade_at") != null
                        ? rs.getTimestamp("last_trade_at").toInstant()
                        : null
        ), indexName);
    }

    private record CachedIndex(List<IndexConstituent> constituents, long loadedAt) {
        boolean isExpired() {
            return System.currentTimeMillis() - loadedAt > CACHE_TTL_MS;
        }
    }
}
