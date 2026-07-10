"""Historical options chain data: DoltHub's free `post-no-preference/
options` EOD dataset (2019+) is the primary source, Alpha Vantage
HISTORICAL_OPTIONS backfills gaps DoltHub doesn't cover. Cached to
parquet keyed by symbol+date-range so the optopsy worker (and later
oleg_eval) never re-fetches the same range twice. Sanity validators
catch a corrupted fetch/cache before it reaches the backtest engine —
never raise, the caller decides whether to reject or proceed with a
warning.

ponytail: fetch_dolthub_chain() is unverified against DoltHub's live
schema — this sandbox has no outbound network to check table/column
names against the real repo. The DoltHub SQL-API URL shape itself
(`/api/v1alpha1/{owner}/{repo}/{branch}?q=<SQL>`) is DoltHub's stable,
documented public contract; the query string inside is the part to
verify on first real use.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx
import pandas as pd

DOLTHUB_OWNER = "post-no-preference"
DOLTHUB_REPO = "options"
DOLTHUB_API = f"https://www.dolthub.com/api/v1alpha1/{DOLTHUB_OWNER}/{DOLTHUB_REPO}/main"

REQUIRED_COLUMNS = {"underlying_symbol", "quote_date", "expiration", "strike", "option_type", "bid", "ask"}


def validate_chain_data(df: pd.DataFrame) -> list[str]:
    """[] when safe to backtest against; otherwise the problems found."""
    errors: list[str] = []
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        errors.append(f"missing required column(s): {', '.join(sorted(missing))}")
        return errors  # nothing else is checkable without the columns

    if df.empty:
        errors.append("no rows")
        return errors

    if (df["bid"] < 0).any() or (df["ask"] < 0).any():
        errors.append("negative bid/ask found")
    if (df["ask"] < df["bid"]).any():
        errors.append("ask < bid on at least one row")
    if (df["strike"] <= 0).any():
        errors.append("non-positive strike found")
    if not df["option_type"].isin(["C", "P"]).all():
        errors.append("option_type values outside {'C', 'P'}")
    dup_keys = ["underlying_symbol", "quote_date", "expiration", "strike", "option_type"]
    if df.duplicated(subset=dup_keys).any():
        errors.append("duplicate rows for the same symbol/date/expiration/strike/type")
    if (pd.to_datetime(df["expiration"]) < pd.to_datetime(df["quote_date"])).any():
        errors.append("expiration before quote_date on at least one row")
    return errors


def cache_path(cache_dir: Path, symbol: str, start: str, end: str) -> Path:
    return cache_dir / f"{symbol.upper()}_{start}_{end}.parquet"


def load_cached(cache_dir: Path, symbol: str, start: str, end: str) -> pd.DataFrame | None:
    path = cache_path(cache_dir, symbol, start, end)
    return pd.read_parquet(path) if path.exists() else None


def save_cache(cache_dir: Path, symbol: str, start: str, end: str, df: pd.DataFrame) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_dir, symbol, start, end)
    df.to_parquet(path)
    return path


async def fetch_dolthub_chain(symbol: str, start: str, end: str) -> pd.DataFrame:
    """One HTTP GET against DoltHub's public SQL-API. Unverified table/
    column names this pass — see module docstring."""
    sql = (
        f"SELECT * FROM option_chain WHERE act_symbol = '{symbol.upper()}' "
        f"AND date >= '{start}' AND date <= '{end}'"
    )
    url = f"{DOLTHUB_API}?q={quote(sql)}"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    return pd.DataFrame(payload.get("rows", []))
