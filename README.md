# Roostoo Quant Trading Bot

Production-ready starter bot for the Roostoo Quant Trading Hackathon.

## Security rules

- Secrets are read only from environment variables.
- Never hardcode API credentials.
- Never commit `.env` or `roostooAPI.txt`.

## Files

- `main.py`: autonomous loop orchestration
- `config.py`: env loading and validation
- `api_client.py`: signed API requests + retries/backoff + throttling
- `strategy.py`: selectable strategy modes (`ma_momentum` or `dip_ladder`)
- `risk.py`: risk and exchange rule checks
- `execution.py`: safe execution, DRY_RUN, duplicate/pending guards
- `adaptive.py`: live PnL tracking + auto-tuning for strategy/risk aggressiveness
- `logger.py`: console + file logging (`logs/bot.log`)
- `utils.py`: shared utility helpers
- `.env.example`: safe config template
- `requirements.txt`: dependencies
- `.gitignore`: secret/log/artifact protection

## Strategy

- Build rolling price history from `GET /v3/ticker` polling.
- `STRATEGY_MODE=ma_momentum`:
  - `BUY` on bullish MA crossover with positive momentum.
  - Bearish cross is treated as hold unless exit model is triggered.
- `STRATEGY_MODE=dip_ladder`:
  - Enter first tranche after pullback + small rebound confirmation.
  - Add more tranches only if price dips below last buy by `DIP_STEP_PCT`.
  - Keep holding until exit model triggers.
- Exit model for both modes:
  - Hard stop-loss.
  - Take-profit is armed, then trailing-stop exit.
  - Optional minimum hold time (`MIN_HOLD_SECONDS`) to avoid flip-selling.
- Adaptive tuner monitors portfolio/trade outcomes and adjusts aggressiveness.

## Risk controls

- Max USD exposure (`MAX_POSITION_USD`)
- Minimum cash reserve (`MIN_CASH_RESERVE_USD`)
- Cooldown between trades (`COOLDOWN_SECONDS`)
- Enforce pair constraints from `exchangeInfo`:
  - minimum order (`MiniOrder`/`minOrder`)
  - amount precision (`AmountPrecision`)
- Spot only behavior, no leverage, no shorting logic

## API compliance

Base URL:
- `https://mock-api.roostoo.com`

Supported endpoints:
- `GET /v3/serverTime`
- `GET /v3/exchangeInfo`
- `GET /v3/ticker`
- `GET /v3/balance`
- `GET /v3/pending_count`
- `POST /v3/place_order`
- `POST /v3/query_order`
- `POST /v3/cancel_order`

Signed requests:
- Headers: `RST-API-KEY`, `MSG-SIGNATURE`
- Param: `timestamp` in milliseconds
- Signature: HMAC SHA256 over sorted parameter string
- POST uses `Content-Type: application/x-www-form-urlencoded`

## Runtime behavior

- Autonomous infinite loop with exception safety
- Conservative polling interval
- Rate-aware design and client throttling (`MAX_CALLS_PER_MINUTE`, default 30)
- Retries with exponential backoff and timeout handling
- Malformed JSON handling
- Structured logs for market fetches, signals, orders, API failures, portfolio snapshots
- Trade outcome logs (`win`/`loss`) and adaptive reconfiguration logs

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in real values (API key/secret, pair, risk settings).
3. Start with `DRY_RUN=true`.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Run on EC2 with tmux

```bash
tmux new -s roostoo-bot
source .venv/bin/activate
python main.py
# Detach: Ctrl+B then D
# Reattach: tmux attach -t roostoo-bot
```

## Notes on `roostooAPI.txt`

If `roostooAPI.txt` exists, treat it only as a temporary local reference for manually populating `.env`, then ignore it in git.
