# Spinup Capital — Autonomous AI Trading Firm (MVP scaffold)

This is a working implementation of the core loop from your spec:

```
Market Event → Managing Partner → Specialist Factory (hire/reuse)
  → Trade Proposal → Bull/Bear Debate → Risk Governor
  → (Trade Surgery if rejected) → Execution Gateway → Alpaca (paper/mock)
  → Simulated Close → Autopsy → Head of Talent → Capital Reallocation
```

It runs **fully offline out of the box** (no API keys needed) so you can demo
it today, and switches to real Alpaca paper trading / a real LLM the moment
you add keys to `.env` — **no code changes required**.

## Quickstart (offline / mock mode)

```bash
cd spinup-capital
pip install -r requirements.txt     # or just: fastapi sqlalchemy pydantic python-dotenv
cp .env.example .env                # leave keys blank for mock/heuristic mode
python -m backend.demo.run_demo --events 6 --reset
```

You'll see the full narrative in your terminal: hiring, a trade proposal,
the Bull/Bear debate, a Risk Governor rejection + "trade surgery" repair,
an executed paper order, an autopsy, and a Talent Agent promote/keep/fire
decision with capital moving accordingly.

Run it again without `--reset` to keep building on the same firm state
(`spinup.db`, a local SQLite file).

## Turning on the real dashboard API

```bash
uvicorn backend.main:app --reload
```

Endpoints: `/firm/summary`, `/agents`, `/trades`, `/capital-allocations`,
`/events/scenarios`, `POST /demo/run`.

## Running the React dashboard (the org-chart / hiring-animation UI)

A working dashboard now lives in `frontend/` — an ink-navy "firm console"
with a scrolling activity ticker, a ledger-style stats strip, an org chart
with personnel badges (styled like ID badges with a rubber-stamp
PROMOTED/PROBATION/FIRED status), a trade-proposal/risk-decision feed, and
a live audit-trail log.

```bash
# terminal 1
uvicorn backend.main:app --reload

# terminal 2
cd frontend
npm install
npm run dev       # opens on http://localhost:5173
```

Click **"Run market cycle"** in the top-right to trigger `POST /demo/run`
and watch the org chart, ledger, and activity log update live. If the
backend isn't running, the dashboard falls back to static demo data
automatically so it still looks complete for screenshots/rehearsal.

## Going from MOCK to real Alpaca paper trading

1. Create a fresh Alpaca **paper** account, get an API key/secret.
2. Put them in `.env` as `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`.
3. That's it — `backend/trading/alpaca_client.py` automatically switches
   from mock fills to real calls via `alpaca-py`. Live options-chain data
   is now wired up (`get_option_chain_snapshot` calls Alpaca's real
   `OptionHistoricalDataClient.get_option_chain`) — see the notes below
   before you go live with it.

### Notes on the live options-chain wiring

- **Feed**: defaults to `indicative` (free, works on every account, no
  subscription needed). If your account has an OPRA options data
  subscription, set `ALPACA_OPTIONS_FEED=opra` in `.env` for real-time
  data instead.
- **Expiration window**: targets 14–45 days out, then picks whichever
  expiration is closest to a 21-day tenor. Adjust the window in
  `_get_live_option_chain()` if a specialist's mandate needs a different
  tenor (e.g. weekly earnings plays).
- **IV percentile is an approximation, not a true percentile.** Alpaca's
  chain snapshot gives you each contract's *current* implied volatility,
  not a historical percentile rank. This code scales the average current
  IV across the chosen expiration into a 0–100 pseudo-percentile as a
  placeholder. Since IV percentile feeds directly into the Risk
  Governor's earnings-window guard and the specialist's strategy choice,
  swap this for a real percentile rank once you're storing your own IV
  history — that's the single highest-value follow-up here.
- **Underlying price** comes from a live stock-quote call
  (`StockHistoricalDataClient.get_stock_latest_trade`) with a
  strikes-derived fallback if that call fails for any reason.
- **I could not test this against Alpaca's live servers** — my
  environment's network access doesn't include Alpaca's API domains. The
  request/response parsing was verified against alpaca-py's real
  `OptionChainRequest`/`OptionsFeed` classes and a realistic fake response
  shape (see the dry-run tests I ran while building this), and all the
  error paths (auth failure, empty chain, too few strikes, unparseable
  symbols) raise clear, specific `RuntimeError`s rather than crashing
  opaquely. But you should run it against your real account before
  relying on it for a demo — if Alpaca's OCC symbol format doesn't match
  what `_parse_chain_symbols()` expects, that function is the one place
  to fix it.
