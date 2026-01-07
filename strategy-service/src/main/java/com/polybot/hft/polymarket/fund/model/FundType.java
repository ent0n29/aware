package com.polybot.hft.polymarket.fund.model;

/**
 * Defines the types of AWARE Fund products.
 *
 * Two main strategies:
 * - MIRROR: Passively mirrors positions of top traders (PSI indexes)
 * - ACTIVE: Runs proprietary strategies directly (ALPHA funds)
 */
public enum FundType {

    // ============== MIRROR FUNDS (Passive) ==============

    /**
     * PSI-10: Mirrors top 10 replicable traders by Smart Money Score.
     * Excludes HFT/arb strategies that don't work with delay.
     */
    PSI_10("PSI-10", FundStrategy.MIRROR, "Top 10 Smart Money traders"),

    /**
     * PSI-25: Broader index of top 25 traders.
     */
    PSI_25("PSI-25", FundStrategy.MIRROR, "Top 25 Smart Money traders"),

    /**
     * PSI-SPORTS: Top traders in sports markets only.
     */
    PSI_SPORTS("PSI-SPORTS", FundStrategy.MIRROR, "Top sports betting traders"),

    /**
     * PSI-CRYPTO: Top traders in crypto price markets.
     */
    PSI_CRYPTO("PSI-CRYPTO", FundStrategy.MIRROR, "Top crypto price traders"),

    /**
     * PSI-POLITICS: Top traders in political markets.
     */
    PSI_POLITICS("PSI-POLITICS", FundStrategy.MIRROR, "Top political market traders"),

    /**
     * PSI-ALPHA: Highest alpha-generating traders across all categories.
     * Selected for consistent outperformance and signal quality.
     */
    PSI_ALPHA("PSI-ALPHA", FundStrategy.MIRROR, "Highest alpha generators"),


    // ============== ACTIVE FUNDS (Proprietary) ==============

    /**
     * ALPHA-ARB: Runs our gabagool22 complete-set arbitrage strategy.
     * Active fund with direct execution (no mirroring).
     */
    ALPHA_ARB("ALPHA-ARB", FundStrategy.ACTIVE, "Complete-set arbitrage strategy"),

    /**
     * ALPHA-INSIDER: Trades based on insider detection signals.
     * Uses InsiderDetector to identify informed trading and follows.
     */
    ALPHA_INSIDER("ALPHA-INSIDER", FundStrategy.ACTIVE, "Insider signal following"),

    /**
     * ALPHA-EDGE: Multi-strategy combining arbitrage + insider + momentum.
     */
    ALPHA_EDGE("ALPHA-EDGE", FundStrategy.ACTIVE, "Multi-strategy alpha fund");


    private final String id;
    private final FundStrategy strategy;
    private final String description;

    FundType(String id, FundStrategy strategy, String description) {
        this.id = id;
        this.strategy = strategy;
        this.description = description;
    }

    public String getId() {
        return id;
    }

    public FundStrategy getStrategy() {
        return strategy;
    }

    public String getDescription() {
        return description;
    }

    /**
     * Check if this fund type mirrors other traders.
     */
    public boolean isMirrorFund() {
        return strategy == FundStrategy.MIRROR;
    }

    /**
     * Check if this fund type runs active strategies.
     */
    public boolean isActiveFund() {
        return strategy == FundStrategy.ACTIVE;
    }

    /**
     * Find fund type by ID string.
     */
    public static FundType fromId(String id) {
        for (FundType type : values()) {
            if (type.id.equalsIgnoreCase(id)) {
                return type;
            }
        }
        throw new IllegalArgumentException("Unknown fund type: " + id);
    }

    /**
     * Strategy classification for funds.
     */
    public enum FundStrategy {
        /**
         * MIRROR: Passively mirrors positions of top traders.
         * Uses FundTradeListener + FundPositionMirror.
         */
        MIRROR,

        /**
         * ACTIVE: Runs proprietary strategies directly.
         * Uses GabagoolDirectionalEngine or similar with fund attribution.
         */
        ACTIVE
    }
}
