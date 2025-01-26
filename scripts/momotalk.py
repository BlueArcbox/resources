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


@dataclass(frozen=True)
class Student:
    Id: int
    Avatar: list[str]
    Name: LocalizedText
    Bio: LocalizedText
    Nickname: list[str]
    Birthday: str
    School: str
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
                "jp": f"{GITHUB_RAW_BASE}/jp/Excel/CharacterExcelTable.json",
                "global": f"{GITHUB_RAW_BASE}/global/Excel/CharacterExcelTable.json",
            },
            # Localization data
            "etc": {
                "jp": f"{GITHUB_RAW_BASE}/jp/DB/LocalizeEtcExcelTable.json",
                "global": f"{GITHUB_RAW_BASE}/global/DB/LocalizeEtcExcelTable.json",
            },
            # Profile data
            "profile": {
                "jp": f"{GITHUB_RAW_BASE}/jp/Excel/LocalizeCharProfileExcelTable.json",
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
                            "School": self.school_table[id],
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
            f"{KIVO_BASE}/?page=1&page_size=10&is_install=true&release_date_sort=desc"
        )
        try:
            kivo_file = open(ENDPOINTS["KIVO_MAP_JSON"], "r", encoding="utf-8")
            self.latest_kivo_data = requests.get(kivo_student_list_url).json()["data"][
                "students"
            ]
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


if __name__ == "__main__":
    try:
        logger.info("🎮 Starting student data synchronization...")

        # Update local data
        old_data = json.load(open(ENDPOINTS["STUDENTS_JSON"], "r", encoding="utf-8"))
        new_data = copy.deepcopy(old_data)

        student_g = StudentSyncGithub()
        student_k = StudentSyncKivo()
        student_list = student_g.data

        find_first = lambda value: next((x for x in new_data if x["Id"] == value), None)

        # Process each student
        for item in student_list:
            target_item = find_first(item["Id"])
            student_id = item["Id"]
            student_name = item["Name"]["jp"]
            info_msg = f"{Colors.RED}{student_id}-{student_name}{Colors.RESET}"

            if not target_item:
                logger.info(f"➕ Updating {info_msg} from Kivo")
                new_data.append(student_k.fill_student(item))

            elif "tw" not in target_item["Name"] and "tw" in item["Name"]:
                logger.info(f"➕ Updating {info_msg} from global data")
                zh_name = target_item["Name"].get("zh", "")
                target_item["Name"] = item["Name"]
                target_item["Name"].update({"zh": zh_name})

                zh_bio = target_item["Bio"].get("zh", "")
                target_item["Bio"] = item["Bio"]
                target_item["Bio"].update({"zh": zh_bio})

        # Save updated data
        logger.info("💾 Saving updated data...")
        sort_by_key = lambda table: dict(sorted(table.items()))
        with open(ENDPOINTS["STUDENTS_JSON"], "w", encoding="utf-8") as f:
            f.write(json.dumps(new_data, indent=4, ensure_ascii=False))
        with open(ENDPOINTS["KIVO_MAP_JSON"], "w", encoding="utf-8") as f:
            f.write(
                json.dumps(sort_by_key(student_k.data), indent=4, ensure_ascii=False)
            )

        logger.success("Synchronization completed successfully!")
    except Exception as e:
        logger.error(f"Synchronization failed: {str(e)}")
        raise
