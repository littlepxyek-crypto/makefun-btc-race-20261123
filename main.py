"""CBBTC minute-bar regime-hold bot for agent-fun/bars-replay/v1 (make.fun btc-race-24h).

Strategy: establish an uptrend against a 120-bar EMA and hold it. The bot
takes one position when the close stands at least ENTRY_BPS above that EMA,
then simply holds; it leaves only on a 350 bps trailing stop under the
highest close since the entry, a regime break 150 bps under the EMA, or the
800 bps equity drawdown brake, which also parks the bot in cash for a
120-bar cooldown. Entries are sized down until their own modelled price
impact is at most IMPACT_CAP_BPS. There is no per-bar trend chasing: in a
window that jumps once and then chops sideways, the bot trades rarely and
lets the position ride instead of bleeding fees on crossovers.

Everything is integer arithmetic, with no clock, no randomness and no
environment access: the same bars always produce the same orders, byte for
byte.

The wire protocol (hello/batch/reply, account bookkeeping, order checks) is
owned by the vendored shim, vendor/makefun_bars.py; this file only decides.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

#: The only symbol this bot trades.
SYMBOL = "CBBTC"

#: Basis points per unit (10_000 bps = 100%).
BPS = 10_000

# --- strategy parameters (tune here; nothing else needs to change) ---
EMA_REGIME = 120         # the single regime EMA length, in one-minute bars
ENTRY_BPS = 10           # entry needs close >= regime EMA * (1 + 10 bps)
TRAIL_BPS = 350          # trailing stop: sell at 350 bps under the peak close
REGIME_EXIT_BPS = 150    # regime break: sell when close < EMA * (1 - 150 bps)
DD_BRAKE_BPS = 800       # drawdown brake: peak-to-current equity loss, bps
BRAKE_COOLDOWN_BARS = 120  # bars parked in cash after the brake fires
MAX_SLIPPAGE_BPS = 60    # max_slippage_bps stamped on every order
MIN_BARS = 120           # closes to collect before any rule may fire
IMPACT_CAP_BPS = 12      # entries are cut until their own impact is <= this
MIN_NOTIONAL = 1_000_000  # 1 USDC in quote units (6 decimals); smaller is refused

# --- run state (one process, one run; rebuilt from the bars alone) ---
_closes = []             # every CBBTC close seen, oldest first (ints)
_ema = None              # integer EMA over _closes, seeded at the first close
_peak_equity = 0         # highest state.equity seen so far (quote units)
_cooldown = 0            # bars of entry ban left after the drawdown brake
_peak_close = None       # highest close since the current position opened


def _ema_update(ema, close, period):
    """One integer EMA step with k = 2 / (period + 1): ((n-1)*ema + 2*close) // (n+1)."""
    if ema is None:
        return close
    return (ema * (period - 1) + 2 * close) // (period + 1)


def _sell_all(qty):
    """The single exit order: the whole position, at the standing slippage cap."""
    return {"side": "sell", "symbol": SYMBOL, "qty": qty, "max_slippage_bps": MAX_SLIPPAGE_BPS}


def on_batch(state, batch):
    """Decide the orders for one batch: at most one, and usually none."""
    global _ema, _peak_equity, _cooldown, _peak_close

    # The batch's CBBTC bar is the only new fact; without it there is nothing
    # to update and nothing to decide.
    close = None
    for bar in batch["bars"]:
        if bar["symbol"] == SYMBOL:
            close = int(bar["c"])
    if close is None:
        return []

    _closes.append(close)
    _ema = _ema_update(_ema, close, EMA_REGIME)
    if state.equity > _peak_equity:
        _peak_equity = state.equity
    if _cooldown > 0:
        _cooldown -= 1

    # Warm-up batches only build history: every order decided on one is
    # rejected by the harness anyway, so decide nothing there.
    if state.warming_up:
        return []
    if len(_closes) < MIN_BARS:
        return []

    holding = state.positions.get(SYMBOL)
    held_qty = holding.qty if holding is not None else 0

    if held_qty > 0:
        # Track the highest close since the position opened; the trailing
        # stop is measured from it.
        if _peak_close is None or close > _peak_close:
            _peak_close = close
        # Trailing stop: the run from the peak close is over.
        if close * BPS <= _peak_close * (BPS - TRAIL_BPS):
            _peak_close = None
            return [_sell_all(held_qty)]
        # Regime break: the close has fallen through the regime EMA by more
        # than the buffer, so the uptrend the entry relied on is gone.
        if close * BPS < _ema * (BPS - REGIME_EXIT_BPS):
            _peak_close = None
            return [_sell_all(held_qty)]
        # Drawdown brake: an equity loss this deep from the peak means the
        # position and the tape disagree with the entry; cut it and park in
        # cash, so a falling market is not re-entered bar after bar.
        if _peak_equity > 0 and state.equity * BPS <= _peak_equity * (BPS - DD_BRAKE_BPS):
            _cooldown = BRAKE_COOLDOWN_BARS
            _peak_close = None
            return [_sell_all(held_qty)]
        return []

    # Flat: the peak close belongs to a position, so keep it cleared, and
    # make a single entry decision gated on every condition at once.
    _peak_close = None
    if _cooldown > 0:
        return []
    if close * BPS < _ema * (BPS + ENTRY_BPS):
        return []

    # Size: nine tenths of equity at most, never more cash than is on hand,
    # never more than the position-weight cap leaves room for.
    notional = min(state.cash, state.equity * 9 // 10, state.weight_room(SYMBOL))
    # Then cut the order until its own price impact fits the cap. Impact is
    # close to linear in size, so scale straight to the cap in one step and
    # only fall back to halving when rounding leaves the scale unchanged;
    # either way the size strictly falls, so the loop reaches the cap or the
    # floor in a few passes.
    while notional >= MIN_NOTIONAL:
        impact = state.impact_bps(SYMBOL, notional)
        if impact is None or impact <= IMPACT_CAP_BPS:
            break
        scaled = notional * IMPACT_CAP_BPS // impact
        notional = scaled if scaled < notional else notional // 2
    if notional < MIN_NOTIONAL:
        return []
    # The position opens on this decision: its peak close starts here.
    _peak_close = close
    return [{
        "side": "buy",
        "symbol": SYMBOL,
        "notional_quote_units": notional,
        "max_slippage_bps": MAX_SLIPPAGE_BPS,
    }]


if __name__ == "__main__":
    makefun_bars.run(on_batch)
