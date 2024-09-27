import requests
from html.parser import HTMLParser
import json
from pathlib import Path
import logging
import re
from urllib.parse import unquote
from functools import cached_property

# name fixing table
FIX_GAMEKEE_ALIAS = {
    "60697": ["シュン", "シュン（幼女）"],
    "155638": ["サオリ（水着", "サオリ（水着）"],
    "130764": ["Saten Ruiko", "Saten Ruiko,佐天涙子"],
}
FIX_KIVO_NAME = {
    "ミク": "初音ミク",
    "美琴": "御坂美琴",
    "操祈": "食蜂操祈",
    "涙子": "佐天涙子",
}
FIX_KIVO_SKIN = {"骑行服": "骑行", "私服": "便服", "体育服": "运动服"}

errors = []


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
        super().info(f"{Colors.GREEN} {msg}{Colors.RESET}", *args, **kwargs)

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


class BlueRequest:
    def __init__(self) -> None:
        self.gamekee_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            "game-id": "0",
            "game-alias": "ba",
        }

    @cached_property
    def request_gamekee_list(self):
        url = "https://ba.gamekee.com/v1/wiki/entry"
        response = requests.get(url, headers=self.gamekee_headers)
        if response.status_code != 200:
            logger.error(
                f"Failed to get gamekee student list, status code: {response.status_code}"
            )
            raise Exception("Failed to get student list")
        return response.json()["data"]["entry_list"]

    @cached_property
    def request_kivo_list(self):
        url = "https://api.kivo.fun/api/v1/data/students/?page=1&page_size=5000&name="
        response = requests.get(url)
        if response.status_code != 200:
            logger.error(
                f"Failed to get kivo student list, status code: {response.status_code}"
            )
            raise Exception("Fail to request data")
        data = response.json()
        if data["code"] != 2000:
            raise Exception(f"Fail to response, codename {data['codename']}")
        return response.json()["data"]["students"]

    def request_schale_list(self, lng="jp"):
        url = f"https://schaledb.com/data/{lng}/students.min.json"
        response = requests.get(url)
        if response.status_code != 200:
            logger.error(
                f"Failed to get SchaleDB student list, status code: {response.status_code}"
            )
            raise Exception("Failed to get SchaleDB student list")
        return response.json()

    def request_gamekee_page(self, content_id):
        url = f"https://www.gamekee.com/ba/{content_id}.html"
        response = requests.get(url, headers=self.gamekee_headers)
        if response.status_code != 200:
            logger.error(
                f"Failed to get student page for {content_id}, status code: {response.status_code}"
            )
            raise Exception("Failed to get student page")
        return response.text

    def request_kivo_data(self, id):
        url = f"https://api.kivo.wiki/api/v1/data/students/{id}"
        response = requests.get(url)
        if response.status_code != 200:
            url = f"https://api.kivo.fun/api/v1/data/students/{id}"
            response = requests.get(url)
            if response.status_code != 200:
                raise Exception("Fail to request data")
        data = response.json()
        if data["code"] != 2000:
            raise Exception(f"Fail to response, codename {data['codename']}")
        return data["data"]


class Schale:
    def __init__(self) -> None:
        self.ba = BlueRequest()

    @property
    def student_list(self):
        return self.get_list_gamkee

    def get_list(self, name):
        logger.info("🔍 Starting to fetch SchaleDB student list")

        if name == "kivo":
            student_list = self.get_list_kivo
        elif name == "gamekee":
            student_list = self.get_list_gamkee

        logger.success(
            f"Successfully fetched SchaleDB student list, total students: {len(student_list)}"
        )
        return student_list

    @cached_property
    def get_list_gamkee(self):
        data = self.ba.request_schale_list()
        student_list = {key: item["Name"] for (key, item) in data.items()}
        return student_list

    @cached_property
    def get_list_kivo(self):
        res_jp = self.ba.request_schale_list("jp")
        res_zh = self.ba.request_schale_list("zh")

        student_list = {}
        for key in res_jp:
            jp_name = res_jp[key]["Name"]
            zh_name = res_zh[key]["Name"]

            student_name = jp_name
            pattern = r"(.*?)（(.*)）"
            if re.search(pattern, zh_name):
                name = re.search(pattern, jp_name).group(1)
                skin = re.search(pattern, zh_name).group(2)
                student_name = f"{name}（{skin}）"

            student_list[key] = student_name

        return student_list


class SiteTool:
    def __init__(self, name) -> None:
        self.ba = BlueRequest()
        self.schale_fetcher = Schale()
        self.name = name

        assert self.name in ["gamekee", "kivo"], f"Invalid site name: {self.name}"

        logger.info(f"🚀 Starting to process {self.name} student data")
        self.schale_student_list = self.schale_fetcher.get_list(self.name)
        self.student_list = self.get_list()

        logger.info(f"🔗 Starting to build schale-{self.name} ID mapping table")
        self.maptable = self.build_table(self.student_list, self.schale_student_list)

    @property
    def table(self):
        return self.maptable

    def get_list(self):
        pass

    def build_table(self, student_list, schale_student_list):
        pass

    def get_stickers(self, id):
        pass


