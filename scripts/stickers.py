import logging
import json
from html.parser import HTMLParser
from urllib.parse import unquote
from pathlib import Path

import requests

FIELDS_TO_COPY = [
    "avatar",
    "momotalk",
    "name_en",
    "name_jp",
    "name_zh",
    "nicknames",
    "sticker_download_flag",
]

# Manual mapping for inconsistent GameKee IDs
FUCK_GAMEKEE_ALIAS = {
    # Gamekee 的别名体系完全不规范，不是括号缺了就是根本没填 (ー`´ー)
    # student id: gamekee id
    10025: 60697,  # シュン（幼女）
    10101: 155638,  # サオリ（水着）
    10103: 160537,  # マリナ（チーパオ）
    10108: 172184,  # ユウカ（パジャマ）
    10109: 172185,  # ノア（パジャマ）
    26011: 130764,  # 佐天涙子
    26014: 645822,  # カリン（制服）
    10111: 173926,  # ネル（制服）
    20041: 173927,  # リオ
    20043: 650981,  # イズミ（正月）
}

# URL replacement patterns for local storage
REPLACE_STR = {
    "https://static.kivo.wiki/images": "/kivo",
    "https://cdnimg-v2.gamekee.com/wiki2.0/images": "/gamekee",
}

STICKER_DIR = Path("Stories/")
ID_MAP_PATH = Path("scripts/id_map.json")


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"


