import os
import io
import re
import copy
import json
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import unquote
from dataclasses import dataclass
from typing import Any, TypedDict, Optional

import requests
from PIL import Image


# 🌍 Load environment variables and configure constants
load_dotenv()
REPO_OWNER = os.getenv("REPO_OWNER")
REPO_NAME = os.getenv("REPO_NAME")
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"
KIVO_BASE = "https://api.kivo.wiki/api/v1/data/students"
ENDPOINTS = {
    "STUDENTS_JSON": Path("Momotalk/students.json"),
    "KIVO_MAP_JSON": Path("scripts/id_map.json"),
    "AVATAR_BASE": Path("Avatars/Kivo/Released"),
    "SKIN_TABLE": Path("Momotalk/prefixTable.json"),
}
FIXED_RELEASE_DATE = {
    16005: datetime(2021, 6, 30, 11, 0, 1),
    20003: datetime(2021, 2, 14, 11, 0, 1),
    16010: datetime(2022, 9, 28, 11, 0, 1),
}


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

# Format better SKIN_TABLE
class CompactListEncoder(json.JSONEncoder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.indent_level = 0
        
    def encode(self, obj):
        if isinstance(obj, dict):
            self.indent_level += 1
            items = []
            for key, value in obj.items():
                key_repr = f'"{key}"' if isinstance(key, str) else json.dumps(key)
                encoded_value = self.encode(value)
                items.append(f'{" " * self.indent * self.indent_level}{key_repr}: {encoded_value}')
            self.indent_level -= 1
            return "{\n" + ",\n".join(items) + "\n" + " " * self.indent * self.indent_level + "}"
        elif isinstance(obj, list):
            return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in obj) + "]"
        else:
            return json.dumps(obj, ensure_ascii=False)

class LocalizedText(TypedDict):
    en: str
    jp: str
    kr: str
    tw: str
    zh: str


@dataclass(frozen=True)
class KivoStudent:
    id: int
    avatar: str
    momotalk: str
    name_jp: str
    name_en: str
    name_zh: str
    nicknames: list[str]
    sticker_download_flag: list[bool]


@dataclass(frozen=True)
class Student:
    Id: int
    Avatar: list[str]
    Name: LocalizedText
    Bio: LocalizedText
    Nickname: list[str]
    Birthday: str
    Age: str
    School: str
    Club: str
    Star: int
    Released: bool
    Related: Optional[Any]


