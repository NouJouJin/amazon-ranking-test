import argparse
import csv
import logging
import os
from datetime import datetime, timezone, timedelta

import yaml

from scraper import find_rank

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
CSV_HEADER = ["recorded_at", "keyword", "asin", "rank", "note"]


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def append_to_csv(output_path: str, rows: list[dict]) -> None:
    is_new_file = not os.path.exists(output_path)
    with open(output_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if is_new_file:
            writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="HTMLを保存し広告判定ログを詳細出力する")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    config = load_config()
    settings = config.get("settings", {})
    targets = config.get("targets", [])

    max_pages = settings.get("max_pages", 3)
    delay = settings.get("request_delay", 3)
    output_dir = settings.get("output_dir", "results")

    os.makedirs(output_dir, exist_ok=True)

    now = datetime.now(JST)
    recorded_at = now.strftime("%Y-%m-%d %H:%M:%S")
    output_path = os.path.join(output_dir, "rankings.csv")

    logger.info(f"=== Amazon ランキング取得開始: {recorded_at} ===")
    logger.info(f"追跡対象: {len(targets)} 件")

    rows = []
    for target in targets:
        keyword = target.get("keyword", "")
        asin = target.get("asin", "")

        if not keyword or not asin or asin == "XXXXXXXXXX":
            logger.warning(f"設定が不正なためスキップ: {target}")
            continue

        logger.info(f"\nキーワード「{keyword}」/ ASIN: {asin}")
        rank = find_rank(keyword, asin, max_pages=max_pages, delay=delay, debug=args.debug)

        row = {
            "recorded_at": recorded_at,
            "keyword": keyword,
            "asin": asin,
            "rank": rank if rank is not None else "",
            "note": "圏外" if rank is None else "",
        }
        rows.append(row)
        logger.info(f"  結果: {'圏外' if rank is None else f'{rank}位'}")

    append_to_csv(output_path, rows)
    logger.info(f"\n=== 完了。結果を保存しました: {output_path} ===")


if __name__ == "__main__":
    main()
