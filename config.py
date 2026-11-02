"""
集中管理可调参数。
"""

import os
import platform

from wanyou.env_loader import load_project_env

load_project_env()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int = 0) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default

# 登录凭据改为运行时输入，不在配置中保存。

# Selenium 选项
HEADLESS = True
PAGE_LOAD_TIMEOUT = 30
PAGE_LOAD_STRATEGY = "eager"
WAIT_TIMEOUT = 15
UNIFIED_AUTH_MANUAL_WAIT_SECONDS = 600
SELENIUM_BROWSER = os.environ.get(
    "WANYOU_SELENIUM_BROWSER",
    "chrome" if platform.system().lower() == "darwin" else "edge",
).lower()
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/70.0.3538.25 Safari/537.36"
)
SELENIUM_CACHE_DIR = "./output/selenium_cache"
# Keep the unified-auth browser identity so WebVPN's trusted-device decision
# survives between Wanyou runs. Override with WANYOU_AUTH_PROFILE_DIR when needed.
UNIFIED_AUTH_PROFILE_DIR = os.environ.get(
    "WANYOU_AUTH_PROFILE_DIR",
    os.path.join(SELENIUM_CACHE_DIR, "unified-auth-profile"),
)

# 日期/时间窗口
NOTICE_PREFILTER_CUTOFF = ""

# 站点 URL
URL_INFO = (
    "https://webvpn.tsinghua.edu.cn/https/77726476706e69737468656265737421f9f9479369247b59700f81b9991b2631506205de/"
    "f/info/xxfb_fg/xnzx/template/more?lmid=all"
)
URL_MYHOME = (
    "https://webvpn.tsinghua.edu.cn/http/77726476706e69737468656265737421fdee49932a3526446d0187ab9040227bca90a6e14cc9/"
    "web_Netweb_List/News_notice.aspx?wrdrecordvisit=1746369533000"
)
URL_LIB_NOTICE = "https://lib.tsinghua.edu.cn/tzgg.htm"
URL_LIB_EVENT = "https://lib.tsinghua.edu.cn/hdrl.htm"
URL_HALL_PAGES = [
    "https://www.hall.tsinghua.edu.cn/columnEx/pwzx_hdap/yc-dy-px-zl-jz/1",
    "https://www.hall.tsinghua.edu.cn/columnEx/pwzx_hdap/yc-dy-px-zl-jz/2",
]
PHYSICS_REPORT_LIST_PAGES = [
    "https://www.phys.tsinghua.edu.cn/xwyhd/xshd.htm",
    "https://www.phys.tsinghua.edu.cn/kxyj/xsbg.htm",
]

# 筛选/排除规则
MYHOME_NO_CONSIDER = ["学生社区中心信息周报", "学生区室外大型活动信息"]
LIB_NO_CONSIDER = []
LIB_CONSIDER = ["信息", "资源", "研究"]
HALL_NO_CONSIDER = []
PHYSICS_REPORT_FORCE_KEYWORDS = ["学术报告", "学术讲座", "报告", "讲座", "colloquium", "seminar", "讲坛", "论坛"]
PHYSICS_REPORT_LOCATION_KEYWORDS = ["W101", "W105", "理科楼", "物理楼"]

# myhome 图片 OCR
MYHOME_IMAGE_OCR_ENABLED = _env_bool("MYHOME_IMAGE_OCR_ENABLED", True)
MYHOME_IMAGE_OCR_KEEP_IMAGE = _env_bool("MYHOME_IMAGE_OCR_KEEP_IMAGE", True)
MYHOME_IMAGE_OCR_SPACE_URL = os.environ.get("MYHOME_IMAGE_OCR_SPACE_URL", "https://api.ocr.space/parse/image")
MYHOME_IMAGE_OCR_API_KEY_ENV = os.environ.get("MYHOME_IMAGE_OCR_API_KEY_ENV", "OCR_SPACE_API_KEY")
MYHOME_IMAGE_OCR_LANGUAGE = os.environ.get("MYHOME_IMAGE_OCR_LANGUAGE", "chs")
MYHOME_IMAGE_OCR_ENGINE = _env_int("MYHOME_IMAGE_OCR_ENGINE", 1)
MYHOME_IMAGE_OCR_TIMEOUT_SECONDS = _env_int("MYHOME_IMAGE_OCR_TIMEOUT_SECONDS", 30)

