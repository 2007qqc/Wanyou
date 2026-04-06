"""
集中管理可调参数
"""

# 登录凭据改为运行时输入（不在配置中保存）

# Selenium 选项
HEADLESS = True
PAGE_LOAD_TIMEOUT = 30
WAIT_TIMEOUT = 15
SLEEP_SECONDS = 3
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.25 Safari/537.36"

# 日期/时间窗口
DAYS_WINDOW_INFO = 300
DAYS_WINDOW_MYHOME = 300
DAYS_WINDOW_LIB = 300
HALL_RECENT_DAYS = 14
LIB_EVENT_YEAR_ROLL_DAYS = 350

# 站点 URL
URL_INFO = "https://webvpn.tsinghua.edu.cn/https/77726476706e69737468656265737421f9f9479369247b59700f81b9991b2631506205de/f/info/xxfb_fg/xnzx/template/more?lmid=all"
URL_MYHOME = "https://webvpn.tsinghua.edu.cn/http/77726476706e69737468656265737421fdee49932a3526446d0187ab9040227bca90a6e14cc9/web_Netweb_List/News_notice.aspx?wrdrecordvisit=1746369533000"
URL_LIB_NOTICE = "https://lib.tsinghua.edu.cn/tzgg.htm"
URL_LIB_EVENT = "https://lib.tsinghua.edu.cn/hdrl.htm"
URL_HALL_PAGES = [
    "https://www.hall.tsinghua.edu.cn/columnEx/pwzx_hdap/yc-dy-px-zl-jz/1",
    "https://www.hall.tsinghua.edu.cn/columnEx/pwzx_hdap/yc-dy-px-zl-jz/2",
]

# 筛选/排除规则
MYHOME_NO_CONSIDER = ["学生社区中心信息周报", "学生区室外大型活动信息"]
LIB_NO_CONSIDER = []
LIB_CONSIDER = ["信息•资源•研究"]
HALL_NO_CONSIDER = []

# myhome 图片 OCR（用于将正文图片中的文字转为 markdown 文本）
MYHOME_IMAGE_OCR_ENABLED = True
MYHOME_IMAGE_OCR_KEEP_IMAGE = False
MYHOME_IMAGE_OCR_SPACE_URL = "https://api.ocr.space/parse/image"
MYHOME_IMAGE_OCR_API_KEY_ENV = "OCR_SPACE_API_KEY"
MYHOME_IMAGE_OCR_LANGUAGE = "chs"
MYHOME_IMAGE_OCR_ENGINE = 1
MYHOME_IMAGE_OCR_TIMEOUT_SECONDS = 30

# 输出相关
OUTPUT_DIR = "./output"
OUTPUT_NAME_PREFIX = "wanyou"
IMAGES_DIR_PREFIX = "images"
PANDOC_RESOURCE_PATH_TEMPLATE = "--resource-path={images_dir}"

# 公众号抓取相关（down.mptext.top API）
WECHAT_PUBLIC_API_BASE_URL = "https://down.mptext.top/api/public/v1"
WECHAT_PUBLIC_API_KEY_ENV = "WECHAT_PUBLIC_API_KEY"  # 可选，若设置则作为 X-Auth-Key 请求头
WECHAT_ACCOUNT_KEYWORD = "清华青年科创"  # 例如“阮一峰”
WECHAT_FAKEID = ""  # 设置后可跳过 keyword 查询
WECHAT_ACCOUNT_SEARCH_SIZE = 1
WECHAT_ARTICLE_SIZE = 20
WECHAT_DOWNLOAD_FORMAT = "html"
WECHAT_DAYS_LIMIT = 0  # 独立运行 wechat_public.py 时生效；0 表示不限制
WECHAT_MAIN_RECENT_DAYS = 7  # main.py 中抓取公众号时仅保留最近 N 天

# 兼容旧配置（当前脚本不再使用）
WECHAT_BIZ = ""
WECHAT_APPMSG_LIST_URL = ""
WECHAT_OUTPUT_FORMAT = "md"  # "md" or "json"
WECHAT_PAGE_SIZE = 10
WECHAT_MAX_PAGES = 20
WECHAT_MAX_ARTICLES = 3  # 0 表示不限制
WECHAT_FETCH_CONTENT = True  # 仅控制 md 是否写入正文，不影响正文抓取
WECHAT_CONTENT_FORMAT = "md"  # "md" or "html"
WECHAT_COOKIE_ENV = "WECHAT_COOKIE"
WECHAT_COOKIE_PROMPT = True
WECHAT_REQUEST_TIMEOUT = 15
WECHAT_SLEEP_SECONDS = 1
WECHAT_OCR_ENABLED = True
WECHAT_OCR_SPACE_URL = "https://api.ocr.space/parse/imageurl"
WECHAT_OCR_SPACE_API_KEY_ENV = "OCR_SPACE_API_KEY"
WECHAT_OCR_TIMEOUT_SECONDS = 30
WECHAT_OCR_SPACE_LANGUAGE = "chs"
WECHAT_OCR_SPACE_IS_OVERLAY_REQUIRED = False
WECHAT_OCR_SPACE_DETECT_ORIENTATION = False
WECHAT_OCR_SPACE_IS_TABLE = False
WECHAT_OCR_SPACE_ENGINE = 1
WECHAT_OCR_MAX_IMAGES_PER_ARTICLE = 0  # 0 表示全部图片
WECHAT_IMAGE_LLM_ENABLED = True
WECHAT_IMAGE_LLM_BASE_URL = ""  # 为空则回退到 LLM_BASE_URL
WECHAT_IMAGE_LLM_MODEL = ""  # 为空则回退到 LLM_MODEL
WECHAT_IMAGE_LLM_API_KEY_ENV = ""  # 为空则回退到 LLM_API_KEY_ENV
WECHAT_IMAGE_LLM_TIMEOUT_SECONDS = 20
WECHAT_FILTER_MD_WITH_LLM = False
WECHAT_FILTER_CONTENT_MAX_CHARS = 3000
WECHAT_FILTER_FALLBACK_KEEP = True

# LLM 自动决策（yes/no）
LLM_ENABLED = False
LLM_PROVIDER = "zhipuai"  # "openai" or "zhipuai"
LLM_MODEL = "glm-4.7"
LLM_API_KEY_ENV = "ZHIPUAI_API_KEY"
LLM_BASE_URL = "https://open.bigmodel.cn"
LLM_TIMEOUT_SECONDS = 20
LLM_LOG_PATH = "llm_decisions.jsonl"  # 为空则不记录
LLM_FORCE_YES_KEYWORDS = [
    "开馆",
    "注册",
    "学籍",
    "培养",
    "课程",
    "选课"
    "奖学金",
]
LLM_FORCE_NO_KEYWORDS = [
    "公示",
    "招聘",
    "教师",
    "研究生",
    "博士生",
    "停水"
]
LLM_SYSTEM_PROMPT = (
    "你是一个内容筛选器。"
    "根据提供的标题、日期、站点、摘要判断是否需要保留该条内容。"
    "只输出 YES 或 NO，不要输出其他文字。"
    "优先规则：本科生学习、生活等相关输出 YES；"
    "研究生、教师相关内容（不包含评教）、重复通知、关于特定宿舍楼的、停水等持续时间短的通知输出 NO。"
)
