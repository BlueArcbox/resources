import requests
from pathlib import Path
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()
REPO_OWNER = os.getenv("REPO_OWNER")
REPO_NAME = os.getenv("REPO_NAME")

if not REPO_OWNER or not REPO_NAME:
    raise ValueError("REPO_OWNER and REPO_NAME environment variables must be set.")


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
BASE_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"

with open("scripts/signature.json", "r", encoding="utf-8") as f:
    signature = json.loads(f.read())


def check(student):
    if student["CharacterId"] > 99999:
        return False
    if student["StatusMessageJp"] == "" and student["PersonalNameJp"] != "ヒナ":
        return False
    return True


def download_momotalk_status():
    url_jp = f"{BASE_URL}/jp/Excel/LocalizeCharProfileExcelTable.json"
    url_global = f"{BASE_URL}/global/Excel/LocalizeCharProfileExcelTable.json"

    response = requests.get(url_jp)
    response.encoding = "utf-8"
    if response.status_code != 200:
        logger.error("Failed to fetch jp status data")
        raise Exception("Failed to fetch data")
    student_info = response.json()["DataList"]
    status_list = [
        {
            "id": student["CharacterId"],
            "name": student["FullNameJp"],
            "data": {
                "zh": (
                    signature[str(student["CharacterId"])]
                    if str(student["CharacterId"]) in signature
                    else student["StatusMessageJp"]
                ),
                "jp": student["StatusMessageJp"],
                "kr": student["StatusMessageKr"],
            },
        }
        for student in student_info
        if check(student)
    ]

    response = requests.get(url_global)
    response.encoding = "utf-8"
    if response.status_code != 200:
        logger.error("Failed to fetch global status data")
        raise Exception("Failed to fetch data")
    student_info = response.json()["DataList"]
    for student in student_info:
        if not check(student):
            continue
        for item in status_list:
            if item["id"] == student["CharacterId"]:
                item["data"]["tw"] = student["StatusMessageTw"]
                item["data"]["en"] = student["StatusMessageEn"]
                break

    for status in status_list:
        for key in status["data"]:
            status["data"][key] = (
                status["data"][key].replace('"', '\\"').replace("\n", " ")
            )

    return status_list


if __name__ == "__main__":
    # 获取本地数据
    logger.info("🔍 Load local data from local file")
    file_path = Path("Momotalk/")
    with open(file_path / "students.json", "r", encoding="utf-8") as f:
        local_data = json.load(f)
    logger.info("✅ Load local data from local file")

    # 获取当前版本数据
    logger.info("🔍 Fetch latest momotalk status data")
    source_list = download_momotalk_status()
    logger.info("✅ Fetch latest momotalk status data")

    # 分析更新数据
    target_list = []
    for new_student in source_list:
        found = False
        for local_student in local_data:
            if new_student["id"] == local_student["Id"]:
                if len(new_student["data"]) != len(local_student["Bio"]):
                    new_student["exist"] = True
                    target_list.append(new_student)
                found = True
                break
        if not found:
            new_student["exist"] = False
            target_list.append(new_student)
    logger.info("✅ Analyze update data:")
    for item in target_list:
        logger.info(f"    - {item['name']}")

    # 更新本地数据
    data = local_data.copy()
    for item in target_list:
        if item["exist"]:
            for student in data:
                if student["Id"] == item["id"]:
                    for key in item["data"]:
                        if key not in student["Bio"]:
                            student["Bio"][key] = item["data"][key]
                    logger.info(f"✍️  Update {item['name']}")
                    break
        else:
            data.append(
                {
                    "Id": item["id"],
                    "Avatar": [],
                    "Bio": item["data"],
                    "Nickname": [],
                    "Fixed": [],
                    "Related": None,
                }
            )
            logger.info(f"✍️  Insert {item['name']}")

    with open(file_path / "students.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logger.success("Update local data done")