# Custom logger class with colors and emojis
class ColoredLogger(logging.Logger):
    def __init__(self, name):
        super().__init__(name)

    def info(self, msg, *args, **kwargs):
        super().info(f" {msg}", *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        super().warning(f"{Colors.YELLOW} ⚠️  {msg}{Colors.RESET}", *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        super().error(f"{Colors.RED}❌ {msg}{Colors.RESET}", *args, **kwargs)

    def success(self, msg, *args, **kwargs):
        self.info(f"{Colors.CYAN}✨ {msg}{Colors.RESET}", *args, **kwargs)


# Configure logging
logging.setLoggerClass(ColoredLogger)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class Gamekee:
    """
    Handles interaction with GameKee API and student data processing.
    Responsible for fetching and mapping student information.
    """

    def __init__(self) -> None:
        # Initialize headers for GameKee API requests
        self.gamekee_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            "game-id": "0",
            "game-alias": "ba",
        }
        self.get_list()

    def request_gamekee_list(self):
        """
        Fetches student list from GameKee API.
        """
        try:
            url = "https://ba.gamekee.com/v1/wiki/entry"
            response = requests.get(url, headers=self.gamekee_headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch data from {url}: {str(e)}")
            raise e

    def get_list(self):
        logger.info("🔍 Starting to fetch GameKee student list")
        entry_list = self.request_gamekee_list()["data"]["entry_list"]
        学生图鉴 = next(x for x in entry_list if x["id"] == 23941)["child"]
        所有学生 = next(x for x in 学生图鉴 if x["id"] == 49443)["child"]

        self.student_alias_list = {
            student["content_id"]: [student["name"]] + student["name_alias"].split(",")
            for student in 所有学生
        }

        logger.success(
            f"Successfully fetched GameKee student list, total students: {len(self.student_alias_list)}"
        )

    def _generate_name_variants(self, name):
        """
        Generates different variations of student names to improve matching.
        """
        variants = [
            name,
            name.translate(str.maketrans("（）", "()")),
            name.replace("（", " (").replace("）", " )"),
            name.replace("＊", "*"),
        ]
        return variants

    def fill_gamekee_id(self, id_map):
        not_found_count = 0
        find_first = lambda name_variants: next(
            (
                key
                for (key, alias_list) in self.student_alias_list.items()
                if any(variant in alias_list for variant in name_variants)
            ),
            None,
        )

        for key in id_map:
            item = id_map[key]
            name = item["name_jp"]

            if int(key) in FUCK_GAMEKEE_ALIAS:
                id_map[key] = {
                    "kivo_id": item["kivo_id"],
                    "gamekee_id": FUCK_GAMEKEE_ALIAS[int(key)],
                    **{k: item[k] for k in FIELDS_TO_COPY},
                }
                continue

            name_variants = self._generate_name_variants(name)
            if search_result := find_first(name_variants):
                id_map[key] = {
                    "kivo_id": item["kivo_id"],
                    "gamekee_id": search_result,
                    **{k: item[k] for k in FIELDS_TO_COPY},
                }
            else:
                not_found_count += 1
                print(f"No match found: {key}, {name}")
                logger.warning(f"No match found: {key}, {name}")

        logger.success(
            f"gamekee ID map built, total unmatched students: {not_found_count}"
        )
        return id_map


class ImageURLExtractor(HTMLParser):
    """Extracts character face diff image URLs from HTML content.

    equals to javascript:
    img_list = document.querySelector("div.swiper-container:nth-child(3) > div:nth-child(1)").children
    img_list.forEach(ele=>console.log(ele.children[0].src))
    """

    def __init__(self):
        super().__init__()
        self.image_urls = []
        self.in_target_div = False
        self.div_depth = 0
        self.swiper_container_count = 0

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            attrs = dict(attrs)
            if "class" in attrs and "swiper-container" in attrs["class"]:
                self.swiper_container_count += 1
            if self.swiper_container_count == 2 and self.div_depth == 0:
                self.in_target_div = True
            if self.in_target_div:
                self.div_depth += 1
        elif tag == "img" and self.in_target_div:
            for attr in attrs:
                if attr[0] == "src":
                    self.image_urls.append("https:" + attr[1])

    def handle_endtag(self, tag):
        if tag == "div" and self.in_target_div:
            self.div_depth -= 1
            if self.div_depth == 0:
                self.in_target_div = False
                self.swiper_container_count = 0


class StickerFetcher:
    """
    Handles fetching stickers from both GameKee and Kivo sources.
    Manages download status and storage of sticker URLs.
    """

    def __init__(self, id_map) -> None:
        self.gamekee_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            "game-id": "0",
            "game-alias": "ba",
        }
        self.id_map = id_map

    def request_gamekee_page(self, content_id):
        url = f"https://www.gamekee.com/ba/{content_id}.html"
        response = requests.get(url, headers=self.gamekee_headers)
        if response.status_code != 200:
            logger.error(
                f"Failed to get student page for gamekee {content_id}, status code: {response.status_code}"
            )
            with open(ID_MAP_PATH, "w", encoding="utf-8") as f:
                json.dump(self.id_map, f, indent=4, ensure_ascii=False)
            raise Exception("Failed to get student page")
        return response.text

    def get_gamekee_sticker(self, student_id):
        logger.info(f"🔄 Starting to fetch stickers for gamekee_id[{student_id}]")
        try:
            id = self.id_map[student_id]["gamekee_id"]
            html = self.request_gamekee_page(id)

            parser = ImageURLExtractor()
            parser.feed(html)
            self.id_map[student_id]["sticker_download_flag"][1] = True
            logger.info(
                f"✅ Successfully fetched stickers for gamekee_id[{student_id}], total stickers: {len(parser.image_urls)}"
            )
            return parser.image_urls
        except:
            logger.error(
                f"Failed to fetch stickers for gamekee_id[{student_id}], return empty []"
            )
            return []
            

    def request_kivo_data(self, id):
        url = f"https://api.kivo.wiki/api/v1/data/students/{id}"
        response = requests.get(url)
        if response.status_code != 200:
            url = f"https://api.kivo.fun/api/v1/data/students/{id}"
            response = requests.get(url)
            if response.status_code != 200:
                logger.error(
                    f"Failed to get student page for kivo {id}, status code: {response.status_code}"
                )
                with open(ID_MAP_PATH, "w", encoding="utf-8") as f:
                    json.dump(self.id_map, f, indent=4, ensure_ascii=False)
                raise Exception("Fail to request data")
        data = response.json()
        if data["code"] != 2000:
            raise Exception(f"Fail to response, codename {data['codename']}")
        return data["data"]

    def get_kivo_stickers(self, student_id):
        logger.info(f"🔄 Starting to fetch stickers for kivo_id[{student_id}]")
        id = self.id_map[student_id]["kivo_id"]
        data = self.request_kivo_data(id)
        result = []
        for sticker_list in data["gallery"]:
            # if sticker_list["title"] not in ["相关图像", "角色图像", "资料图像", "图像资料"]
            if "图像" not in sticker_list["title"]:
                result += [unquote("https:" + i) for i in sticker_list["images"]]
        self.id_map[student_id]["sticker_download_flag"][0] = True
        logger.info(
            f"✅ Successfully fetched stickers for kivo_id[{student_id}], total stickers: {len(result)}"
        )
        return result


def replace_str(url):
    for old, new in REPLACE_STR.items():
        if url.startswith(old):
            url = url.replace(old, new)
    return url


if __name__ == "__main__":
    """
    Main execution flow:
    1. Load existing ID mappings
    2. Update GameKee IDs
    3. Fetch and save stickers for each student
    4. Update download status flags
    """
    with open(ID_MAP_PATH, "r", encoding="utf-8") as f:
        id_map = json.loads(f.read())

    sort_by_key = lambda table: dict(sorted(table.items()))
    gamekee = Gamekee()
    id_map = gamekee.fill_gamekee_id(id_map)

    sticker = StickerFetcher(id_map)
    for key in id_map:
        sticker_flag_kivo, sticker_flag_gamekee = id_map[key]["sticker_download_flag"]
        stickers = []
        if not sticker_flag_kivo or not sticker_flag_gamekee:
            stickers.extend(sticker.get_gamekee_sticker(key))
            stickers.extend(sticker.get_kivo_stickers(key))

            path = STICKER_DIR / key
            path.mkdir(parents=True, exist_ok=True)
            with open(path / "Stickers.json", "w", encoding="utf-8") as f:
                stickers = [replace_str(i) for i in stickers]
                json.dump(stickers, f, indent=4, ensure_ascii=False)
            logger.success(
                f"Successfully saved stickers for {Colors.RED}{key}-{id_map[key]['name_jp']}{Colors.RESET}, total stickers: {len(stickers)}"
            )

    with open(ID_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(id_map, f, indent=4, ensure_ascii=False)
