import threading
import json
import asyncio
from os import mkdir, system
from sys import argv
from tempfile import gettempdir
from time import time
from shutil import rmtree
from io import BytesIO
from ctypes import windll

import webview
import websockets
import pydub
import requests
import cv2
from PIL import Image, ImageDraw, ImageFont
from numpy import array as nparray

if len(argv) < 4:
    print("Usage: TodayTopic <zhihu_question_id> <question_image> <output_video>")
    windll.kernel32.ExitProcess(0)

threading._curt = threading.current_thread
def _current_thread():
    t = threading._curt()
    t.name = "MainThread"
    return t
threading.current_thread = _current_thread

zhihu_qid = argv[1]
devid = 358882467914123
iid = 358882467914123
appid = 3704
appkey = "IZjhUeAYwP"
uvc = "6.0.1.11779"
vc = "6.0.1"
un = "名称"
pt = "平台"

window = webview.create_window("", f"https://www.zhihu.com/question/{zhihu_qid}")
threading.Thread(target=lambda:webview.start(debug=True, private_mode=False), daemon=True).start()

input("Press Enter to continue (please wait for the page to load completely, login and scroll down to the bottom answer) ...")

js = '''

const answers = document.querySelectorAll("div.ContentItem.AnswerItem");
const imre = /<img[^>]*>/g;

class Answer {
    constructor(ele) {
        this.userName = ele.querySelector(".ContentItem-meta .AuthorInfo .AuthorInfo").children[0].content;
        this.content = ele.querySelector(".RichContent span .RichContent-inner").children[0].children[0].textContent.replace(imre,);
    }
}

const pyresult = [];
for (let i = 0; i < answers.length; i++) {
    pyresult.push(new Answer(answers[i]));
}

pyresult;

'''

result: list[dict[str, str]] = window.evaluate_js(js)
question = window.evaluate_js("document.body.querySelector(\".QuestionHeader-title\").innerText;")

async def getTTS(text: str) -> bytes:
    print(f"getting TTS, length: {len(text)}")
    async with websockets.connect(f"wss://sami.bytedance.com/internal/api/v2/ws?device_id={devid}&iid={iid}&app_id={appid}&region=CN&update_version_code={uvc}&version_code={vc}&appKey={appkey}&device_type=windows&device_platform=windows") as ws:
        await ws.send(json.dumps({
            "appkey": appkey,
            "event": "StartTask",
            "namespace": "TTS",
            "payload": json.dumps({
                "audio_config": {
                    "bit_rate": 64000,
                    "format": "ogg_opus",
                    "sample_rate": 16000
                },
                "speaker": "BV408_streaming",
                "texts": [text]
            })
        }))
        await ws.recv()
        await ws.send(json.dumps({
            "appkey": appkey,
            "event": "FinishTask",
            "namespace": "TTS"
        }))
        while True:
            data = await ws.recv()
            if isinstance(data, bytes) and data.startswith(b"Ogg"):
                try: await ws.close()
                except Exception: pass
                return data

def getImage(text: str):
    try:
        result = requests.get(
            f"https://image.baidu.com/search/acjson?tn=resultjson_com&word={text}",
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        ).json()
        data = requests.get(result["data"][0]["middleURL"]).content
        return Image.open(BytesIO(data))
    except Exception:
        return defaultErrIm

contentDatas = []

contentDatas.append({
    "before": 0.75,
    "text": f"今日话题: {question}",
    "im": False
})

contentDatas.append({
    "before": 0.3,
    "text": f"关于这个话题, {pt}{un} 精选了几位网友的回答",
    "im": False
})

answersplit_chars = ",，。!！?？\n"

for i, answer in enumerate(result):
    for char in answersplit_chars:
        answer["content"] = answer["content"].replace(char, " ")
    answer_splited = list(filter(lambda x: x, answer["content"].replace("undefined", "").split(" ")))
    contentDatas.append({
        "before": 0.5,
        "text": f"第{i + 1}位网友 {answer["userName"]} 回答道:",
        "im": True
    })
    for ansi, ans in enumerate(answer_splited):
        contentDatas.append({
            "before": 0.05,
            "text": ans,
            "im": True
        })

