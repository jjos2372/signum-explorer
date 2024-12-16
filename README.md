# Signum Explorer

This documentation is a work in progress. More details to follow.
<br>
<br>
<br>
<br>
<br>
## API Info
```json/snrinfo/```                   Used to sync multiple explorers to the SNR master so they are all show the same info.<br>
```json/state/1.2.3.4```              1.2.3.4 is announced address, returns node state (ONLINE=1 UNREACHABLE=2 SYNC=3 STUCK=4 FORKED=5). <br>
```json/nodeinfo/1.2.3.4```           1.2.3.4 is announced address, returns node details. <br>
```json/accounts/```                  Returns top 10 richest accounts. <br>

## Slow Queries?
Don't forget to create these indexes:
```
CREATE INDEX transaction_height_timestamp ON transaction(height, timestamp);
CREATE INDEX asset_height ON asset(height);
CREATE INDEX account_latest ON account(latest);

```
