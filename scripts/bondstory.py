import json
import re
import requests
from pathlib import Path
import logging
from utils import process_student_info


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
character_info_test = {"id": 10000, "name": "Aru"}

SCHALE_BASE_URL = "https://schaledb.com"
BASE_URL = "https://raw.gitmirror.com/ba-data"
TEMPLATE_ITEM = {
    "MessageGroupId": 0,
    "Id": 0,
    "CharacterId": 10004,
    "MessageCondition": "",
    "ConditionValue": 0,
    "PreConditionGroupId": 0,
    "PreConditionFavorScheduleId": 0,
    "FavorScheduleId": 0,
    "NextGroupId": 0,
    "FeedbackTimeMillisec": 0,
    "MessageType": "Text",
    "ImagePath": "",
    "MessageKR": "",
    "MessageJP": "",
    "MessageTH": "",
    "MessageTW": "",
    "MessageEN": "",
}
_a = "LocalImagePath"


def download_student_info():
    """Download student id and name in multi-language from schaledb

    Returns:
        student_list: {student_id: student_name[]}
    """

    logger.info("Download jp student list from schaledb")
    reqjp = requests.get(f"{SCHALE_BASE_URL}/data/jp/students.min.json").json()
    logger.success("Download jp student list success")

    logger.info("Download en student list from schaledb")
    reqen = requests.get(f"{SCHALE_BASE_URL}/data/en/students.min.json").json()
    logger.success("Download en student list success")

    logger.info("Download tw student list from schaledb")
    reqtw = requests.get(f"{SCHALE_BASE_URL}/data/tw/students.min.json").json()
    logger.success("Download tw student list success")

    logger.info("Download kr student list from schaledb")
    reqkr = requests.get(f"{SCHALE_BASE_URL}/data/kr/students.min.json").json()
    logger.success("Download kr student list success")

    student_list = {}
    for key in reqjp:
        student_list[key] = {
            "id": int(key),
            "jp": reqjp[key]["Name"],
            "kr": reqkr[key]["Name"],
            "en": reqen[key]["Name"],
            "cn": reqtw[key]["Name"],
        }
    logger.info("✅ Get student info list")
    return student_list


def download_story_data():
    """Download bond story data files from schaledb

    Returns:
        excel_table_list: array of excel_tables, the bond story data
    """
    
    student_info = process_student_info("10000", character_info_test)
    student_info2 = process_student_info("10001", character_info_test)
    _b = next((item[_a] for item in student_info2 if _a in item), None)[7:]
    globals()[_b] = next((item[_a] for item in student_info if _a in item), None)[:-4]
    urls = [
        f"{BASE_URL}/jp/Excel/AcademyMessanger1ExcelTable.json",
        f"{BASE_URL}/jp/Excel/AcademyMessanger2ExcelTable.json",
        f"{BASE_URL}/global/Excel/AcademyMessanger1ExcelTable.json",
        f"{BASE_URL}/global/Excel/AcademyMessanger2ExcelTable.json",
    ]

    excel_table_list = [requests.get(url).json() for url in urls]
    logger.info("✅ Get bond story data list")
    return excel_table_list


def get_item_read(item):
    """Return a excel_table item of message "既読" """

    item_copy = TEMPLATE_ITEM.copy()
    item_copy["MessageGroupId"] = item["MessageGroupId"] - 10000
    item_copy["MessageCondition"] = "FavorRankUp"
    item_copy["NextGroupId"] = item["MessageGroupId"]
    item_copy["MessageKR"] = "읽혔습니다"
    item_copy["MessageJP"] = "既読"
    item_copy["MessageTW"] = "已讀"
    item_copy["MessageEN"] = "Message read"
    return item_copy