# 输出相关
OUTPUT_DIR = "./output"
OUTPUT_NAME_PREFIX = "wanyou"
IMAGES_DIR_PREFIX = "images"
PANDOC_RESOURCE_PATH_TEMPLATE = "--resource-path={images_dir}"
OUTPUT_DOCX_ENABLED = True
OUTPUT_H5_ENABLED = True
OUTPUT_AGENT_PAYLOAD_ENABLED = True
H5_TITLE = "万有预报"
RAW_COLLECTION_MODE = False
RAW_SKIP_LLM_CLEAN = False
RAW_COLLECTION_KEEP_IMAGES = _env_bool("RAW_COLLECTION_KEEP_IMAGES", True)

# 公众号抓取相关（down.mptext.top API）
WECHAT_PUBLIC_API_BASE_URL = "https://down.mptext.top/api/public/v1"
WECHAT_PUBLIC_API_KEY_ENV = "WECHAT_PUBLIC_API_KEY"
WECHAT_ACCOUNT_KEYWORDS = [
    "清华青年科创",
    "清华大学学生会",
    "清华大学学生会权益服务中心",
    "清华大学学生社团",
    "清华大学学生公益",
]
WECHAT_ACCOUNT_KEYWORD = WECHAT_ACCOUNT_KEYWORDS[0]
WECHAT_FAKEID = ""
WECHAT_ACCOUNT_SEARCH_SIZE = 1
WECHAT_ARTICLE_SIZE = 20
WECHAT_DOWNLOAD_FORMAT = "html"
WECHAT_DAYS_LIMIT = 0
WECHAT_MAIN_RECENT_DAYS = 7
# 「近一周」的窗口口径（见 wanyou/recent_window.py）：
#   "week"    —— 上一校历周周一 00:00 起（默认；滚动窗口会漏掉边界日白天的推送）
#   "day"     —— 今天 00:00 往前 N 天
#   "rolling" —— 老的 now - N×24h
WECHAT_RECENT_ALIGN = os.environ.get("WECHAT_RECENT_ALIGN", "week").strip().lower()
# 撞上微信读书人机校验（-2041）时，程序提示用户手动完成后原地等待的上限（秒）
WEREAD_RISK_WAIT_SECONDS = _env_int("WEREAD_RISK_WAIT_SECONDS", 600)

# 公众号抓取来源：
#   "weread"  —— 微信读书网页版（默认；一次运行即可抓满一周，不依赖任何第三方域名）
#   "mptext"  —— 旧的 down.mptext.top 第三方 API（2026-10-30 域名到期，仅留作回滚）
WECHAT_SOURCE = os.environ.get("WECHAT_SOURCE", "weread").strip().lower()
# 微信读书路线：目标公众号的 bookId（MP_WXS_<base64decode(__biz) 的数字部分>）。
# 号名不用写在这里，运行时从书架接口反查。
WEREAD_ACCOUNT_BOOK_IDS = [
    "MP_WXS_3531191868",  # 清华大学学生会
    "MP_WXS_3089010740",  # 清华青年科创
    # bookId = "MP_WXS_" + base64decode(__biz) 中的数字部分；下面两个号已实测可订阅、可取列表。
    "MP_WXS_2398854781",  # 清华大学学生社团（__biz=MjM5ODg1NDc4MQ==）
    "MP_WXS_2394734625",  # 清华大学学生公益（__biz=MjM5NDczNDYyNQ==）
]
WEREAD_DEBUG_PORT = _env_int("WEREAD_DEBUG_PORT", 9333)
# 登录态和人机校验的信任都留在这个 profile 里，换目录就得重新扫码。
WEREAD_PROFILE_DIR = os.environ.get("WEREAD_PROFILE_DIR", "output/selenium_cache/weread-debug-profile")
WEREAD_CHROME_PATH = os.environ.get("WEREAD_CHROME_PATH", "")
# 一页 = 20 次群发（实测一个号一页覆盖约 15 天），所以 2 页足够一周且只发 2 次请求。
WEREAD_MAX_PAGES = _env_int("WEREAD_MAX_PAGES", 2)
# 微信读书列表接口只给正文节选（常见几十字），/web/mp/content?reviewId=... 能拿到
# 整篇正文和图片。打开全文后，时效判断能解析活动日期，报名二维码也能提取出来。
WECHAT_FULL_CONTENT_ENABLED = _env_bool("WECHAT_FULL_CONTENT_ENABLED", True)
WECHAT_FULL_CONTENT_MAX_CHARS = _env_int("WECHAT_FULL_CONTENT_MAX_CHARS", 8000)
# 报名二维码：从正文图片里识别（OpenCV QR 检测），落到本地后作为图片附在卡片里。
WECHAT_QR_ENABLED = _env_bool("WECHAT_QR_ENABLED", True)
WECHAT_QR_MAX_IMAGES = _env_int("WECHAT_QR_MAX_IMAGES", 2)
WECHAT_QR_MAX_CANDIDATES = _env_int("WECHAT_QR_MAX_CANDIDATES", 6)
WECHAT_QR_IMAGE_DIR = os.environ.get("WECHAT_QR_IMAGE_DIR", "output/wechat_qr")

