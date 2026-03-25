import time
import random
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

AMAZON_BASE_URL = "https://www.amazon.co.jp/s"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xhtml;q=0.9,*/*;q=0.8",
}


def is_sponsored(item) -> bool:
    """広告（スポンサー）商品かどうかを判定する"""
    # パターン1: data-component-type 属性
    if item.get("data-component-type") == "sp-sponsored-result":
        return True

    # パターン2: スポンサーラベルのテキスト
    sponsored_labels = item.select(
        "span.puis-sponsored-label-text, "
        "span[class*='sponsored'], "
        "div[data-component-type='sp-sponsored-result']"
    )
    if sponsored_labels:
        return True

    # パターン3: テキストで「スポンサー」を含む要素
    for tag in item.find_all(["span", "div"], string=True):
        text = tag.get_text(strip=True)
        if text in ("スポンサー", "Sponsored"):
            return True

    return False


def fetch_page(keyword: str, page: int, delay: float) -> BeautifulSoup | None:
    """指定ページの検索結果を取得してパースする"""
    params = {"k": keyword, "page": page}
    try:
        # ランダムな遅延でbot検出を回避
        sleep_time = delay + random.uniform(0.5, 1.5)
        logger.info(f"  ページ{page}を取得中（{sleep_time:.1f}秒待機）...")
        time.sleep(sleep_time)

        response = requests.get(
            AMAZON_BASE_URL, params=params, headers=HEADERS, timeout=15
        )
        response.raise_for_status()

        # CAPTCHAページの検出
        if "robot" in response.url or "captcha" in response.text.lower():
            logger.warning("  CAPTCHAが検出されました。しばらく時間をおいて再実行してください。")
            return None

        return BeautifulSoup(response.text, "html.parser")

    except requests.RequestException as e:
        logger.error(f"  ページ取得エラー: {e}")
        return None


def find_rank(keyword: str, target_asin: str, max_pages: int, delay: float) -> int | None:
    """
    キーワードで検索し、広告除外後の順位を返す。
    見つからない場合は None を返す。
    """
    organic_rank = 0  # 広告除外後のカウンター

    for page in range(1, max_pages + 1):
        soup = fetch_page(keyword, page, delay)
        if soup is None:
            break

        # 検索結果の商品リストを取得
        items = soup.select("div[data-asin]")
        if not items:
            logger.info(f"  ページ{page}に商品が見つかりませんでした。検索終了。")
            break

        for item in items:
            asin = item.get("data-asin", "")
            if not asin:
                continue

            if is_sponsored(item):
                logger.debug(f"  スキップ（広告）: {asin}")
                continue

            organic_rank += 1
            logger.debug(f"  自然順位 {organic_rank}: {asin}")

            if asin == target_asin:
                logger.info(f"  発見！ 自然検索順位: {organic_rank}位")
                return organic_rank

    logger.info(f"  {max_pages}ページ内に対象商品が見つかりませんでした（圏外）")
    return None
