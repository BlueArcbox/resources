import requests
import json
import time
import math
import random

header = {
    "credentials": "include",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "referrer": "https://space.bilibili.com/436037759/dynamic",
    "method": "GET",
    "mode": "cors"
}

page_size = 30
results = []
cache = []

with open('./Comics/cache.json', 'r', encoding='utf-8') as f:
    cache = json.loads(f.read())

keywordTable = {
    "blueArchive": "純粋な不純物&mid=436037759",
    "fourPanel": "碧蓝档案漫画连载中&mid=37507923",
    "record": "作:せるげい(@pattundo)&mid=436037759",
    "record2": "せるげい&mid=37507923"
}

filterTable = {
    "blueArchive": [
        771782039631298564,
        771753035707711507,
        657128385688895507,
        502993601544930371,
        502670564173752802,
        502253063285176379,
        500453398969849746,
        491922077794132770
        ],
    "fourPanel": [
        766219696196288546,
        755717938514755654,
        755365802750771249
        ],
    "record": [
        771782039631298564,
        505966668097363742,
        505374941860938266
        ],
    "record2": []
}

insertDynamics = {
    "blueArchive": [
        719366263004987413, # 86
        716787723564744726, # 85
        714168983229562884, # 84
        711623721184395264, # 83
        701286460703113239, # 79
        690906375250771989, # 75
        688279650352234500, # 74
        677935526590808103, # 70
        667528279671963656, # 66
        662337751564156977, # 64
        636565692956540967, # 55
        633409759584714759, # 54
        557338174927095808 #27
        ],
    "fourPanel": [
        # 98
        812964277775237233, # 88
        789572395511840805, # 79
        779465431184310291, # 75
        722056226799616017, # 54
        719458136674533433, # 53
        716841032688336930 # 52
        # 49-1
        ],
    "record": [
        771753035707711507 # 4 
        ],
    "record2": [
        861948456858550274, # 30
        860008020687454273, # 29
    ]
}

def sleepRandomTime():
    t = random.randrange(15, 30)
    print(f"sleeping {t} sec")
    time.sleep(t)

def retry(times):
    def wrapper(func):
        def inner_wrapper(*args, **kwargs):
            i = 0
            while i < times:
                try:
                    print(f"try in {i} times...")
                    return func(*args, **kwargs)
                except:
                    print("logdebug: {}()".format(func.__name__))
                    i += 1
        return inner_wrapper
    return wrapper

def requestDemo(url):
    sleepRandomTime()
    r = requests.get(url, headers=header)
    data = json.loads(r.content)
    return data

@retry(10)
def _getADynamic(dyid):
    url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/detail?id={dyid}"
    data = requestDemo(url)
    data = data['data']['item']['modules']['module_dynamic']

    result = {
            "dynamic_id": dyid,
            "description": data['desc']['text'],
            "pictures": data['major']['draw']['items'],
            "pictures_count": len(data['major']['draw']['items'])
        }

    return result

def getADynamic(dyid):
    global cache
    for item in cache:
        if item['dynamic_id'] == dyid:
            return item
    return _getADynamic(dyid)

@retry(3)
def getTotalNum(target):
    global total
    src = f"https://api.bilibili.com/x/space/dynamic/search?keyword={ keywordTable[target] }&pn=1&ps=1"
    data = requestDemo(src)
    total = data['data']['total']
    print(f"1️⃣ [total] {data['data']['total']} pages")
    return total

@retry(3)
def getMost(target, total):
    tmp_results = []
    for i in range(math.ceil(total/page_size)):
        
        url = f"https://api.bilibili.com/x/space/dynamic/search?keyword={ keywordTable[target] }&pn={ i+1 }&ps={ page_size }"
        print(url)
        data = requestDemo(url)
        
        for item in data['data']['cards']:
            if item['desc']['type'] != 2:
                continue
            tmp_results.append({
                "dynamic_id": item['desc']['dynamic_id'],
                "description": json.loads(item['card'])['item']['description'],
                "pictures": json.loads(item['card'])['item']['pictures'],
                "pictures_count": json.loads(item['card'])['item']['pictures_count']
            })

        print(f"2️⃣ [most] downloaded {min(total, page_size*(i+1))}/{total} pages")
    return tmp_results

def getRest(target):
    global results
    results = [item for item in results if item['dynamic_id'] not in filterTable[target]]
    results += [getADynamic(dyid) for dyid in insertDynamics[target]]
    results = sorted(results, key=lambda x:x['dynamic_id'])
    print(f"3️⃣ [rest] rid of wrong dynamic and download lost dynamic in { target }")

def save(target):
    with open("./Comics/"+target+'.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(results, indent=4, ensure_ascii=False))
        
def download(target):
    global results
    print("===== start =====")
    print(f"🚀 start download {target}")
    start_time = time.time()
    results = []
    total = getTotalNum(target)
    results += getMost(target, total)
    getRest(target)
    save(target)
    finish_time = time.time()
    print(f"download {target} total {len(results)} pages in {finish_time-start_time} sec")
    
if __name__ == '__main__':
    start = time.time()
    for target in list(keywordTable.keys()):
        download(target)
    finish = time.time()
    print(f"====== finished ======\n✅ finishied in {finish-start} sec")