# 公众号抓取/输出
WECHAT_OUTPUT_FORMAT = "md"
WECHAT_REQUEST_TIMEOUT = 15
WECHAT_SLEEP_SECONDS = 1
WECHAT_DOWNLOAD_MAX_WORKERS = 16
WECHAT_OCR_ENABLED = _env_bool("WECHAT_OCR_ENABLED", True)
WECHAT_OCR_SPACE_URL = os.environ.get("WECHAT_OCR_SPACE_URL", "https://api.ocr.space/parse/imageurl")
WECHAT_OCR_SPACE_API_KEY_ENV = os.environ.get("WECHAT_OCR_SPACE_API_KEY_ENV", "OCR_SPACE_API_KEY")
WECHAT_OCR_TIMEOUT_SECONDS = _env_int("WECHAT_OCR_TIMEOUT_SECONDS", 30)
WECHAT_OCR_SPACE_LANGUAGE = os.environ.get("WECHAT_OCR_SPACE_LANGUAGE", "chs")
WECHAT_OCR_SPACE_IS_OVERLAY_REQUIRED = _env_bool("WECHAT_OCR_SPACE_IS_OVERLAY_REQUIRED", False)
WECHAT_OCR_SPACE_DETECT_ORIENTATION = _env_bool("WECHAT_OCR_SPACE_DETECT_ORIENTATION", False)
WECHAT_OCR_SPACE_IS_TABLE = _env_bool("WECHAT_OCR_SPACE_IS_TABLE", False)
WECHAT_OCR_SPACE_ENGINE = _env_int("WECHAT_OCR_SPACE_ENGINE", 1)
WECHAT_OCR_MAX_IMAGES_PER_ARTICLE = _env_int("WECHAT_OCR_MAX_IMAGES_PER_ARTICLE", 0)
IMAGE_LLM_PROVIDER = os.environ.get("IMAGE_LLM_PROVIDER", "")
IMAGE_LLM_BASE_URL = os.environ.get("IMAGE_LLM_BASE_URL", "")
IMAGE_LLM_MODEL = os.environ.get("IMAGE_LLM_MODEL", "")
IMAGE_LLM_API_KEY_ENV = os.environ.get("IMAGE_LLM_API_KEY_ENV", "")
IMAGE_LLM_TIMEOUT_SECONDS = _env_int("IMAGE_LLM_TIMEOUT_SECONDS", 20)
OCR_VISION_LLM_ENABLED = _env_bool("OCR_VISION_LLM_ENABLED", False)
OCR_VISION_LLM_MODE = os.environ.get("OCR_VISION_LLM_MODE", "fallback").strip().lower()
OCR_VISION_LLM_PROVIDER = os.environ.get("OCR_VISION_LLM_PROVIDER", IMAGE_LLM_PROVIDER)
OCR_VISION_LLM_BASE_URL = os.environ.get("OCR_VISION_LLM_BASE_URL", IMAGE_LLM_BASE_URL)
OCR_VISION_LLM_MODEL = os.environ.get("OCR_VISION_LLM_MODEL", IMAGE_LLM_MODEL)
OCR_VISION_LLM_API_KEY_ENV = os.environ.get("OCR_VISION_LLM_API_KEY_ENV", IMAGE_LLM_API_KEY_ENV)
OCR_VISION_LLM_TIMEOUT_SECONDS = _env_int("OCR_VISION_LLM_TIMEOUT_SECONDS", IMAGE_LLM_TIMEOUT_SECONDS)
# DeepSeek 的模型名只写这一个地方。deepseek-v4-flash / deepseek-v4-flash-vision-exp
# 是遗留兼容别名，底层模型已下线，请求只是被临时转发到 deepseek-flash；
# deepseek-chat / deepseek-reasoner 已于 2026-07-24 彻底退役。
DEEPSEEK_DEFAULT_MODEL = "deepseek-flash"
WECHAT_IMAGE_LLM_ENABLED = _env_bool("WECHAT_IMAGE_LLM_ENABLED", True)
WECHAT_IMAGE_LLM_PROVIDER = os.environ.get("WECHAT_IMAGE_LLM_PROVIDER", IMAGE_LLM_PROVIDER)
WECHAT_IMAGE_LLM_BASE_URL = os.environ.get("WECHAT_IMAGE_LLM_BASE_URL", IMAGE_LLM_BASE_URL)
WECHAT_IMAGE_LLM_MODEL = os.environ.get("WECHAT_IMAGE_LLM_MODEL", IMAGE_LLM_MODEL or DEEPSEEK_DEFAULT_MODEL)
WECHAT_IMAGE_LLM_API_KEY_ENV = os.environ.get("WECHAT_IMAGE_LLM_API_KEY_ENV", IMAGE_LLM_API_KEY_ENV)
WECHAT_IMAGE_LLM_TIMEOUT_SECONDS = _env_int("WECHAT_IMAGE_LLM_TIMEOUT_SECONDS", IMAGE_LLM_TIMEOUT_SECONDS)
WECHAT_FILTER_MD_WITH_LLM = False
WECHAT_FILTER_CONTENT_MAX_CHARS = 3000
WECHAT_FILTER_FALLBACK_KEEP = True

