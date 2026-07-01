# Deep Transaction Lifecycle Flow Results

This document records the exact real-world flows covered by
`tests/test_transaction_lifecycle_deep.py` and the latest observed result from
the Docker test run.

Latest passing run command:

```bash
docker compose -f deploy/docker-compose.yml exec -T web sh -c 'RUN_TAG=deep_fixed_$(date +%H%M%S) python tests/test_transaction_lifecycle_deep.py'
```

## Flow Matrix

| # | Flow | Expected Result | Latest Result |
|---|---|---|---|
| 1 | Create master data: vendors, customers, expense party, `Cash Sale` party if missing, and two stock items | Required parties and items are available | Passed |
| 2 | Run all report groups after setup | Accounts, stock, monthly, sales, dashboard, and legacy report objects execute | Passed |
| 3 | Purchase four serials from vendor | All purchased serials are `in_stock = true` | Passed |
| 4 | Sell serial 1 to customer | Serial 1 becomes `in_stock = false` | Passed |
| 5 | Try to sell serial 1 again while already sold | Duplicate sale is blocked | Passed |
| 6 | Try to return serial 1 from wrong customer | Wrong-customer sale return is blocked | Passed |
| 7 | Return serial 1 from correct customer | Return succeeds and serial becomes `in_stock = true` | Passed |
| 8 | Try to return serial 1 again without a new sale | Duplicate sale return is blocked | Passed |
| 9 | Resell returned serial 1 | Resale succeeds and serial becomes `in_stock = false` | Passed |
| 10 | Return serial 1 after resale | Second valid return succeeds | Passed |
| 11 | Try purchase return with wrong vendor | Wrong-vendor purchase return is blocked | Passed |
| 12 | Purchase return serial after sale/return/resale/return lifecycle | Purchase return succeeds and serial becomes unavailable | Passed |
| 13 | Try to sell serial after purchase return | Sale is blocked | Passed |
| 14 | Purchase mixed-state invoice with four serials | Invoice is created | Passed |
| 15 | Sell one serial from mixed purchase invoice | Sold serial becomes `in_stock = false` | Passed |
| 16 | Validate purchase price-only update while one serial is sold | Validation allows price-only update | Passed |
| 17 | Apply purchase price-only update while one serial is sold | Update succeeds and sold serial remains sold | Passed |
| 18 | Validate replacing only an unsold serial | Validation allows replacement because sold serial is preserved | Passed |
| 19 | Apply replacing only an unsold serial | Replacement succeeds; old unsold serial is removed; replacement is in stock | Passed |
| 20 | Validate removing sold serial from purchase invoice | Validation blocks removal and identifies sold serial | Passed |
| 21 | Try to apply purchase update that removes sold serial | Update is blocked | Passed |
| 22 | Purchase return replacement serial | Purchase return succeeds and replacement becomes unavailable | Passed |
| 23 | Purchase four serials for partial return testing | Serial stock is created | Passed |
| 24 | Sell four serials in one sale invoice | All four serials become sold | Passed |
| 25 | Partially return two of four sold serials | Returned serials become stock; non-returned serials remain sold | Passed |
| 26 | Try to update sale invoice after a sale return exists | Sale invoice update is blocked | Passed |
| 27 | Try to delete sale invoice after a sale return exists | Sale invoice delete is blocked | Passed |
| 28 | Update sale return from two serials down to one serial | Removed return serial goes back to sold; retained return serial stays in stock | Passed |
| 29 | Delete sale return before resale | Return deletion succeeds and all affected serials go back to sold | Passed |
| 30 | Purchase serials for sale-return mutation after resale | Serial stock is created | Passed |
| 31 | Credit sale one serial, then return it | Credit sale return succeeds | Passed |
| 32 | Cash-resell the returned serial | Cash resale succeeds and serial becomes sold | Passed |
| 33 | Try to delete old sale return after the serial was resold | Delete is blocked to avoid two active sold states | Passed |
| 34 | Try to update old sale return after the serial was resold | Update is blocked | Passed |
| 35 | Try to return the cash resale from the old credit customer | Wrong-customer return is blocked | Passed |
| 36 | Return the cash resale from `Cash Sale` | Cash sale return succeeds and serial comes back to stock | Passed |
| 37 | Purchase multi-item serial stock for two items | Multi-item stock is created | Passed |
| 38 | Sell multi-item invoice with six serials | All serials across both items become sold | Passed |
| 39 | Return one serial from each item | Mixed-item partial return succeeds | Passed |
| 40 | Try duplicate mixed-item partial return | Duplicate return is blocked | Passed |
| 41 | Update multi-item return to different sold serials | Old returned serials go back to sold; new returned serials come into stock | Passed |
| 42 | Try to update multi-item sale invoice after return exists | Sale invoice update is blocked | Passed |
| 43 | Try to delete multi-item sale invoice after return exists | Sale invoice delete is blocked | Passed |
| 44 | Run all report groups after every posted entry/checkpoint | Accounts, stock, monthly, sales, dashboard, and retained legacy report objects execute | Passed |
| 45 | Check journal integrity after every checkpoint | No empty journal entries exist | Passed |
| 46 | Check serial sale integrity after every checkpoint | Each tested serial has at most one active `SoldUnits.status = 'Sold'` row | Passed |

## Failed Flows

| Flow # | Failed Flow | Latest Result |
|---|---|---|
| - | None | All previously failing flows passed in the latest full run. |

## Current Summary

Latest Docker run result:

```text
PASSED: all deep lifecycle checks passed.
```

All previously passing checks still passed after the SQL hardening fix. All
accounting, stock, monthly, sales, dashboard, retained legacy report, journal
integrity, and active-sold-row invariant checks passed after the tested
checkpoints.