class Kivo(SiteTool):
    def __init__(self) -> None:
        super().__init__("kivo")

    @staticmethod
    def _fix_kivo_name(name):
        for key, value in FIX_KIVO_NAME.items():
            if key == name:
                logger.info(
                    f"📝 Correcting name alias for student name {key} -> {value}"
                )
                return name.replace(key, value)
        return name

    @staticmethod
    def _fix_kivo_skin(skin):
        for key, value in FIX_KIVO_SKIN.items():
            if key == skin:
                logger.info(
                    f"📝 Correcting name alias for student skin {key} -> {value}"
                )
                return skin.replace(key, value)
        return skin

    @staticmethod
    def _replace_domain(result):
        result = [
            item.replace("https://static.kivo.fun/images", "/kivo")
            .replace("https://static.kivo.wiki/images", "/kivo")
            for item in result
        ]
        return result

    def get_list(self):
        students = self.ba.request_kivo_list
        student_list = {}
        for student in students:
            student_name = self._fix_kivo_name(student["given_name_jp"])
            if student["skin"]:
                student_name += f"（{self._fix_kivo_skin(student['skin'])}）"
            student_list[student["id"]] = student_name
        return student_list

    def build_table(self, kivo_student_list, schale_student_list):
        global errors
        schale_kivo_table = {}
        not_found_count = 0
        for key, name in schale_student_list.items():
            search_result = [k for k, v in kivo_student_list.items() if v == name]
            if len(search_result) == 1:
                logger.info(f"🔍 Match found: {key} <- {name} -> {search_result[0]}")
                schale_kivo_table[key] = search_result[0]
            else:
                not_found_count += 1
                errors.append(f"{key} - {name}")
                logger.warning(f"No match found: {key}, {name}")

        logger.success(
            f"schale-kivo ID mapping table built, total unmatched students: {not_found_count}"
        )

        return schale_kivo_table

    def get_stickers(self, id):
        logger.info(f"🔄 Starting to fetch stickers for kivo_id[{id}]")
        data = self.ba.request_kivo_data(id)
        result = []
        for sticker_list in data["gallery"]:
            # if sticker_list["title"] not in ["相关图像", "角色图像", "资料图像", "图像资料"]
            if "图像" not in sticker_list["title"]:
                result += [unquote("https:" + i) for i in sticker_list["images"]]
        logger.info(
            f"✅ Successfully fetched stickers for kivo_id[{id}], total stickers: {len(result)}"
        )
        result = self._replace_domain(result)
        return result


class Gamekee(SiteTool):
    def __init__(self):
        super().__init__("gamekee")

    @staticmethod
    def _fix_gamkee_alias(student):
        for key, value in FIX_GAMEKEE_ALIAS.items():
            if student["id"] == int(key):
                logger.info(f"📝 Correcting name alias for student {student['id']}")
                student["name_alias"] = student["name_alias"].replace(
                    value[0], value[1]
                )
                return student
        return student

    @staticmethod
    def _replace_domain(result):
        result = [
            item.replace("https://cdnimg-v2.gamekee.com/wiki2.0/images", "/gamekee")
            for item in result
        ]
        return result

    def _generate_name_variants(self, name):
        variants = [
            name,
            name.replace("（", "(").replace("）", ")"),
            name.replace("（", " (").replace("）", ")"),
            name.replace("＊", "*"),
        ]
        return variants

    def get_list(self):
        logger.info("🔍 Starting to fetch GameKee student list")
        entry_list = self.ba.request_gamekee_list
        student_list = [i for i in entry_list if i["id"] == 23941][0]["child"]
        student_list = [i for i in student_list if i["id"] == 49443][0]["child"]
        student_list = [self._fix_gamkee_alias(i) for i in student_list]
        logger.success(
            f"Successfully fetched GameKee student list, total students: {len(student_list)}"
        )
        return student_list

    def build_table(self, gamkee_list, schale_list):
        global errors
        student_alias_list = {
            student["content_id"]: [student["name"]] + student["name_alias"].split(",")
            for student in gamkee_list
        }

        not_found_count = 0
        schale_gamekee_table = {}
        for key, name in schale_list.items():
            name_variants = self._generate_name_variants(name)
            search_result = [
                key
                for (key, alias_list) in student_alias_list.items()
                if any(variant in alias_list for variant in name_variants)
            ]

            if len(search_result) == 1:
                logger.info(f"🔍 Match found: {key} <- {name} -> {search_result[0]}")
                schale_gamekee_table[key] = search_result[0]
            else:
                not_found_count += 1
                errors.append(f"{key} - {name}")
                logger.warning(f"No match found: {key}, {name}")

        logger.success(
            f"schale-gamekee ID mapping table built, total unmatched students: {not_found_count}"
        )

        return schale_gamekee_table

    def get_sticker(self, id):
        logger.info(f"🔄 Starting to fetch stickers for gamekee_id[{id}]")
        html = self.ba.request_gamekee_page(id)

        parser = ImageURLExtractor()
        parser.feed(html)
        logger.info(
            f"✅ Successfully fetched stickers for gamekee_id[{id}], total stickers: {len(parser.image_urls)}"
        )

        result = self._replace_domain(parser.image_urls)
        return result


if __name__ == "__main__":
    gamekee = Gamekee()
    kivo = Kivo()
    schale = Schale()

    schale_gamekee_table = gamekee.table
    schale_kivo_table = kivo.table
    schale_student_list = schale.student_list

    logger.info("💾 Starting to save student stickers")
    for key in schale_student_list:
        gamekee_id = schale_gamekee_table[key]
        kivo_id = schale_kivo_table[key]
        file_path = Path("Stories") / key / "Stickers.json"

        if not file_path.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            logger.success(f"Stickers for student {key} have saved, skipping")
            continue

        logger.info(f"🔄 Processing student {key} - {schale_student_list[key]}")
        gamekee_result = gamekee.get_sticker(gamekee_id)
        kivo_result = kivo.get_stickers(kivo_id)

        with open(file_path, "w+", encoding="utf-8") as f:
            json.dump(gamekee_result + kivo_result, f, indent=4, ensure_ascii=False)
        logger.success(f"Stickers for student {schale_student_list[key]}({key}) saved")

    logger.info("✨ All student stickers processed and saved")

    if errors:
        logger.warning("No match found: ")
        for error in errors:
            logger.warning(error)