contentDatas.append({
    "before": 0.75,
    "text": "以上几位网友的回答希望对大家有所启发",
    "im": False
})

contentDatas.append({
    "before": 0.1,
    "text": f"关注{pt}{un}, 探索更多问题的答案",
    "im": False
})

defaultIm = Image.open(argv[2])
defaultErrIm = Image.open("default-err.png")
tempDir = f"{gettempdir()}/todayTopic_temp{time()}"
try: mkdir(tempDir)
except FileExistsError: pass
maxt = 0.0

for index, item in enumerate(contentDatas):
    try:
        fp = f"{tempDir}/{index}.ogg"
        with open(fp, "wb") as f:
            f.write(asyncio.run(getTTS(item["text"])))
        item["seg"] = pydub.AudioSegment.from_ogg(fp)
    except Exception as e:
        item["seg"] = pydub.AudioSegment.silent(50)
    item["im"] = getImage(item["text"]) if item["im"] else defaultIm
    if 0 in item["im"].size:
        item["im"] = defaultErrIm
    maxt += item["before"] + item["seg"].duration_seconds

mergedSeg = pydub.AudioSegment.silent(int(maxt * 1000) + 2500).overlay(pydub.AudioSegment.from_file("bgm.mp3"), 0.0, True)
nowoggt = 0.0
for item in contentDatas:
    nowoggt += item["before"]
    mergedSeg = mergedSeg.overlay(item["seg"], int(nowoggt * 1000))
    nowoggt += item["seg"].duration_seconds

mergedSeg.export(f"{tempDir}/audio.ogg", format="ogg")

contentEvents = []
st = 0.0
for index, item in enumerate(contentDatas):
    if index != len(contentDatas) - 1:
        contentEvents.append({
            "st": st,
            "et": st + item["before"] + item["seg"].duration_seconds,
            "data": item
        })
    st += item["before"] + item["seg"].duration_seconds

def getNowState(t: float):
    for e in contentEvents:
        if e["st"] <= t <= e["et"]:
            p = (t - e["st"]) / (e["et"] - e["st"])
            return e["data"]["im"], p if e["data"]["im"] is not defaultIm else 1.0, e["data"]["text"]
    return defaultIm, 1.0, contentDatas[-1]["text"]

writer = cv2.VideoWriter(
    f"{tempDir}/video.mp4",
    cv2.VideoWriter.fourcc(*"mp4v"),
    60,
    (1920, 1080),
    True
)

try:
    maxframe = int(mergedSeg.duration_seconds * 60) + 1
    fcut = -1
    font = ImageFont.truetype("font.ttf", int((1920 + 1080) / 65))
    while fcut <= maxframe:
        fcut += 1
        frame = Image.new("RGB", (1920, 1080), (0, 0, 0))
        fim, p, text = getNowState(fcut / 60.0)
       
        scale = 1.0 - (1.0 - (0.75 + p * 0.25)) ** 2
        br = 1920 / 1080
        gr = fim.width / fim.height
        if br >= gr:
            w, h = 1080 / fim.height * fim.width, 1080
        else:
            w, h = 1920, 1920 / fim.width * fim.height
        w, h = int(w * 0.75 * scale), int(h * 0.75 * scale)
        w, h = w if w > 0 else 1, h if h > 0 else 1
        frame.paste(fim.resize((w, h)), (int((1920 - w) / 2), int((1080 - h) / 2)))
        
        frameDraw = ImageDraw.Draw(frame)
        tbox = frameDraw.multiline_textbbox((0, 0), text, font)
        frameDraw.multiline_text(
            (1920 / 2 - (tbox[2] - tbox[0]) / 2, 1080 * 0.9),
            text = text,
            font = font,
            fill = "white"
        )
        
        writer.write(nparray(frame)[:, :, ::-1])
        print(f"\rcrating video frame {fcut} / {maxframe}", end="")
except Exception as e:
    print(e)

writer.release()

system(f"ffmpeg -i \"{tempDir}/video.mp4\" -i \"{tempDir}/audio.ogg\" -acodec copy -vcodec copy \"{argv[3]}\"")

try: rmtree(tempDir)
except Exception as e: print(e)