- **Options trading level**: this only affects whether `submit_mleg_order`
  succeeds (multi-leg orders need Level 3 options approval on the
  account), not the chain-data fetch above. Check/set this in your Alpaca
  dashboard's account configuration if multi-leg submission fails.

## Turning on a real LLM

Set `LLM_PROVIDER=openai` or `LLM_PROVIDER=anthropic` in `.env` and add the
matching API key. If left as `heuristic` (default), all narrative text
(thesis, bull/bear debate, autopsy) is generated by deterministic templates
instead — same code path, zero cost, fully reproducible for demo rehearsal.

## Architecture guarantees baked into the code (map back to the spec)

- **"The LLM proposes, deterministic policy decides, Alpaca executes."**
  `backend/agents/risk_governor.py` is pure Python — no LLM call in it at
  all. `backend/trading/execution.py` refuses to submit any order whose
  `RiskCheckResult.approved` is `False`.
- **Single execution choke point.** Only `alpaca_client.py` ever imports the
  Alpaca SDK; only `execution.py` ever calls `alpaca_client.py`. No
  specialist agent has a path to the broker that skips risk review.
- **Real hiring, not a hardcoded animation.** `specialist_factory.py` takes
  a `SpecialistType` + `MarketEvent` and returns a concrete `AgentSpec`
  (mandate, capital, permissions, risk budget) that gets persisted as a row
  in `agents` — this is what you'd show in the "NEW HIRE" demo screen.
- **Transparent, deterministic Talent scoring.** `agents/talent.py` uses an
  explicit weighted formula (ROI, win rate, drawdown, violations,
  consistency) printed in the module docstring — "don't hide the decision
  behind 'the LLM decided,'" per your notes.
- **Trade surgery is a real repair, not cosmetic.** `repair_proposal()` in
  `specialist_trader.py` both switches to a narrower strategy *and* scales
  the position size down until it fits the agent's risk budget.
- **Deterministic math, judgment-only LLM calls.** P&L, max loss/profit,
  Sharpe-style scoring, and capital allocation are all plain arithmetic in
  `options.py` / `talent.py`. The LLM (or heuristic fallback) is only ever
  asked for thesis text, debate text, and autopsy text.

## What's here vs. what's next (per your 7-day plan)

| Done in this scaffold | Still to build |
|---|---|
| Managing Partner routing | Bull/Bear as a true LLM debate (works today via heuristic; flip provider for real one) |
| Specialist Factory (4 templates) | Live options-chain integration for your Alpaca account tier |
| Deterministic Risk Governor | — |
| Execution Gateway + mock/live Alpaca client | — |
| React dashboard (hiring pipeline, org chart, ledger, activity log, trade feed, trading memory) | — |
| **Live dashboard updates** — polls every 5s while the tab is visible, pauses automatically when the tab is hidden or a manual "Run market cycle" is in flight, skips overlapping requests, and has a click-to-pause toggle showing "updated Xs ago"; verified against a real running backend (confirmed exact 5.0s request spacing, confirmed pause/resume actually starts/stops requests) | Swap polling for a WebSocket/SSE push if you want sub-second updates during a live demo — polling is simpler and was the right tradeoff here, but it's not instant |
| **Organizational memory** — every closed trade's autopsy produces a structured rule stored in the `lessons` table; specialists retrieve firm-wide relevant lessons (by specialist type + ticker) *before* proposing their next trade | Retrieval could get smarter — currently recency + ticker-match rank; embeddings would scale better past a few dozen lessons |
| **Agent Arena** — every newly spun-up specialist runs `ARENA_TRIALS` synthetic scenarios through the real strategy-builder and Risk Governor *before* any treasury capital is committed; candidates that don't clear the win-rate/risk-pass-rate bar are declined with zero capital spent | Historical replay instead of synthetic scenarios (feed real past price/IV data through the same gauntlet) |
| Head of Talent scoring + promote/probation/fire + capital reallocation | — |
| **Static-desk vs. Spinup control experiment** — both arms run against the identical event stream and identical simulated market outcomes (same seed per event), isolating organizational adaptation as the only variable | Feed a longer, more realistic event stream (real historical earnings/macro calendar) for a bigger, more persuasive sample |
| **Live Alpaca options-chain wiring** — real `OptionHistoricalDataClient.get_option_chain` calls, parsed and validated against realistic fake responses (see notes above); flip on by adding your keys | Untested against Alpaca's actual live servers (my environment can't reach them) — verify against your real account before a demo; replace the IV-percentile approximation with a real historical rank |
| Full offline demo script (`run_demo.py`) | Demo hardening for judge day (retry logic, deterministic seeded scenarios for a reliable live demo) |

