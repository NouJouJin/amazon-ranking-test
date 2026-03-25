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

# スポンサー判定で使うテキスト
_SPONSORED_TEXTS = {"スポンサー", "Sponsored"}


def _sponsored_reason(item) -> str | None:
    """
    広告商品かどうかを判定し、該当する場合は理由を返す。
    非広告の場合は None を返す。
    """
    # パターン1: data-component-type 属性（最も確実）
    if item.get("data-component-type") == "sp-sponsored-result":
        return "data-component-type=sp-sponsored-result"

    # パターン2: data-ad-details 属性
    if item.get("data-ad-details"):
        return "data-ad-details attribute"

    # パターン3: AdHolder クラス
    classes = " ".join(item.get("class", []))
    if "AdHolder" in classes:
        return "AdHolder class"

    # パターン4: CSSセレクタで広告ラベル要素を探す
    sponsored_nodes = item.select(
        "span.puis-sponsored-label-text, "
        "span[class*='sponsored-label'], "
        "div[data-component-type='sp-sponsored-result'], "
        "i[class*='sponsored']"
    )
    if sponsored_nodes:
        return f"CSS selector match: {sponsored_nodes[0]}"

    # パターン5: aria-label で「スポンサー」を含む要素
    for tag in item.find_all(True, attrs={"aria-label": True}):
        if tag["aria-label"].strip() in _SPONSORED_TEXTS:
            return f"aria-label: {tag['aria-label']}"

    # パターン6: span タグの直接テキストのみで「スポンサー」を判定
    # ※ get_text() は子孫要素のテキストも含むため organic item を誤検出する原因になる
    # ※ tag.string は直下に文字列のみを持つ要素だけを対象にするため安全
    for tag in item.find_all("span"):
        if tag.string and tag.string.strip() in _SPONSORED_TEXTS:
            return f"span text match: {tag.string.strip()!r}"

    return None


def is_sponsored(item, debug: bool = False) -> bool:
    reason = _sponsored_reason(item)
    if reason and debug:
        logger.debug(f"    [広告判定] {item.get('data-asin', '?')} → {reason}")
    return reason is not None


def fetch_page(
    keyword: str, page: int, delay: float, debug: bool = False, debug_dir: str = "debug"
) -> BeautifulSoup | None:
    """指定ページの検索結果を取得してパースする"""
    params = {"k": keyword, "page": page}
    try:
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

        # デバッグモード: HTMLをファイルに保存して目視確認できるようにする
        if debug:
            import os
            os.makedirs(debug_dir, exist_ok=True)
            safe_kw = keyword.replace(" ", "_")
            path = os.path.join(debug_dir, f"{safe_kw}_page{page}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info(f"  [DEBUG] HTMLを保存しました: {path}")

        return BeautifulSoup(response.text, "html.parser")

    except requests.RequestException as e:
        logger.error(f"  ページ取得エラー: {e}")
        return None


def find_rank(
    keyword: str,
    target_asin: str,
    max_pages: int,
    delay: float,
    debug: bool = False,
) -> int | None:
    """
    キーワードで検索し、広告除外後の順位を返す。
    見つからない場合は None を返す。
    """
    organic_rank = 0

    for page in range(1, max_pages + 1):
        soup = fetch_page(keyword, page, delay, debug=debug)
        if soup is None:
            break

        # data-index を持つ要素のみ対象（ネストした子要素を除外）
        # data-index はAmazonが検索結果の各アイテムに付与する連番
        items = soup.select("div[data-asin][data-index]")
        if not items:
            # フォールバック: data-index がない場合は data-asin のみで取得
            items = [
                el for el in soup.select("div[data-asin]")
                if el.get("data-asin")  # 空文字除外
            ]

        if not items:
            logger.info(f"  ページ{page}に商品が見つかりませんでした。検索終了。")
            break

        for item in items:
            asin = item.get("data-asin", "")
            if not asin:
                continue

            if is_sponsored(item, debug=debug):
                logger.info(f"  [広告スキップ] {asin}")
                continue

            organic_rank += 1
            logger.info(f"  自然順位 {organic_rank}: {asin}")

            if asin == target_asin:
                logger.info(f"  発見！ 自然検索順位: {organic_rank}位")
                return organic_rank

    logger.info(f"  {max_pages}ページ内に対象商品が見つかりませんでした（圏外）")
    return None
