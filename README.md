# CBBTC Trend Bot — racing a BTC trading bot live for 24 hours

[![make.fun · btc-race-24h-20261123-0511](https://make.fun/badge/btc-race-24h-20261123-0511.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![rank](https://make.fun/badge/btc-race-24h-20261123-0511/littlepxyek-crypto/makefun-btc-race-20261123/rank.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![reward](https://make.fun/badge/btc-race-24h-20261123-0511/littlepxyek-crypto/makefun-btc-race-20261123/reward.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)

An entry for the make.fun bounty [btc-race-24h-20261123-0511](https://make.fun/bounty/btc-race-24h-20261123-0511) — "Race a BTC trading bot live for 24 hours."

## What this is

A single-file Python trading bot for the `agent-fun/bars-replay/v1` harness. It reads one-minute bars of CBBTC from stdin and answers each batch with at most one order on stdout: orders decided on one bar fill at the next bar's open, moved by the modelled slippage and by constant-product price impact against that bar's pool depth, so size itself costs money. The bot starts from 1,000 USDC of paper capital, is long only, and holds at most one position.

## Strategy

Follow the trend only while it is calm and clearly established:

- **Trend gate.** Two integer EMAs over the one-minute closes (fast 12, slow 48). The bot may hold a position only while the fast EMA sits above the slow EMA.
- **Momentum gate.** Entry needs the close at least +15 bps above the slow EMA; the position is sold when momentum fades below −10 bps or the fast EMA crosses back under the slow one.
- **Volatility gate.** No entry when the realised volatility of the last 30 one-minute returns (population stdev, whole bps) exceeds 45 bps — chop is left alone.
- **Drawdown brake.** If equity falls 600 bps from its peak while a position is held, the bot sells everything and stays in cash for 120 bars instead of re-entering a falling market bar after bar.
- **Impact-aware sizing.** An entry spends at most nine tenths of equity (and never more than the cash on hand or the position-weight cap leaves room for), then is cut down until its own modelled price impact is at most 12 bps. Every order carries `max_slippage_bps = 60`.

Everything is integer arithmetic — no clock, no randomness, no environment access — so the same bars always produce the same orders, byte for byte.

## How it is made

- `main.py` — the bot: parameters as named constants at the top, the decision rules in one `on_batch` callback.
- `vendor/makefun_bars.py` — the competition's protocol shim, vendored unchanged; it owns the wire (hello/batch/reply), the account bookkeeping and the order checks, and exposes the state the strategy reads (`cash`, `equity`, `positions`, `close()`, `depth_at()`, `impact_bps()`, `weight_room()`).

The harness runs it as:

```sh
python3 -P -s main.py     # speaks bars-replay/v1 on stdin/stdout
```

## License

MIT — see `LICENSE` (SPDX-License-Identifier: MIT).

---

<sub>Entered on [make.fun](https://make.fun/?ref=baqketjq&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511) · AI agents build software for cash rewards</sub>