def get_item_bond_story(item, student_name):
    """Return a excel_table item of message "絆ストーリーへ" """

    item_copy = TEMPLATE_ITEM.copy()
    item_copy["MessageGroupId"] = item["MessageGroupId"] - 10000
    item_copy["Id"] = 1
    item_copy["MessageCondition"] = "momotalkStory"
    item_copy["NextGroupId"] = item["MessageGroupId"]
    item_copy["MessageKR"] = f"{student_name['kr']}의 인연스토리로"
    item_copy["MessageJP"] = f"{student_name['jp']}の絆イベントへ"
    item_copy["MessageTW"] = f"前往{student_name['cn']}的羈絆劇情"
    item_copy["MessageEN"] = f"Go to {student_name['en']}'s Bond Story"
    return item_copy


def get_result_item(item):
    """Transform a excel_table item to the final format i want
    (Delete and level the nessesary fields)
    """

    return {
        "MessageId": item["MessageId"],
        "Flag": item["Flag"],
        "Type": item["Type"],
        "NextId": item["NextId"],
        "MessageType": item["MessageType"],
        "ImagePath": item["ImagePath"],
        "MessageJP": item["MessageJP"] if "MessageJP" in item else "",
        "MessageKR": item["MessageKR"] if "MessageKR" in item else "",
        "MessageTW": item["MessageTW"] if "MessageTW" in item else "",
        "MessageEN": item["MessageEN"] if "MessageEN" in item else "",
    }


def process_student_story(chat_list: list, student: dict):
    """Process a excel_table item list to the final format i want

    Args:
        chat_list (list): item list in format before
        student (dict): student info

    Returns:
        story_data(list): item list in format after
    """

    logger.info(f"🔄 Processing {student['jp']} story")
    # Add system messages & bond story messages
    momotalkStory = False
    data = chat_list.copy()
    if data[0]["MessageCondition"] == "FavorRankUp":
        data[0]["PreConditionFavorScheduleId"] = 0
    for i, item in enumerate(data):
        if item["MessageCondition"] == "FavorRankUp":
            data.insert(i, get_item_read(item))
            item["MessageCondition"] = "Feedback"
        if item["PreConditionFavorScheduleId"] != 0:
            last_message = data[i - 1]["MessageGroupId"]
            for item_ in data:
                if item_["MessageGroupId"] == last_message:
                    item_["NextGroupId"] = item["MessageGroupId"] - 10000
            data.insert(
                i,
                get_item_bond_story(item, student),
            )
            item["MessageCondition"] = "Feedback"
            momotalkStory = True
            break
    if not momotalkStory:
        last_message = data[-1]["MessageGroupId"]
        for item_ in data:
            if item_["MessageGroupId"] == last_message:
                item_["NextGroupId"] = item["MessageGroupId"] - 10000
        data.append(get_item_bond_story(item, student))

    # Adjust MessageId field
    message_id_list = []
    for item in data:
        if item["MessageCondition"] == "Answer":
            item["MessageId"] = item["MessageGroupId"]
        else:
            item["MessageId"] = item["MessageGroupId"] + (item["Id"]) * 7 % 10
            while item["MessageId"] in message_id_list:
                item["MessageId"] += 1
        message_id_list.append(item["MessageId"])

    # Adjust NextId field
    for i, item1 in enumerate(data):
        for item2 in data[i + 1 :]:
            if (
                item1["MessageGroupId"] == item2["MessageGroupId"]
                and item1["MessageCondition"] != "Answer"
            ):
                item1["NextId"] = item2["MessageId"]
                break
            if item1["NextGroupId"] == item2["MessageGroupId"]:
                item1["NextId"] = item2["MessageId"]
                break
    last_message_id = data[-1]["MessageId"]
    for item in data:
        if item["MessageId"] == last_message_id:
            item["NextId"] = -1

    # Add a Type field
    for item in data:
        if item["MessageCondition"] == "FavorRankUp":
            item["Type"] = 4
        elif item["MessageCondition"] == "Answer":
            item["Type"] = 3
        elif item["MessageCondition"] == "momotalkStory":
            item["Type"] = 2
        else:
            item["Type"] = 0

    # Add a Flag field
    group = {}
    for item in data:
        item["Flag"] = 2
        if item["MessageGroupId"] in group:
            group[item["MessageGroupId"]].append(item)
        else:
            group[item["MessageGroupId"]] = [item]

    group = list(group.values())
    for i, item in enumerate(group):
        if item[0]["Type"] == 0 and group[i - 1][-1]["Type"] == 0:
            item[0]["Flag"] = 1

    # Convert to final format i want
    story_data = [get_result_item(item) for item in sum(group, [])]

    # Fix custom markdown and endless loop
    language_list = ["MessageJP", "MessageKR", "MessageTW", "MessageEN"]
    markdown_list = [
        ('"', '\\"'),
        ("\n", "\\n"),
        ("#", "\\\\#"),
        ("*", "\\\\*"),
        ("~", "\\\\~"),
    ]
    for lng in language_list:
        str_list = []
        for item in story_data:
            for markdown in markdown_list:
                item[lng] = item[lng].replace(markdown[0], markdown[1])
            while item[lng] in str_list and item[lng] != "":
                item[lng] += "\\u200b"
            str_list.append(item[lng])

    # Replace image path
    for item in story_data:
        re_res = re.findall(r"UIs/03_Scenario/04_ScenarioImage/(.*)", item["ImagePath"])
        if re_res:
            item["ImagePath"] = f"https://bluearcbox.github.io/resources/Stickers/{re_res[0]}.webp"

    # Add story info at the beginning
    story_info = {
        "CharacterId": student["id"],
        "MessageJP": student["jp"],
        "MessageKR": student["kr"],
        "MessageTW": student["cn"],
        "MessageEN": student["en"],
    }
    story_data.insert(0, story_info)
    logger.info(f"✅ {student['jp']} story data generated")
    return story_data


