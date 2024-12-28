import json
import aiohttp
import asyncio

with open("Momotalk/students.json", 'r', encoding='utf-8') as f:
    character_info = json.load(f)

avatar_list_list = [info["Avatar"] for info in character_info]
targets = sum([[avatar for avatar in l if avatar.startswith("/fandom")] for l in avatar_list_list if l], [])
urls = [target.replace("/fandom", "https://static.wikia.nocookie.net/blue-archive/images") for target in targets]

async def async_download(url):
    name = url.split("/")[-1]
    async with aiohttp.ClientSession() as session:
        async with session.get(url, proxy="http://127.0.0.1:7900") as resp:
            with open(f"Avatars/Fandom/{name}", "wb") as f:
                f.write(await resp.content.read())
    print("下载完成")

async def main():
    tasks = [asyncio.create_task(async_download(url)) for url in urls]
    await asyncio.wait(tasks)

loop = asyncio.get_event_loop()
loop.create_task(main())