#!/usr/bin/env python3
"""
AWARE Analytics - Market Classification Job

Classifies all unique market slugs into categories (CRYPTO, POLITICS, SPORTS, etc.)
and stores the results in ClickHouse for efficient querying by PSI sectorial indexes.

This job:
1. Fetches all unique market_slugs from aware_global_trades that aren't classified
2. Classifies each using MarketClassifier (keyword/regex matching)
3. Stores classifications in aware_market_classifications table
4. Categories are then used by PSI-POLITICS, PSI-SPORTS, PSI-CRYPTO indexes

Usage:
    python market_classification_job.py                 # Classify new markets
    python market_classification_job.py --full          # Reclassify all markets
    python market_classification_job.py --stats         # Show category stats

Environment Variables:
    CLICKHOUSE_HOST - ClickHouse host (default: localhost)
    CLICKHOUSE_PORT - ClickHouse port (default: 8123)
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime

import clickhouse_connect

from market_classifier import MarketClassifier, MarketCategory

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('market-classification')


class MarketClassificationJob:
    """
    Batch job to classify all unique market slugs and store in ClickHouse.

    Creates/updates the aware_market_classifications table which is then
    used by PSI sectorial indexes (PSI-POLITICS, PSI-SPORTS, PSI-CRYPTO).
    """

    def __init__(self, clickhouse_client):
        self.ch = clickhouse_client
        self.classifier = MarketClassifier()

    def get_unclassified_markets(self) -> list[str]:
        """
        Get market slugs that haven't been classified yet.

        Returns:
            List of market_slug strings needing classification
        """
        query = """
        SELECT DISTINCT t.market_slug
        FROM polybot.aware_global_trades_dedup t
        LEFT JOIN polybot.aware_market_classifications c FINAL
            ON t.market_slug = c.market_slug
        WHERE t.market_slug != ''
          AND c.market_slug IS NULL
        """

        try:
            result = self.ch.query(query)
            slugs = [row[0] for row in result.result_rows]
            logger.info(f"Found {len(slugs)} unclassified markets")
            return slugs
        except Exception as e:
            logger.error(f"Failed to get unclassified markets: {e}")
            return []

    def get_all_markets(self) -> list[str]:
        """
        Get all unique market slugs (for full reclassification).

        Returns:
            List of all market_slug strings
        """
        query = """
        SELECT DISTINCT market_slug
        FROM polybot.aware_global_trades_dedup
        WHERE market_slug != ''
        """

        try:
            result = self.ch.query(query)
            slugs = [row[0] for row in result.result_rows]
            logger.info(f"Found {len(slugs)} total markets")
            return slugs
        except Exception as e:
            logger.error(f"Failed to get all markets: {e}")
            return []

    def classify_markets(self, market_slugs: list[str]) -> list[dict]:
        """
        Classify a list of market slugs.

        Args:
            market_slugs: List of slugs to classify

        Returns:
            List of classification dicts ready for insertion
        """
        classifications = []

        for slug in market_slugs:
            result = self.classifier.classify_with_confidence(slug)
            classifications.append({
                'market_slug': slug,
                'market_category': result.category.value,
                'confidence': result.confidence,
                'matched_patterns': ','.join(result.matched_patterns[:5]),  # Limit patterns stored
            })

        # Log distribution
        category_counts = {}
        for c in classifications:
            cat = c['market_category']
            category_counts[cat] = category_counts.get(cat, 0) + 1

        logger.info(f"Classification distribution: {category_counts}")

        return classifications

    def save_classifications(self, classifications: list[dict]) -> int:
        """
        Save classifications to ClickHouse.

        Args:
            classifications: List of classification dicts

        Returns:
            Number of classifications saved
        """
        if not classifications:
            return 0

        try:
            rows = [
                (
                    c['market_slug'],
                    c['market_category'],
                    c['confidence'],
                    c['matched_patterns'],
                    datetime.utcnow(),
                )
                for c in classifications
            ]

            self.ch.insert(
                'polybot.aware_market_classifications',
                rows,
                column_names=[
                    'market_slug',
                    'market_category',
                    'confidence',
                    'matched_patterns',
                    'classified_at',
                ]
            )

            logger.info(f"Saved {len(rows)} market classifications")
            return len(rows)

        except Exception as e:
            logger.error(f"Failed to save classifications: {e}")
            return 0

    def run(self, full_reclassify: bool = False) -> dict:
        """
        Run the classification job.

        Args:
            full_reclassify: If True, reclassify all markets. If False, only new ones.

        Returns:
            Stats dict with classification results
        """
        start_time = time.time()

        if full_reclassify:
            logger.info("Running FULL market reclassification...")
            market_slugs = self.get_all_markets()
        else:
            logger.info("Classifying new/unclassified markets...")
            market_slugs = self.get_unclassified_markets()

        if not market_slugs:
            logger.info("No markets to classify")
            return {
                'status': 'success',
                'markets_classified': 0,
                'elapsed_seconds': time.time() - start_time,
            }

        # Classify all markets
        classifications = self.classify_markets(market_slugs)

        # Save to ClickHouse
        saved_count = self.save_classifications(classifications)

        elapsed = time.time() - start_time

        # Calculate category distribution
        category_distribution = {}
        for c in classifications:
            cat = c['market_category']
            category_distribution[cat] = category_distribution.get(cat, 0) + 1

        return {
            'status': 'success',
            'markets_classified': saved_count,
            'category_distribution': category_distribution,
            'elapsed_seconds': elapsed,
        }

    def get_stats(self) -> dict:
        """
        Get current classification statistics.

        Returns:
            Dict with category stats
        """
        try:
            # Overall stats
            query = """
            SELECT
                market_category,
                count() AS market_count,
                avg(confidence) AS avg_confidence
            FROM polybot.aware_market_classifications FINAL
            GROUP BY market_category
            ORDER BY market_count DESC
            """

            result = self.ch.query(query)

            categories = {}
            total_markets = 0
            for row in result.result_rows:
                cat, count, conf = row[0], row[1], row[2]
                categories[cat] = {
                    'market_count': count,
                    'avg_confidence': round(conf, 3),
                }
                total_markets += count

            # Check how many are unclassified
            unclassified_query = """
            SELECT count(DISTINCT t.market_slug)
            FROM polybot.aware_global_trades_dedup t
            LEFT JOIN polybot.aware_market_classifications c FINAL
                ON t.market_slug = c.market_slug
            WHERE t.market_slug != ''
              AND c.market_slug IS NULL
            """

            result = self.ch.query(unclassified_query)
            unclassified_count = result.result_rows[0][0] if result.result_rows else 0

            return {
                'total_classified': total_markets,
                'unclassified': unclassified_count,
                'categories': categories,
            }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {'error': str(e)}


def get_clickhouse_client():
    """Get ClickHouse client"""
    return clickhouse_connect.get_client(
        host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
        database=os.getenv('CLICKHOUSE_DATABASE', 'polybot')
    )


def main():
    parser = argparse.ArgumentParser(description='Market Classification Job')
    parser.add_argument('--full', action='store_true',
                       help='Reclassify all markets (not just new ones)')
    parser.add_argument('--stats', action='store_true',
                       help='Show classification statistics')
    args = parser.parse_args()

    ch_client = get_clickhouse_client()
    job = MarketClassificationJob(ch_client)

    if args.stats:
        stats = job.get_stats()
        print("\nMarket Classification Statistics:")
        print("-" * 50)
        print(f"Total classified: {stats.get('total_classified', 0)}")
        print(f"Unclassified: {stats.get('unclassified', 0)}")
        print("\nBy category:")
        for cat, info in stats.get('categories', {}).items():
            print(f"  {cat:15} {info['market_count']:>5} markets  "
                  f"(avg conf: {info['avg_confidence']:.2f})")
    else:
        result = job.run(full_reclassify=args.full)
        print("\nMarket Classification Results:")
        print("-" * 50)
        import json
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
