"""Export closed candles from an already connected Windows MetaTrader 5 terminal."""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, help="Exact name in the broker's terminal")
    parser.add_argument("--alias", required=True, help="CSV prefix configured in Market Intelligence")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bars", type=int, default=1000, choices=range(50, 10001), metavar="50–10000")
    parser.add_argument("--terminal")
    args = parser.parse_args()
    if not args.alias.isascii() or not args.alias.replace(".", "").replace("-", "").replace("_", "").isalnum() or not args.alias[0].isalnum():
        parser.error("Invalid CSV prefix")

    import MetaTrader5 as mt5

    if not (mt5.initialize(args.terminal) if args.terminal else mt5.initialize()):
        raise SystemExit(f"MT5 unavailable: {mt5.last_error()}")
    try:
        if not mt5.symbol_select(args.symbol, True):
            raise SystemExit(f"Symbol unavailable: {args.symbol}")
        args.output.mkdir(parents=True, exist_ok=True)
        failures = []
        for interval in ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"):
            bars = mt5.copy_rates_from_pos(args.symbol, getattr(mt5, f"TIMEFRAME_{interval}"), 1, args.bars)
            if bars is None or not len(bars):
                failures.append(interval)
                continue
            path = args.output / f"{args.alias}_{interval}.csv"
            with NamedTemporaryFile("w", encoding="utf-8", dir=args.output, newline="", delete=False) as handle:
                temporary = Path(handle.name)
                writer = csv.writer(handle)
                writer.writerow(["time_utc", "open", "high", "low", "close", "tick_volume"])
                for bar in bars:
                    stamp = datetime.fromtimestamp(int(bar["time"]), timezone.utc).isoformat()
                    writer.writerow([stamp, *(bar[key] for key in ("open", "high", "low", "close", "tick_volume"))])
            try:
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        if failures:
            raise SystemExit("Intervals unavailable: " + ", ".join(failures))
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