class StudentSyncGithub:
    """
    🔄 Synchronizes student data from GitHub repository

    This class handles fetching and processing student data from the GitHub repository,
    including character information, localization, and profile data.
    """

    def __init__(self) -> None:
        logger.info("🚀 Initializing GitHub sync...")
        self._validate_env()
        self.raw_data: dict[str, list[dict[str, Any]]] = {}
        self.ordering: list[int] = []
        self.school_table: dict[int, str] = {}
        self.club_table: dict[int, str] = {}
        self.star_table: dict[int, int] = {}
        self.age_table: dict[int, str] = {}
        self.name_table: dict[int, dict[str, str]] = {}
        self.status_message_table: dict[int, dict[str, str]] = {}
        self.results: dict[int, Student] = {}

        self._initialize_data()

    def _initialize_data(self) -> None:
        """Initialize all data tables in sequence."""
        logger.info("📚 Starting data initialization process...")

        logger.info("📝 Loading base data from GitHub...")
        self.load_base_data()

        logger.info("📝 Building release order...")
        self.build_release_order()

        logger.info("📝 Building school information...")
        self.build_school()

        logger.info("📝 Building name tables...")
        self.build_name()

        logger.info("📝 Building status messages...")
        self.build_status_message()
        
        logger.info("📝 Building club...")
        self.build_club()

        logger.info("📝 Building star...")
        self.build_star()

        logger.info("📝 Building age...")
        self.build_age()

        logger.info("📝 Merging localization data...")
        self.merge_localization()

        logger.success("Data initialization completed successfully")

    @property
    def data(self) -> list[Student]:
        return self.results

    def _validate_env(self) -> None:
        if not REPO_OWNER or not REPO_NAME:
            raise ValueError(
                "Environment variable REPO_OWNER and REPO_NAME must be set"
            )

    def fetch_json(self, url: str) -> dict[str, Any]:
        """
        🌐 Fetch JSON data from given URL with error handling
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch data from {url}: {str(e)}")
            raise e

    def load_base_data(self) -> None:
        endpoints = {
            # Character data
            "character": {
                "jp": f"{GITHUB_RAW_BASE}/jp/DB/CharacterExcelTable.json",
                "global": f"{GITHUB_RAW_BASE}/global/Excel/CharacterExcelTable.json",
            },
            # Localization data
            "etc": {
                "jp": f"{GITHUB_RAW_BASE}/jp/DB/LocalizeEtcExcelTable.json",
                "global": f"{GITHUB_RAW_BASE}/global/DB/LocalizeEtcExcelTable.json",
            },
            # Profile data
            "profile": {
                "jp": f"{GITHUB_RAW_BASE}/jp/DB/LocalizeCharProfileExcelTable.json",
                "global": f"{GITHUB_RAW_BASE}/global/Excel/LocalizeCharProfileExcelTable.json",
            },
        }

        for data_type, regions in endpoints.items():
            for region, url in regions.items():
                key = f"{data_type}_{region}"
                try:
                    logger.info(f"📥 Fetching {key} data...")
                    self.raw_data[key] = self.fetch_json(url)["DataList"]
                except Exception as e:
                    logger.error(f"Failed to load {key} data: {str(e)}")
                    raise

    @staticmethod
    def get_fixed_id(item: dict[str, Any]) -> int:  # 星野beta 100050001
        char_id = item["CharacterId"]
        return char_id if char_id <= 99999 else char_id // 10000

    @staticmethod
    def sort_by_key(table: dict[str, Any]) -> dict[str, Any]:
        return dict(sorted(table.items()))

    def build_release_order(self):
        """Build student release order based on JP server data."""
        self.ordering = []

        # Use character_jp data for release order
        release_data_table = {
            item["Id"]: datetime.strptime(item["ReleaseDate"], "%Y-%m-%d %H:%M:%S")
            for item in self.raw_data["character_jp"]
            if item["IsPlayable"]
            and item["ProductionStep"] == "Release"
            and item["TacticEntityType"] == "Student"
        }
        release_data_table.update(FIXED_RELEASE_DATE)

        release_data_table = sorted(release_data_table.items(), key=lambda x: x[1])
        self.ordering = list(dict(release_data_table).keys())

    def build_school(self):
        """Build school mapping from JP server data."""
        self.school_table = {
            item["Id"]: item["School"]
            for item in self.raw_data["character_jp"]
            if item["TacticEntityType"] == "Student"
        }
    
    def build_club(self):
        """Build club mapping from JP server data."""
        self.club_table = {
            item["Id"]: item["Club"]
            for item in self.raw_data["character_jp"]
            if item["TacticEntityType"] == "Student"
        }
    
    def build_star(self):
        """Build star mapping from JP server data."""
        self.star_table = {
            item["Id"]: item["DefaultStarGrade"]
            for item in self.raw_data["character_jp"]
            if item["TacticEntityType"] == "Student"
        }
        
    def build_age(self):
        """Build age mapping from JP server data."""
        self.age_table = {
            item["CharacterId"]: item["CharacterAgeJp"]
            for item in self.raw_data["profile_jp"]
            if item["CharacterAgeJp"]
        }

    def build_name(self):
        """Build name tables from both JP and Global server data."""
        self.name_table = {}
        _key = lambda key: key.replace("Name", "").lower()
        _value = lambda value: value.translate(str.maketrans("()", "（）"))

        # Process both JP and Global data
        for region in ["jp", "global"]:
            character_data = self.raw_data[f"character_{region}"]
            etc_data = self.raw_data[f"etc_{region}"]

            _find_first = lambda value: next(
                (x for x in etc_data if x["Key"] == value), None
            )

            for item in character_data:
                localize_item = _find_first(item["LocalizeEtcId"])
                if localize_item:
                    self.name_table.update(
                        {
                            item["Id"]: {
                                _key(key): (value if key != "NameTw" else _value(value))
                                for key, value in localize_item.items()
                                if key.startswith("Name") and not key.endswith("Th")
                            }
                        }
                    )

        self.name_table = {
            key: self.sort_by_key(value) for key, value in self.name_table.items()
        }

    def build_status_message(self):
        """Build status message tables from both JP and Global server data."""
        self.status_message_table = {}
        _key = lambda key: key.replace("StatusMessage", "").lower()

        # Process both JP and Global profile data
        for region in ["jp", "global"]:
            profile_data = self.raw_data[f"profile_{region}"]
            for item in profile_data:
                self.status_message_table.update(
                    {
                        self.get_fixed_id(item): {
                            _key(key): value
                            for key, value in item.items()
                            if key.startswith("StatusMessage")
                            and not key.endswith("Th")
                        }
                    }
                )

        self.status_message_table = {
            key: self.sort_by_key(value)
            for key, value in self.status_message_table.items()
        }

    def merge_localization(self):
        """Merge all localization data into final results."""
        self.results = {}

        for item in self.raw_data["profile_jp"]:
            if item["FullNameJp"]:
                id = self.get_fixed_id(item)
                self.results.update(
                    {
                        id: {
                            "Id": id,
                            "Avatar": [],  # manual
                            "Name": self.name_table[id],
                            "Bio": self.status_message_table[id],
                            "Nickname": [],  # manual
                            "Birthday": item["BirthDay"],
                            "Age": self.age_table[id],
                            "School": self.school_table[id],
                            "Club": self.club_table[id],
                            "Star": self.star_table[id],
                            "Released": True,
                            "Related": None,  # manual
                        }
                    }
                )

        # Sort results by release order
        self.results = [
            self.results[key] for key in self.ordering if key in self.results
        ]


class StudentSyncKivo:
    """
    🔄 Synchronizes student data from Kivo API

    Handles fetching and processing student data from the Kivo API,
    including avatars, names, and other student-specific information.
    """

    def __init__(self) -> None:
        logger.info("🚀 Initializing Kivo sync...")
        kivo_student_list_url = (
            "{KIVO_BASE}/?page={PAGE}&page_size=10&is_install=true&release_date_sort=desc"
        )
        try:
            kivo_file = open(ENDPOINTS["KIVO_MAP_JSON"], "r", encoding="utf-8")
            self.latest_kivo_data = []
            for page in range(1, 3):
                kivo_student_list_url_ = kivo_student_list_url.format(KIVO_BASE=KIVO_BASE, PAGE=page)
                kivo_student_list = requests.get(kivo_student_list_url_).json()["data"]["students"]
                self.latest_kivo_data.extend(kivo_student_list)
            self.cached_kivo_data = {
                int(key): value for key, value in json.load(kivo_file).items()
            }
            kivo_file.close()
            logger.success("Kivo data loaded successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kivo sync: {str(e)}")
            raise

    @property
    def data(self) -> dict[int, KivoStudent]:
        return self.cached_kivo_data

    @staticmethod
    def sort_by_key(table: dict):
        return dict(sorted(table.items()))

    def get_new_kivo_student(self, kivo_id: int) -> dict[str, Any]:
        new_item = {}
        kivo_student_url = f"{KIVO_BASE}/{kivo_id}"
        kivo_student_data = requests.get(kivo_student_url).json()

        kivo_item = kivo_student_data["data"]
        item_skin = f"（{kivo_item['skin']}）" if kivo_item["skin"] else ""
        decode_url = lambda url: (
            unquote("https:" + url) if url.startswith("//") else unquote(url)
        )

        new_item["kivo_id"] = kivo_id
        new_item["avatar"] = decode_url(kivo_item["avatar"])
        new_item["momotalk"] = kivo_item["momo_talk_signature"]
        new_item["name_en"] = kivo_item["given_name_en"]
        new_item["name_jp"] = kivo_item["given_name_jp"]
        new_item["name_zh"] = kivo_item["given_name"] + item_skin
        new_item["nicknames"] = (
            re.split("[,，]", kivo_item["nick_name"])
            if kivo_item["nick_name"] and kivo_item["nick_name"] != ","
            else []
        )
        new_item["sticker_download_flag"] = [False, False]
        return new_item

    def _download_and_save_avatar(self, avatar_url: str, student_id: int) -> str:
        """
        Download and save avatar in webp format

        Args:
            avatar_url: URL of the avatar image
            student_name: Student's Japanese name

        Returns:
            str: Returns API path if successful, kivo path if failed
        """
        try:
            # Prepare path
            avatar_filename = f"{student_id}.webp"
            avatar_path = ENDPOINTS["AVATAR_BASE"] / avatar_filename
            avatar_path.parent.mkdir(parents=True, exist_ok=True)
            api_path = f"/api/{ENDPOINTS['AVATAR_BASE'].as_posix()}/{avatar_filename}"

            if avatar_path.exists():
                logger.info(f"⚠️  Avatar already exists for {student_id}")
                return api_path

            # Save as webp format
            response = requests.get(avatar_url)
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content))
            img.save(str(avatar_path), "WEBP", quality=90)

            # Return API path
            logger.success(f"Successfully saved avatar for {student_id}")
            return api_path

        except Exception as e:
            logger.warning(f"Failed to process avatar for {student_id}: {str(e)}")
            # Return kivo path if failed
            return avatar_url.replace("https://static.kivo.wiki/images", "/kivo")

    def _fill_student_filed(self, student: Student, kivo_item: dict[str, Any]) -> None:
        if "zh" not in student["Bio"]:
            student["Name"].update({"zh": kivo_item["name_zh"]})
            student["Name"] = self.sort_by_key(student["Name"])

        if "zh" not in student["Bio"]:
            student["Bio"].update({"zh": kivo_item["momotalk"]})
            student["Bio"] = self.sort_by_key(student["Bio"])

        # Process avatar
        avatar_path = self._download_and_save_avatar(
            kivo_item["avatar"], student["Id"]
        )
        if avatar_path not in student["Avatar"]:
            student["Avatar"] = [avatar_path] + student["Avatar"]

        for nickname in kivo_item["nicknames"] + [kivo_item["name_en"]]:
            if nickname not in student["Nickname"]:
                student["Nickname"] = [nickname] + student["Nickname"]

    def fill_student(self, student: Student) -> Student:
        filled_s = copy.deepcopy(student)
        student_id = filled_s["Id"]
        student_name = filled_s["Name"]["jp"]

        match_name = lambda key: next(
            (x for x in self.latest_kivo_data if key in x["given_name_jp"]), None
        )

        if not student_id in self.cached_kivo_data:
            kivo_match = match_name(student_name.split("（")[0])
            if kivo_match:
                kivo_item = self.get_new_kivo_student(kivo_match["id"])
                kivo_item.update({"name_jp": student_name})
                self._fill_student_filed(filled_s, kivo_item)
                self.cached_kivo_data.update({student_id: kivo_item})
            else:
                raise ValueError(f"Not found {student_id}-{student_name} in Kivo!")
        else:
            kivo_item = self.cached_kivo_data[student_id]
            kivo_item.update({"name_jp": student_name})
            self._fill_student_filed(filled_s, kivo_item)
        return filled_s

def check_skin_table(skin):
    with open(ENDPOINTS["SKIN_TABLE"], 'r', encoding="utf-8") as f:
        table = json.loads(f.read())
    if skin in table:
        return

    table[skin] = []
    table = dict(sorted(table.items()))
    with open(ENDPOINTS["SKIN_TABLE"], 'w', encoding="utf-8") as f:
        f.write(json.dumps(table, indent=4, ensure_ascii=False, cls=CompactListEncoder))

if __name__ == "__main__":
    try:
        logger.info("🎮 Starting student data synchronization...")

        # Update local data
        existing_students = json.load(open(ENDPOINTS["STUDENTS_JSON"], "r", encoding="utf-8"))
        updated_students = copy.deepcopy(existing_students)

        github_sync = StudentSyncGithub()
        kivo_sync = StudentSyncKivo()
        github_studuents = github_sync.data

        find_student_by_id = lambda value: next((x for x in updated_students if x["Id"] == value), None)
        find_student_by_jp_name = lambda value: next((x for x in github_studuents if x["Name"]["jp"] == value), None)

        # Process each student
        for github_student in github_studuents:
            if github_student["Id"] == 10099: continue ## 临战星野盾形态
            existing_student = find_student_by_id(github_student["Id"])
            student_id = github_student["Id"]
            student_name = github_student["Name"]["jp"]
            info_msg = f"{Colors.RED}{student_id}-{student_name}{Colors.RESET}"

            # new student in jp server
            if not existing_student:
                logger.info(f"➕ Updating {info_msg} from Kivo")
                new_student = kivo_sync.fill_student(github_student)

                # a studen with skin
                skin = re.match(r"(.*?)（(.*)）", student_name)
                if skin:
                    student_origin_name = skin.group(1)
                    student_origin_id = find_student_by_jp_name(student_origin_name)["Id"]
                    student_skin = skin.group(2)
                    new_student["Related"] = {"ItemId": student_origin_id, "ItemType": student_skin}
                    check_skin_table(student_skin)

                updated_students.append(new_student)

            # new student in global server
            elif "tw" not in existing_student["Name"] and "tw" in github_student["Name"]:
                logger.info(f"➕ Updating {info_msg} from global data")
                zh_name = existing_student["Name"].get("zh", "") # backup zh name
                existing_student["Name"] = github_student["Name"]
                existing_student["Name"].update({"zh": zh_name})

                zh_bio = existing_student["Bio"].get("zh", "") # backup zh momotalk status
                existing_student["Bio"] = github_student["Bio"]
                existing_student["Bio"].update({"zh": zh_bio})

        # Save updated data
        logger.info("💾 Saving updated data...")
        sort_by_key = lambda table: dict(sorted(table.items()))
        with open(ENDPOINTS["STUDENTS_JSON"], "w", encoding="utf-8") as f:
            f.write(json.dumps(updated_students, indent=4, ensure_ascii=False))
        with open(ENDPOINTS["KIVO_MAP_JSON"], "w", encoding="utf-8") as f:
            f.write(json.dumps(sort_by_key(kivo_sync.data), indent=4, ensure_ascii=False))

        logger.success("Synchronization completed successfully!")
    except Exception as e:
        logger.error(f"Synchronization failed: {str(e)}")
        raise
