from dataclasses import dataclass
from django.conf import settings
from scan.caching_data.base import CachingDataBase

import os
import logging
import requests

logger = logging.getLogger(__name__)

@dataclass
class ExchangeData:
    price_usd: float = float(os.environ.get("COINGECKO_PRICE_USD"))
    market_cap_usd: float = float(os.environ.get("COINGECKO_MKT_USD"))
    percent_change_24h: float = 0

class CachingExchangeData(CachingDataBase):
    _cache_key = "exchange_data"
    _cache_expiring = 3600  # SECONDS to hold value if API breaks
    live_if_empty = False
    default_data_if_empty = ExchangeData()

    @property
    def cached_data(self):
        if settings.TEST_NET:
            return self.default_data_if_empty
        return super().cached_data

    def _loads(self, data):
        return ExchangeData(**data)

    def _dumps(self, data):
        return data.__dict__
    

    def _get_live_data(self):  # Force cache to update unless testnet
        if settings.TEST_NET:
            return self.default_data_if_empty

        try:
            logger.info("Getting Exchange data from API")
            headers = {
                'Accepts': 'application/json',
                'X-CMC_PRO_API_KEY': os.environ.get("COINMARKETCAP_API_KEY"),
            }
            url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={os.environ.get('COIN_SYMBOL')}"
            response = requests.get(url, headers=headers).json()
            logger.info("Error message: %s", response['status']['error_message'])
            data = response['data'][os.environ.get("COIN_SYMBOL")]
            return ExchangeData(
                price_usd=data["quote"]["USD"]["price"],
                market_cap_usd=data["quote"]["USD"]["market_cap"],
                percent_change_24h=data["quote"]["USD"]["percent_change_24h"],
            )
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return self.default_data_if_empty