# LLM 自动决策（yes/no）
LLM_ENABLED = True
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek")  # "zhipuai", "openai", "chatgpt", "deepseek", "gemini"
LLM_MODEL = os.environ.get("LLM_MODEL", DEEPSEEK_DEFAULT_MODEL)
DECIDER_LLM_MODEL = os.environ.get("DECIDER_LLM_MODEL", DEEPSEEK_DEFAULT_MODEL)
WECHAT_SUMMARY_LLM_MODEL = os.environ.get("WECHAT_SUMMARY_LLM_MODEL", DEEPSEEK_DEFAULT_MODEL)
PHYSICS_EXTRACT_LLM_MODEL = os.environ.get("PHYSICS_EXTRACT_LLM_MODEL", DEEPSEEK_DEFAULT_MODEL)
RAW_RANKING_LLM_MODEL = os.environ.get("RAW_RANKING_LLM_MODEL", DEEPSEEK_DEFAULT_MODEL)
SYNTHESIS_LLM_MODEL = os.environ.get("SYNTHESIS_LLM_MODEL", DEEPSEEK_DEFAULT_MODEL)
MARKDOWN_CLEAN_LLM_MODEL = os.environ.get("MARKDOWN_CLEAN_LLM_MODEL", DEEPSEEK_DEFAULT_MODEL)
LLM_API_KEY_ENV = os.environ.get("LLM_API_KEY_ENV", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_TIMEOUT_SECONDS = 20
# 单次请求的输出上限。0（默认）表示不下发 max_tokens，由服务端给默认值：
# 非思考 8K、思考 64K（reasoning_effort=max 时 128K），上限 384K。
# 各调用点以前写死的 5~800 太小，截断后调用方的 `or fallback` 会静默降级，
# 从日志上看不出来，所以改成默认不限；确实要限长再设成正数。
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 0)
LLM_LOG_PATH = "llm_decisions.jsonl"
INTERACTIVE_REVIEW = False
DEFAULT_COPY_WHEN_UNDECIDED = True
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_BASE_URL = "https://api.openai.com/v1"
DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
# 思考强度，对应请求体的 reasoning_effort，只对 deepseek 下发（别的 provider 不认这个字段）。
#   none          关闭思考模式
#   low / high    开启思考，指定强度
#   max           开启思考，最高强度（max_tokens 默认额度也随之抬到 128K）
# medium（默认）是官方兼容别名，实际映射为 high —— 也就是服务端本来就用的默认档。
# 另注：思考模式下 temperature 不生效（官方明确说明不报错、但也不起作用），
# 想让它重新起作用就把这里设成 none。
DEEPSEEK_REASONING_EFFORT = os.environ.get("DEEPSEEK_REASONING_EFFORT", "medium").strip().lower()
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
ZHIPUAI_API_KEY_ENV = "ZHIPUAI_API_KEY"
ZHIPUAI_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
LLM_FORCE_YES_KEYWORDS = [
    "开题",
    "注册",
    "学籍",
    "培养",
    "课程",
    "选课",
    "退课",
    "奖学金",
    "物理",
    "讲座",
    "SRT",
]
LLM_FORCE_NO_KEYWORDS = [
    "公示",
    "招聘",
    "教师",
    "研究生",
    "博士生",
]