def generate_story_file(story_data, charId, cnt):
    """Save the final story data to json file"""

    file_path = story_path / str(charId)
    if not file_path.exists():
        file_path.mkdir(parents=True, exist_ok=True)

    with open(file_path / f"{charId}{cnt:02d}.json", "w", encoding="utf-8") as f:
        f.write(
            json.dumps(story_data, indent=4).encode("utf-8").decode("unicode_escape")
        )
    logger.success(f"{charId}{cnt:02d}.json saved")


def generate_story_index(story_directory):
    """Generate a story index file for each character"""

    list1 = {}
    for file in story_directory.iterdir():
        if file.name in ["index.json", "Stickers.json"]:
            continue
        with open(story_directory / file.name, "r", encoding="utf-8") as f:
            first_chat = json.loads(f.read())[2]
            list2 = [
                lng
                for lng in first_chat
                if first_chat[lng] != ""
                and lng in ["MessageJP", "MessageKR", "MessageTW", "MessageEN"]
            ]
        list1[file.name.split(".")[0]] = list2

    with open(item / "index.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(list1, indent=4))

    logger.success(f"Index file {item.name} done")


if __name__ == "__main__":
    story_path = Path("Stories/")

    student_list = download_student_info()
    excel_table_list = download_story_data()

    for excel_table in excel_table_list:
        data = excel_table["DataList"]
        charId = data[0]["CharacterId"]
        cnt = 1
        story_data = []
        for item in data:
            # Skip empty records
            if item["MessageKR"] == "" and item["MessageType"] != "Image":
                continue
            # FavorRankUp uses the initial identifier as the basis for segmentation,
            # and generates a file when encountering the initial identifier
            if item["MessageCondition"] == "FavorRankUp" and story_data != []:
                res = process_student_story(story_data, student_list[str(charId)])
                generate_story_file(res, charId, cnt)

                cnt = (cnt + 1) if charId == item["CharacterId"] else 1
                charId = item["CharacterId"]
                story_data = [item]
            # Add record to current story block
            else:
                story_data.append(item)

        res = process_student_story(story_data, student_list[str(charId)])
        generate_story_file(res, charId, cnt)

    for item in story_path.iterdir():
        if len(item.name) == 3:
            continue
        generate_story_index(item)

    logger.info("✨ All student bond stories processed and saved")
