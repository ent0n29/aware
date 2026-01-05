"""
Sequence Feature Extractor

Builds trade sequences for LSTM/Transformer models.
Each trade is represented as a feature vector:
- Normalized price
- Log-scaled size
- Side encoding (buy=1, sell=-1)
- Time delta from previous trade
- Outcome index
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class SequenceExtractor:
    """
    Extract trade sequences for deep learning models.

    Converts raw trades into fixed-length sequences suitable
    for LSTM or Transformer architectures.
    """

    def __init__(self, ch_client, sequence_length: int = 100):
        """
        Initialize sequence extractor.

        Args:
            ch_client: ClickHouse client
            sequence_length: Max number of trades in sequence
        """
        self.ch_client = ch_client
        self.sequence_length = sequence_length

    def extract(self, proxy_address: str) -> dict:
        """
        Extract trade sequence for a trader.

        Args:
            proxy_address: Trader wallet address

        Returns:
            Dict with 'sequence' (numpy array) and 'length' (int)
        """
        try:
            trades = self._get_recent_trades(proxy_address)

            if not trades:
                return {'sequence': None, 'length': 0}

            sequence = self._build_sequence(trades)

            return {
                'sequence': sequence,
                'length': len(trades),
            }

        except Exception as e:
            logger.error(f"Failed to extract sequence for {proxy_address}: {e}")
            return {'sequence': None, 'length': 0}

    def _get_recent_trades(self, proxy_address: str) -> list[dict]:
        """Get most recent trades for sequence building."""
        try:
            result = self.ch_client.query(f"""
                SELECT
                    ts,
                    price,
                    size,
                    notional,
                    side,
                    outcome_index,
                    market_slug
                FROM aware_global_trades_dedup
                WHERE proxy_address = %(addr)s
                ORDER BY ts DESC
                LIMIT {self.sequence_length}
            """, parameters={'addr': proxy_address})

            trades = []
            for row in result.result_rows:
                trades.append({
                    'ts': row[0],
                    'price': row[1],
                    'size': row[2],
                    'notional': row[3],
                    'side': row[4],
                    'outcome_index': row[5] or 0,
                    'market_slug': row[6],
                })

            # Reverse to chronological order
            return list(reversed(trades))

        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    def _build_sequence(self, trades: list[dict]) -> np.ndarray:
        """
        Build feature sequence from trades.

        Features per trade:
        0. price_normalized: price mapped to [-1, 1] range (0.5 -> 0)
        1. size_log: log(size + 1) normalized
        2. side: 1 for BUY, -1 for SELL
        3. time_delta: log(seconds since previous trade + 1) normalized
        4. outcome_idx: 0 or 1 for YES/NO

        Returns:
            numpy array of shape (seq_len, 5)
        """
        n = len(trades)
        seq_dim = 5
        sequence = np.zeros((self.sequence_length, seq_dim), dtype=np.float32)

        prev_ts = None

        for i, trade in enumerate(trades[:self.sequence_length]):
            # Price: map [0, 1] to [-1, 1]
            price_norm = (trade['price'] - 0.5) * 2

            # Size: log-scale and normalize
            size_log = np.log1p(trade['size'])
            size_norm = min(1.0, size_log / 10.0)  # Cap at ~22000

            # Side: binary
            side = 1.0 if trade['side'] == 'BUY' else -1.0

            # Time delta from previous trade
            if prev_ts is not None:
                delta_seconds = (trade['ts'] - prev_ts).total_seconds()
                # Log-scale and normalize (cap at 1 week)
                delta_norm = min(1.0, np.log1p(delta_seconds) / np.log1p(604800))
            else:
                delta_norm = 0.0
            prev_ts = trade['ts']

            # Outcome index (0 or 1)
            outcome = float(trade['outcome_index'])

            sequence[i] = [price_norm, size_norm, side, delta_norm, outcome]

        return sequence

    def extract_batch(self, proxy_addresses: list[str]) -> tuple[np.ndarray, list[int]]:
        """
        Extract sequences for multiple traders.

        Args:
            proxy_addresses: List of wallet addresses

        Returns:
            - sequences: (N, seq_len, features) array
            - lengths: List of actual sequence lengths
        """
        n = len(proxy_addresses)
        sequences = np.zeros((n, self.sequence_length, 5), dtype=np.float32)
        lengths = []

        for i, addr in enumerate(proxy_addresses):
            result = self.extract(addr)
            if result['sequence'] is not None:
                seq_len = min(result['length'], self.sequence_length)
                sequences[i, :seq_len] = result['sequence'][:seq_len]
                lengths.append(seq_len)
            else:
                lengths.append(0)

        return sequences, lengths


class SequenceAugmenter:
    """
    Data augmentation for trade sequences.

    Useful for training to prevent overfitting.
    """

    @staticmethod
    def random_crop(sequence: np.ndarray, length: int, crop_ratio: float = 0.8) -> tuple[np.ndarray, int]:
        """Randomly crop sequence to shorter length."""
        if length < 10:
            return sequence, length

        new_len = max(10, int(length * crop_ratio))
        start = np.random.randint(0, length - new_len + 1)

        cropped = np.zeros_like(sequence)
        cropped[:new_len] = sequence[start:start + new_len]

        return cropped, new_len

    @staticmethod
    def add_noise(sequence: np.ndarray, noise_std: float = 0.05) -> np.ndarray:
        """Add Gaussian noise to continuous features."""
        noisy = sequence.copy()
        # Only add noise to price and size (indices 0, 1)
        noisy[:, :2] += np.random.normal(0, noise_std, noisy[:, :2].shape)
        return noisy

    @staticmethod
    def time_warp(sequence: np.ndarray, length: int, warp_factor: float = 0.1) -> np.ndarray:
        """Randomly scale time deltas."""
        warped = sequence.copy()
        # Warp time delta (index 3)
        scale = 1.0 + np.random.uniform(-warp_factor, warp_factor)
        warped[:length, 3] *= scale
        warped[:length, 3] = np.clip(warped[:length, 3], 0, 1)
        return warped
