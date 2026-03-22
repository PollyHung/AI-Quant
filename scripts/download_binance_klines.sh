#!/usr/bin/env bash
set -euo pipefail

# Download Binance Vision Spot kline ZIP files for selected symbols/intervals.
# Source: https://data.binance.vision/

BASE_URL="https://data.binance.vision/data/spot"
DATA_DIR="data/raw/binance/spot/klines"

# Defaults (override via env):
SYMBOLS="${SYMBOLS:-BTCUSDT ETHUSDT}"
INTERVALS="${INTERVALS:-1m 5m}"

# Start with 12 months for quick strategy tuning.
MONTHS="${MONTHS:-2025-04 2025-05 2025-06 2025-07 2025-08 2025-09 2025-10 2025-11 2025-12 2026-01 2026-02 2026-03}"
# Add a few recent daily files to stay current.
DAYS="${DAYS:-2026-03-19 2026-03-20 2026-03-21 2026-03-22}"

mkdir -p "${DATA_DIR}"

echo "Downloading monthly files..."
for symbol in ${SYMBOLS}; do
  for interval in ${INTERVALS}; do
    target_dir="${DATA_DIR}/${symbol}/${interval}"
    mkdir -p "${target_dir}"

    for ym in ${MONTHS}; do
      file="${symbol}-${interval}-${ym}.zip"
      url="${BASE_URL}/monthly/klines/${symbol}/${interval}/${file}"
      echo "[monthly] ${file}"
      wget -q -nc -O "${target_dir}/${file}" "${url}" || {
        echo "warn: missing ${url}" >&2
        rm -f "${target_dir}/${file}" || true
      }
    done
  done
done

echo "Downloading daily files..."
for symbol in ${SYMBOLS}; do
  for interval in ${INTERVALS}; do
    target_dir="${DATA_DIR}/${symbol}/${interval}"
    mkdir -p "${target_dir}"

    for day in ${DAYS}; do
      file="${symbol}-${interval}-${day}.zip"
      url="${BASE_URL}/daily/klines/${symbol}/${interval}/${file}"
      echo "[daily] ${file}"
      wget -q -nc -O "${target_dir}/${file}" "${url}" || {
        echo "warn: missing ${url}" >&2
        rm -f "${target_dir}/${file}" || true
      }
    done
  done
done

echo "Done. Files saved under ${DATA_DIR}"
