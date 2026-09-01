import unittest
from copy import deepcopy

from tools.a_share_sentiment_engine import add_theme_ranks


class ThemeRankingReproducibilityTests(unittest.TestCase):
    def test_equal_scores_use_theme_name_as_stable_tiebreaker(self) -> None:
        items = [
            {
                "theme_name": "电池",
                "price_proxy_score": 10,
                "emotion_proxy_score": 8,
                "turnover_amount": 100,
                "theme_score": 50,
            },
            {
                "theme_name": "电力",
                "price_proxy_score": 10,
                "emotion_proxy_score": 8,
                "turnover_amount": 100,
                "theme_score": 50,
            },
        ]

        forward = add_theme_ranks(deepcopy(items))
        backward = add_theme_ranks(deepcopy(list(reversed(items))))

        self.assertEqual(forward, backward)
        self.assertEqual([item["theme_name"] for item in forward], ["电力", "电池"])


if __name__ == "__main__":
    unittest.main()