### What the control experiment actually shows

Run it yourself: `python -m backend.demo.run_experiment --events 40`, or hit
"Run experiment" on the dashboard. Being honest about the result: **the
static desk edges out Spinup over 12–40 events**, roughly ties around 60,
and **Spinup pulls clearly ahead by 100 events** (in one run: +3.6% vs.
+1.5%, with comparable drawdown). That's a more credible story than
"Spinup always wins" — the Arena-gate and lower initial trade count mean
Spinup pays a short-term cost for governance, and the payoff (cutting
losers, compounding winners) shows up over a longer horizon. If a judge
asks "does the organization actually help or is this just a bot with an
org chart on it," this experiment — and its honest short-horizon result —
is a stronger answer than a cherry-picked demo.

### A real bug the Arena caught while building this

Worth mentioning in your pitch: while wiring the Arena, it immediately
exposed a genuine sizing bug — the vertical-spread builder wasn't scaling
its strike width to the agent's risk budget, so a specialist covering a
higher-priced underlying (SPY) failed *100% of trial proposals*, every
time, regardless of market conditions. That's exactly the failure mode the
Arena exists to catch before it costs the firm real money. Fixed now in
`specialist_trader.py` (positions size to the agent's `max_trade_risk`
before ever reaching the Risk Governor), but it's a good, honest example
of "the governance layer works" if a judge asks for proof.

## File map

```
backend/
  config.py                    # env-driven settings (mock vs live, risk limits)
  main.py                      # FastAPI dashboard API
  schemas/models.py            # Pydantic contracts (AgentSpec, TradeProposal, etc.)
  database/models.py           # SQLAlchemy tables (agents, trades, debates, capital_allocations, lessons, treasury)
  database/db.py                # engine/session + treasury helpers
  events/market_events.py      # scenario generator (swap for real news/earnings feed)
  agents/
    managing_partner.py        # event -> specialist routing
    specialist_factory.py      # AgentSpec templates + instantiation
    arena.py                    # Agent Arena — synthetic pre-capital trial gauntlet
    specialist_trader.py       # strategy choice, thesis, trade proposal, trade surgery/repair
    bull_bear.py                # debate (LLM or heuristic)
    risk_governor.py           # deterministic hard gate
    memory.py                    # organizational memory: store/retrieve lessons
    talent.py                   # deterministic promote/keep/probation/fire scoring
    autopsy.py                  # post-trade lesson extraction (narrative + structured rule)
    llm_client.py                # single LLM choke point w/ heuristic fallback
  trading/
    alpaca_client.py            # mock/live broker wrapper (only module that imports alpaca-py)
    options.py                  # deterministic strategy builders (iron condor, verticals, calendar)
    execution.py                 # execution gateway (refuses unapproved trades) + mock close simulator
  demo/
    run_demo.py                # end-to-end orchestrator / CLI demo (SQLite-backed, interactive)
    run_experiment.py          # static-desk vs. Spinup control experiment (in-memory, deterministic)
frontend/
  src/
    App.jsx                     # firm console layout
    api.js                       # fetch layer w/ offline mock fallback
    styles.css                   # design tokens (ink-navy palette, mono/display/body type)
    components/
      TickerBar.jsx              # scrolling live-activity marquee
      OrgChart.jsx                # Managing Partner + SVG connectors + badge row
      AgentBadge.jsx              # signature personnel-badge/dossier card w/ status stamp
      ActivityLog.jsx             # ledger-style audit trail
      TradeFeed.jsx                # trade proposal / risk decision cards
      MemoryPanel.jsx              # trading memory / lessons-learned cards
      ArenaPanel.jsx                # hiring pipeline — arena pass/decline log
      ExperimentPanel.jsx           # static-desk vs. Spinup equity-curve comparison
```

## Suggested next session with Claude

Good next steps to tackle one at a time:
1. "I ran the live options-chain wiring against my real Alpaca account and
   here's what broke / here's a sample response — fix `_parse_chain_symbols`
   to match."
2. "Replace the IV-percentile approximation with a real historical rank —
   I'll store daily IV snapshots for each ticker we trade."
3. "Add a Sortino ratio and profit-factor to the Talent scoring formula
   alongside the existing ROI/win-rate/drawdown weights."
4. "Swap the dashboard's polling for a WebSocket push for the live demo."
