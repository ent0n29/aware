"""
AWARE Analytics - Market Category Classifier

Classifies Polymarket markets into categories for sectorial index filtering.

Categories:
- CRYPTO: BTC, ETH, crypto price markets
- POLITICS: Elections, policy, geopolitical events
- SPORTS: NBA, NFL, soccer, tennis, etc.
- NEWS: Breaking news, current events
- ENTERTAINMENT: Awards, TV, celebrities
- ECONOMICS: Fed rates, GDP, employment
- SCIENCE: Scientific discoveries, space
- OTHER: Uncategorized

Usage:
    classifier = MarketClassifier()
    category = classifier.classify("will-btc-hit-100k")
    # Returns: MarketCategory.CRYPTO
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class MarketCategory(Enum):
    """Categories of prediction markets"""
    CRYPTO = "CRYPTO"
    POLITICS = "POLITICS"
    SPORTS = "SPORTS"
    NEWS = "NEWS"
    ENTERTAINMENT = "ENTERTAINMENT"
    ECONOMICS = "ECONOMICS"
    SCIENCE = "SCIENCE"
    OTHER = "OTHER"


# ═══════════════════════════════════════════════════════════════════════════════
# KEYWORD-BASED CLASSIFICATION RULES
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns are checked in order; first match wins
CATEGORY_PATTERNS = {
    MarketCategory.CRYPTO: [
        # Price markets
        r'\bbtc\b', r'\bbitcoin\b', r'\beth\b', r'\bethereum\b',
        r'\bsol\b', r'\bsolana\b', r'\bxrp\b', r'\bdoge\b', r'\bshib\b',
        r'\bcrypto\b', r'\btoken\b', r'\bdefi\b', r'\bnft\b',
        # Up/Down price patterns
        r'\bprice\b.*\b(above|below|hit|reach)\b',
        r'\b(above|below|hit|reach)\b.*\bprice\b',
        # Specific patterns
        r'\$\d+k\b',  # $100k, $50k etc.
        r'\bhalving\b', r'\betf\b.*\bcrypto\b', r'\bcrypto\b.*\betf\b',
    ],
    MarketCategory.SPORTS: [
        # Major leagues
        r'\bnba\b', r'\bnfl\b', r'\bmlb\b', r'\bnhl\b', r'\bmls\b',
        r'\bpremier\s*league\b', r'\bla\s*liga\b', r'\bserie\s*a\b',
        r'\bbundesliga\b', r'\bchampions\s*league\b', r'\buefa\b',
        # Sports terms
        r'\bsuper\s*bowl\b', r'\bworld\s*series\b', r'\bworld\s*cup\b',
        r'\bolympics\b', r'\bmarch\s*madness\b', r'\bplayoffs\b',
        r'\bfinals\b.*\b(win|champion)\b',
        # Teams (major ones)
        r'\blakers\b', r'\bceltics\b', r'\bwarriors\b', r'\bchiefs\b',
        r'\beagles\b', r'\bcowboys\b', r'\byankees\b', r'\bdodgers\b',
        # Sports types
        r'\btennis\b', r'\bgolf\b', r'\bboxing\b', r'\bufc\b', r'\bmma\b',
        r'\bf1\b', r'\bformula\s*1\b', r'\bnascar\b',
        # Player names (dynamic, could be expanded)
        r'\blebron\b', r'\bcurry\b', r'\bmahomes\b', r'\bbrady\b',
    ],
    MarketCategory.POLITICS: [
        # Elections
        r'\belection\b', r'\bvote\b', r'\bballot\b', r'\bprimary\b',
        r'\bpresident\b', r'\bgovernor\b', r'\bsenator\b', r'\bcongress\b',
        r'\brepublican\b', r'\bdemocrat\b', r'\bgop\b',
        # Political figures
        r'\btrump\b', r'\bbiden\b', r'\bharris\b', r'\bobama\b',
        r'\bdesantis\b', r'\bnewsom\b', r'\bpelosi\b', r'\bmcconnell\b',
        # Geopolitics
        r'\bwar\b', r'\binvasion\b', r'\bsanction\b', r'\btreaty\b',
        r'\bnato\b', r'\bun\b.*\bresolution\b',
        r'\brussia\b', r'\bukraine\b', r'\bchina\b', r'\btaiwan\b',
        r'\bisrael\b', r'\bpalestine\b', r'\biran\b',
        # Policy
        r'\bimpeach\b', r'\blegislat\b', r'\bbill\b.*\bpass\b',
        r'\bsupreme\s*court\b', r'\bscotus\b',
    ],
    MarketCategory.ECONOMICS: [
        # Fed and monetary policy
        r'\bfed\b', r'\bfederal\s*reserve\b', r'\binterest\s*rate\b',
        r'\binflation\b', r'\bcpi\b', r'\bfomc\b',
        r'\brate\s*(cut|hike)\b', r'\b(cut|hike)\s*rate\b',
        # Economic indicators
        r'\bgdp\b', r'\bunemployment\b', r'\bjobs\s*report\b',
        r'\brecession\b', r'\bstock\s*market\b', r'\bs&p\b', r'\bnasdaq\b',
        r'\bdow\b', r'\btreasury\b', r'\byield\b',
    ],
    MarketCategory.ENTERTAINMENT: [
        # Awards
        r'\boscars?\b', r'\bacademy\s*award\b', r'\bemmy\b', r'\bgrammy\b',
        r'\bgolden\s*globe\b', r'\bsag\s*award\b',
        # TV/Movies
        r'\bnetflix\b', r'\bdisney\b', r'\bhbo\b', r'\bstreaming\b',
        r'\bbox\s*office\b', r'\bmovie\b.*\b(gross|earn)\b',
        # Celebrities
        r'\btaylor\s*swift\b', r'\beyoncé?\b', r'\bkanye\b',
        r'\bkardashan\b', r'\belon\s*musk\b',
    ],
    MarketCategory.SCIENCE: [
        # Space
        r'\bspacex\b', r'\bnasa\b', r'\brocket\b', r'\blaunch\b',
        r'\bmars\b', r'\bmoon\b', r'\bastronaut\b', r'\bstarship\b',
        # Tech/Science
        r'\bai\b.*\b(breakthrough|achieve)\b', r'\bquantum\b',
        r'\bclimate\b', r'\bglobal\s*warming\b',
        r'\bvaccine\b', r'\bcovid\b', r'\bpandemic\b',
    ],
    MarketCategory.NEWS: [
        # Breaking news patterns
        r'\bbreaking\b', r'\bjust\s*in\b',
        r'\bwill\b.*\bhappen\b.*\btoday\b',
        r'\bthis\s*week\b', r'\bby\s*end\s*of\b',
        # Current events
        r'\btweet\b', r'\bannounce\b', r'\bresign\b', r'\bfire[ds]?\b',
        r'\barrest\b', r'\bindict\b', r'\bcharge[ds]?\b',
        # Time-sensitive
        r'\bby\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        r'\bby\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b',
    ],
}


@dataclass
class ClassificationResult:
    """Result of market classification"""
    category: MarketCategory
    confidence: float  # 0.0 to 1.0
    matched_patterns: list[str]


class MarketClassifier:
    """
    Classifies markets into categories based on slug and description.

    Uses keyword/regex pattern matching. Could be enhanced with ML later.
    """

    def __init__(self):
        # Compile patterns for efficiency
        self._compiled_patterns = {}
        for category, patterns in CATEGORY_PATTERNS.items():
            self._compiled_patterns[category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def classify(
        self,
        market_slug: str,
        description: str = ""
    ) -> MarketCategory:
        """
        Classify a market into a category.

        Args:
            market_slug: The market's URL slug (e.g., "will-btc-hit-100k")
            description: Optional market description/question

        Returns:
            MarketCategory enum value
        """
        result = self.classify_with_confidence(market_slug, description)
        return result.category

    def classify_with_confidence(
        self,
        market_slug: str,
        description: str = ""
    ) -> ClassificationResult:
        """
        Classify with confidence score and matched patterns.

        Args:
            market_slug: The market's URL slug
            description: Optional market description

        Returns:
            ClassificationResult with category, confidence, and matched patterns
        """
        # Combine slug and description for matching
        text = f"{market_slug.replace('-', ' ')} {description}".lower()

        best_category = MarketCategory.OTHER
        best_matches = []
        best_score = 0

        for category, patterns in self._compiled_patterns.items():
            matches = []
            for pattern in patterns:
                if pattern.search(text):
                    matches.append(pattern.pattern)

            if len(matches) > best_score:
                best_score = len(matches)
                best_category = category
                best_matches = matches

        # Calculate confidence based on number of matches
        # More matches = higher confidence
        confidence = min(1.0, best_score * 0.25)  # 4+ matches = 100%

        return ClassificationResult(
            category=best_category,
            confidence=confidence,
            matched_patterns=best_matches
        )

    def classify_batch(
        self,
        markets: list[dict]
    ) -> dict[str, MarketCategory]:
        """
        Classify multiple markets at once.

        Args:
            markets: List of dicts with 'slug' and optional 'description'

        Returns:
            Dict mapping slug -> category
        """
        results = {}
        for market in markets:
            slug = market.get('slug', market.get('market_slug', ''))
            desc = market.get('description', market.get('question', ''))
            results[slug] = self.classify(slug, desc)
        return results


class TraderCategoryProfiler:
    """
    Profiles a trader's market category distribution.

    Used to determine which traders specialize in which categories
    for sectorial index inclusion.

    NOTE: This uses the pre-computed aware_market_classifications table
    populated by market_classification_job.py for efficiency.
    """

    def __init__(self, clickhouse_client, classifier: Optional[MarketClassifier] = None):
        self.ch = clickhouse_client
        self.classifier = classifier or MarketClassifier()

    def get_trader_category_distribution(
        self,
        proxy_address: str
    ) -> dict[str, float]:
        """
        Get a trader's volume distribution across market categories.

        Uses the pre-computed aware_market_classifications table for efficiency.
        Falls back to on-the-fly classification if classifications table is empty.

        Args:
            proxy_address: Trader's wallet address

        Returns:
            Dict mapping category -> percentage of volume (0.0 to 1.0)
        """
        # First try using the pre-computed classifications table (efficient)
        query = """
        SELECT
            COALESCE(c.market_category, 'OTHER') AS category,
            sum(t.notional) as volume
        FROM polybot.aware_global_trades_dedup t
        LEFT JOIN polybot.aware_market_classifications c FINAL
            ON t.market_slug = c.market_slug
        WHERE t.proxy_address = %(addr)s
        GROUP BY category
        """

        try:
            result = self.ch.query(query, parameters={'addr': proxy_address})

            if not result.result_rows:
                return {}

            category_volumes = {cat.value: 0.0 for cat in MarketCategory}
            total_volume = 0.0

            for row in result.result_rows:
                category, volume = row[0], float(row[1] or 0)
                if category in category_volumes:
                    category_volumes[category] += volume
                else:
                    category_volumes['OTHER'] += volume
                total_volume += volume

            # Convert to percentages
            if total_volume > 0:
                return {
                    cat: vol / total_volume
                    for cat, vol in category_volumes.items()
                }

            return {}

        except Exception as e:
            logger.error(f"Failed to get category distribution for {proxy_address}: {e}")
            # Fall back to on-the-fly classification
            return self._get_distribution_fallback(proxy_address)

    def _get_distribution_fallback(self, proxy_address: str) -> dict[str, float]:
        """
        Fallback: classify on-the-fly if classifications table is unavailable.

        This is slower but works when the table hasn't been populated yet.
        """
        query = """
        SELECT
            market_slug,
            sum(notional) as volume
        FROM polybot.aware_global_trades_dedup
        WHERE proxy_address = %(addr)s
        GROUP BY market_slug
        """

        try:
            result = self.ch.query(query, parameters={'addr': proxy_address})

            if not result.result_rows:
                return {}

            category_volumes = {cat.value: 0.0 for cat in MarketCategory}
            total_volume = 0.0

            for row in result.result_rows:
                slug, volume = row[0], float(row[1] or 0)
                category = self.classifier.classify(slug)
                category_volumes[category.value] += volume
                total_volume += volume

            if total_volume > 0:
                return {
                    cat: vol / total_volume
                    for cat, vol in category_volumes.items()
                }

            return {}

        except Exception as e:
            logger.error(f"Fallback classification failed for {proxy_address}: {e}")
            return {}

    def get_all_trader_profiles(self, limit: int = 10000) -> dict[str, dict[str, float]]:
        """
        Get category distributions for all top traders.

        Uses the pre-computed aware_market_classifications table for efficiency.

        Returns:
            Dict mapping proxy_address -> {category: percentage}
        """
        # Use pre-computed classifications with a single efficient query
        query = f"""
        WITH trader_category_volumes AS (
            SELECT
                t.proxy_address,
                COALESCE(c.market_category, 'OTHER') AS category,
                sum(t.notional) as volume
            FROM polybot.aware_global_trades_dedup t
            LEFT JOIN polybot.aware_market_classifications c FINAL
                ON t.market_slug = c.market_slug
            WHERE t.proxy_address != ''
            GROUP BY t.proxy_address, category
        ),
        trader_totals AS (
            SELECT
                proxy_address,
                sum(volume) as total_volume
            FROM trader_category_volumes
            GROUP BY proxy_address
            ORDER BY total_volume DESC
            LIMIT {limit}
        )
        SELECT
            tcv.proxy_address,
            tcv.category,
            tcv.volume,
            tt.total_volume
        FROM trader_category_volumes tcv
        INNER JOIN trader_totals tt ON tcv.proxy_address = tt.proxy_address
        """

        try:
            logger.info("Fetching category distributions for all traders...")
            result = self.ch.query(query)

            # Build profiles directly from pre-aggregated categories
            profiles = {}
            for row in result.result_rows:
                addr, category, volume, total_volume = row[0], row[1], float(row[2] or 0), float(row[3] or 0)

                if addr not in profiles:
                    profiles[addr] = {cat.value: 0.0 for cat in MarketCategory}

                if category in profiles[addr]:
                    profiles[addr][category] = volume / total_volume if total_volume > 0 else 0.0
                else:
                    profiles[addr]['OTHER'] += volume / total_volume if total_volume > 0 else 0.0

            logger.info(f"Profiled {len(profiles)} traders across categories")
            return profiles

        except Exception as e:
            logger.error(f"Failed to get all trader profiles: {e}")
            return {}

    def filter_by_category(
        self,
        traders: list[str],
        required_categories: list[str],
        min_concentration: float = 0.5
    ) -> list[str]:
        """
        Filter traders to those who specialize in given categories.

        Args:
            traders: List of proxy addresses
            required_categories: Categories the trader must specialize in
            min_concentration: Minimum total volume in required categories

        Returns:
            Filtered list of proxy addresses
        """
        profiles = {addr: self.get_trader_category_distribution(addr) for addr in traders}

        filtered = []
        for addr in traders:
            profile = profiles.get(addr, {})

            # Sum concentration across required categories
            total_concentration = sum(
                profile.get(cat, 0.0)
                for cat in required_categories
            )

            if total_concentration >= min_concentration:
                filtered.append(addr)

        return filtered


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def test_classifier():
    """Test the classifier with sample markets"""
    classifier = MarketClassifier()

    test_cases = [
        ("will-btc-hit-100k-by-end-of-2024", MarketCategory.CRYPTO),
        ("ethereum-price-above-4000", MarketCategory.CRYPTO),
        ("trump-win-2024-election", MarketCategory.POLITICS),
        ("biden-approval-rating-above-50", MarketCategory.POLITICS),
        ("lakers-win-nba-championship", MarketCategory.SPORTS),
        ("super-bowl-winner-2025", MarketCategory.SPORTS),
        ("fed-cut-rates-december", MarketCategory.ECONOMICS),
        ("inflation-below-3-percent", MarketCategory.ECONOMICS),
        ("taylor-swift-wins-grammy", MarketCategory.ENTERTAINMENT),
        ("spacex-starship-successful-launch", MarketCategory.SCIENCE),
        ("ceo-resign-this-week", MarketCategory.NEWS),
    ]

    print("Market Classification Tests:")
    print("-" * 60)

    for slug, expected in test_cases:
        result = classifier.classify_with_confidence(slug)
        status = "✓" if result.category == expected else "✗"
        print(f"{status} {slug[:40]:40} → {result.category.value:12} (conf: {result.confidence:.2f})")

    print("-" * 60)


if __name__ == "__main__":
    test_classifier()
