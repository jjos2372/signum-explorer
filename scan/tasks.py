import logging
import os
import requests, json

from time import sleep
from django.conf import settings
from config.settings import TASKS_SCAN_DELAY, SNR_MASTER_EXPLORER
from django.core.cache import cache

from scan.models import PeerMonitor
from scan.caching_data.exchange import CachingExchangeData
from scan.caching_data.total_txs_count import CachingTotalTxsCount
from scan.caching_data.total_circulating import CachingTotalCirculating
#from scan.caching_data.total_accounts_count import CachingTotalAccountsCount

logger = logging.getLogger(__name__)

######################################
# These tasks run on a regular       #
# interval, currently 60 sec         #
# via a remote script or supervisord #
# By loading cache via a task it     #
# saves the user from a slow initial #
# page load.                         #
######################################

def task_cmd():
    if TASKS_SCAN_DELAY > 0:  # Delay in env used when supervisord is used.
        logger.info(f"Tasks Sleeping for {TASKS_SCAN_DELAY} seconds...")
        sleep(TASKS_SCAN_DELAY)
        logger.info("Checking for tasks that need to be updated.")       

############# Update Exchange ############## (update exchange from api every 5 min)
    exchange_ttl = cache.get('exchange_ttl')
    if not exchange_ttl:
        logger.info("  TASK - Update Cache Exchange data")
        CachingExchangeData().update_live_data()
        cache.set('exchange_ttl', 'ttl', timeout=300) 
        
############## Update Total TX ############# (match block time, heavy db request)
    total_tx_ttl = cache.get('total_tx_ttl')
    if not total_tx_ttl:
        logger.info("  TASK - Update Total TX's count data")
        CachingTotalTxsCount().update_live_data()
        cache.set('total_tx_ttl', 'ttl', timeout=240)
        
######### Update Total Circulating ######### (match block time, heavy db request)
    total_circ_ttl = cache.get('total_circ_ttl')
    if not total_circ_ttl:
        logger.info("  TASK - Update Total Circulating data")
        CachingTotalCirculating().update_live_data()
        cache.set('total_circ_ttl', 'ttl', timeout=240)
    
######### Update Peers SNR Status ########## (update every 3 hours)
    if SNR_MASTER_EXPLORER :
        snr_master_ttl = cache.get('snr_master_ttl')
        if not snr_master_ttl:
            logger.info("  TASK - Update Peer SNR data")
            snr_master = list(requests.get(url=SNR_MASTER_EXPLORER + "/json/SNRinfo").json())
            for node in snr_master:
                PeerMonitor.objects.filter(announced_address=node[0]).update(reward_state=node[2], reward_time=node[3])
            if snr_master :
                logger.info("SNR Master Data Received")
                cache.set('snr_master_ttl', 'ttl', timeout=10800)



#    def update_cache_total_accounts_count():
#        logger.info("TASK - Update Total Accounts data")
#        CachingTotalAccountsCount().update_live_data()