# LLM 内容合成
FINAL_MARKDOWN_LLM_CLEAN_ENABLED = _env_bool("FINAL_MARKDOWN_LLM_CLEAN_ENABLED", True)
XIUMI_IMAGE_MODE = os.environ.get("XIUMI_IMAGE_MODE", "upload").strip().lower()
XIUMI_MAX_INLINE_IMAGE_HTML_CHARS = _env_int("XIUMI_MAX_INLINE_IMAGE_HTML_CHARS", 900000)
XIUMI_IMAGE_UPLOAD_MAX_FAILURES = _env_int("XIUMI_IMAGE_UPLOAD_MAX_FAILURES", 3)
XIUMI_IMAGE_UPLOAD_RETRIES = _env_int("XIUMI_IMAGE_UPLOAD_RETRIES", 2)
XIUMI_IMAGE_UPLOAD_BATCH_SIZE = _env_int("XIUMI_IMAGE_UPLOAD_BATCH_SIZE", 6)
XIUMI_IMAGE_UPLOAD_STALL_SECONDS = _env_int("XIUMI_IMAGE_UPLOAD_STALL_SECONDS", 180)
# 秀米「粘贴转 CDN」通道吃不下大图。实测：0.4 MB 的图全部成功，6~7 MB 的
# 新清华学堂海报 3 张全部失败（cdn_failed），草稿里就是断图。所以超过下面
# 阈值就先在浏览器里用 canvas 降采样再粘。阈值取 1 MB：远高于已验证成功的
# 量级，又远低于已验证失败的量级，留足余量。
XIUMI_IMAGE_MAX_BYTES = _env_int("XIUMI_IMAGE_MAX_BYTES", 1_000_000)
# 降采样时的最长边上限（像素）。手机端正文宽度约 700px，1600 足够清晰。
XIUMI_IMAGE_MAX_DIMENSION = _env_int("XIUMI_IMAGE_MAX_DIMENSION", 1600)
# 公众号条目：把「要点透视」和「摘要」按功能拆开写。
#   要点透视 = 形式信息（对象、时间、地点、报名/截止），像一张速览卡；
#   摘要 = 内容信息（项目/活动简介、比赛或活动流程、亮点）。
# 两者都要求短：要点透视一行、摘要一两句，避免过去两条几乎同文互相重复。
WECHAT_BRIEF_SYSTEM_PROMPT = (
    "你在为清华大学物理系《万有预报》整理一条公众号条目，需要把「要点透视」和「摘要」分开写。\n"
    "「要点透视」只写形式信息：对象（面向谁/谁参加）、时间（哪天几点）、地点（在哪）、报名或截止时间。"
    "每项用分号隔开，不写活动介绍；材料没有的信息直接省略，不要写「未提及」「未交代」；"
    "不超过 40 字。\n"
    "「摘要」只写内容信息：这是什么活动或项目、项目简介、比赛或活动流程、亮点。"
    "不重复对象、时间、地点；不写编者视角（材料、原文、来源为、日期显示为、公众号、推送、标题）；"
    "写 120–180 字，把材料里的具体信息尽量写进来（分组、奖项、报名方式、作品要求、流程环节等），"
    "不要只写一句概括。\n"
    "要点透视要短，摘要可以长；两段都不要空话和客套话。\n"
    '只输出 JSON：{"lede":"要点透视","digest":"摘要"}，不要输出任何其他内容。'
)
WECHAT_LEDE_MAX_CHARS = _env_int("WECHAT_LEDE_MAX_CHARS", 45)
WECHAT_SUMMARY_MAX_CHARS = _env_int("WECHAT_SUMMARY_MAX_CHARS", 220)
# 图片型推送（正文极短、信息都在图里）没有可解析日期时：保留待人工，而不是按 unknown 丢掉
WECHAT_IMAGE_ONLY_KEEP = _env_bool("WECHAT_IMAGE_ONLY_KEEP", True)
WECHAT_IMAGE_ONLY_MAX_CHARS = _env_int("WECHAT_IMAGE_ONLY_MAX_CHARS", 120)
# 人工补链接表（标题<TAB>mp 链接，可选）：原文链接现在由 weread 的 /web/mp/content
# 页面里的 msg_link 自动补全（weread_client.fetch_article_contents）；这个表只用来
# 覆盖个别取不到页面、或想换成官方短链的条目。
# 公众号时效闸门：日期解析不出来时交给 LLM 判，不确定即弃（防过期推送混入）
WECHAT_FRESHNESS_GATE = True
WECHAT_LINKS_TSV = "output/week6_20261019/wechat_links.tsv"
# 公众号栏目的固定顺序；公众号链路和最终清洗阶段共用这一份名单。
WECHAT_SECTIONS = [
    "学生会信息",
    "青年科协信息",
    "学生社团信息",
    "学生公益信息",
    "其他公众号信息",
]
# 拿不到原文链接时先占位，方便人工在成稿里替换
WECHAT_LINK_PLACEHOLDER = "〔原文链接待补〕"
LLM_TRANSITION_ENABLED = False
LLM_TRANSITION_SYSTEM_PROMPT = (
    "你是“万有预报”文案助手。"
    "请用一句话（不超过 18 字）说明本栏本周有哪些事，只陈述事实。"
    "不要抒情、不要比喻、不要“先看这里/下面来看看”这类招呼语，不要重复卡片标题的措辞。"
    "如果本栏目没有内容，请写“本周暂无相关信息”。"
)
# 只保留空栏目的兜底文案。有内容的栏目不再输出导语：按栏目硬编码的过渡句每期重复、
# 与卡片标题重复，还常与当期事实矛盾（十月写「天气渐暖」），已从合成阶段移除。
SECTION_DEFAULT_TRANSITIONS = {
    "EMPTY": "本周暂无相关信息，大家先安心上课。",
}

# 浏览器 Agent / 秀米对接
BROWSER_AGENT_ENABLED = False
BROWSER_AGENT_MCP_CONFIG = "./config/mcporter.json"
BROWSER_AGENT_TARGET = "autoglm-browser-agent"
XIUMI_TEMPLATE_SLOTS = {
    "title": "slot-title",
    "lead": "slot-lead",
    "body": "slot-body",
}
XIUMI_HOME_URL = os.environ.get("XIUMI_HOME_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/")
XIUMI_EDITOR_URL = os.environ.get("XIUMI_EDITOR_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/paper/for/new")
XIUMI_PROFILE_DIR = "./output/selenium_cache/xiumi-profile"
XIUMI_LOGIN_WAIT_SECONDS = 600
XIUMI_SAVE_WAIT_SECONDS = 30

# 不允许脚本自动点登录（会跳到微信扫码/授权页），登录由人自己完成
XIUMI_LOGIN_AUTO_CLICK = False
