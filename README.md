# argus-telemetry

The eye's first live nerve. Every ~30 minutes a GitHub Action reads public
meme-market telemetry (CoinGecko category "meme-token": sector cap, 24h
volume, 24h change, breadth of the top 50, average 7d change, top 10
symbols) and appends one JSON line to `data/telemetry.jsonl`.

It holds no keys, no wallet, no broker credentials, and no third-party
actions beyond GitHub's own checkout. The worst this repository could
ever leak is public numbers. Failed reads are recorded inside the row
(`_errors`), never hidden: a blind pass testifies to its blindness.

## Set up (about five minutes, once)

1. Create a public repository under the `dogcodeai` organization named
   `argus-telemetry`.
2. Upload these files, keeping the paths:
   `collector.py`, `.github/workflows/collector.yml`, `data/.gitkeep`,
   `README.md`.
3. Settings > Actions > General > Workflow permissions: choose
   "Read and write permissions" (the Action commits the data file).
4. Actions tab > `argus-telemetry` > "Run workflow" once by hand.
   Within a minute `data/telemetry.jsonl` gains its first line.
5. Nothing else. The schedule (`*/30 * * * *`) runs from then on.
   GitHub may skip scheduled runs on quiet repositories after 60 days
   of no commits; the Action's own commits keep it alive.

## Verify it is working

Open `data/telemetry.jsonl`. The newest line carries `ts`, `sector`
fields, `breadth` fields and an `_errors` list that should be empty.
Two lines fewer than 20 minutes apart never appear (dedup guard).

## Local check without network

    python3 collector.py --selftest

## What reads it

The Cerberus/Argus session reads the raw file by URL
(`https://raw.githubusercontent.com/dogcodeai/argus-telemetry/main/data/telemetry.jsonl`)
for the weekly review and, after 90 days, the December verdict on the
meme thesis. Layer 2 (the VPS daemon) will push its daily digest to a
`digests/` folder in this same repository.

## What this is not

Not a trading bot. Not connected to any exchange, wallet, or account.
Never runs on the Cerberus machine. Real money in memes stays at zero
until the December verdict, and after that only by signature.
