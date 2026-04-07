"""
集中管理可调参数。
"""

# 登录凭据改为运行时输入，不在配置中保存。

# Selenium 选项
HEADLESS = True
PAGE_LOAD_TIMEOUT = 30
PAGE_LOAD_STRATEGY = "eager"
WAIT_TIMEOUT = 15
SLEEP_SECONDS = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/70.0.3538.25 Safari/537.36"
)
SELENIUM_CACHE_DIR = "./output/selenium_cache"

# 日期/时间窗口
DAYS_WINDOW_INFO = 300
DAYS_WINDOW_MYHOME = 300
DAYS_WINDOW_LIB = 300
HALL_RECENT_DAYS = 14
LIB_EVENT_YEAR_ROLL_DAYS = 350
PHYSICS_REPORT_RECENT_DAYS = 21

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
PHYSICS_REPORT_FORCE_KEYWORDS = ["学术报告", "学术讲座", "报告", "讲座", "colloquium", "seminar"]
PHYSICS_REPORT_LOCATION_KEYWORDS = ["W101", "W105", "理科楼", "物理楼"]

# myhome 图片 OCR
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
OUTPUT_DOCX_ENABLED = True
OUTPUT_H5_ENABLED = True
OUTPUT_AGENT_PAYLOAD_ENABLED = True
OUTPUT_HTML_NAME_SUFFIX = ".html"
H5_TITLE = "万有预报"

# 公众号抓取相关（down.mptext.top API）
WECHAT_PUBLIC_API_BASE_URL = "https://down.mptext.top/api/public/v1"
WECHAT_PUBLIC_API_KEY_ENV = "WECHAT_PUBLIC_API_KEY"
WECHAT_ACCOUNT_KEYWORDS = [
    "清华青年科创",
    "清华大学学生会",
    "清华大学学生会权益服务中心",
]
WECHAT_ACCOUNT_KEYWORD = WECHAT_ACCOUNT_KEYWORDS[0]
WECHAT_FAKEID = ""
WECHAT_ACCOUNT_SEARCH_SIZE = 1
WECHAT_ARTICLE_SIZE = 20
WECHAT_DOWNLOAD_FORMAT = "html"
WECHAT_DAYS_LIMIT = 0
WECHAT_MAIN_RECENT_DAYS = 7

# 兼容旧配置（当前脚本不再使用）
WECHAT_BIZ = ""
WECHAT_APPMSG_LIST_URL = ""
WECHAT_OUTPUT_FORMAT = "md"
WECHAT_PAGE_SIZE = 10
WECHAT_MAX_PAGES = 20
WECHAT_MAX_ARTICLES = 3
WECHAT_FETCH_CONTENT = True
WECHAT_CONTENT_FORMAT = "md"
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
WECHAT_OCR_MAX_IMAGES_PER_ARTICLE = 0
WECHAT_IMAGE_LLM_ENABLED = True
WECHAT_IMAGE_LLM_PROVIDER = ""
WECHAT_IMAGE_LLM_BASE_URL = ""
WECHAT_IMAGE_LLM_MODEL = ""
WECHAT_IMAGE_LLM_API_KEY_ENV = ""
WECHAT_IMAGE_LLM_TIMEOUT_SECONDS = 20
WECHAT_FILTER_MD_WITH_LLM = False
WECHAT_FILTER_CONTENT_MAX_CHARS = 3000
WECHAT_FILTER_FALLBACK_KEEP = True

# LLM 自动决策（yes/no）
LLM_ENABLED = True
LLM_PROVIDER = "deepseek"  # "zhipuai", "openai", "chatgpt", "deepseek", "gemini"
LLM_MODEL = "deepseek-chat"
LLM_API_KEY_ENV = ""
LLM_BASE_URL = ""
LLM_TIMEOUT_SECONDS = 20
LLM_LOG_PATH = "llm_decisions.jsonl"
INTERACTIVE_REVIEW = False
DEFAULT_COPY_WHEN_UNDECIDED = True
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_BASE_URL = "https://api.openai.com/v1"
DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
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
    "停水",
]
LLM_SYSTEM_PROMPT = (
    "你是清华大学物理系学生会的权益助理。"
    "请根据标题、日期、站点和摘要判断该信息是否值得进入“万有预报”。"
    "优先保留物理系相关信息、全校性重大教务安排、奖学金、SRT、选退课和讲座。"
    "优先剔除教师招聘、纯研究生通知、重复公示和影响范围很小的临时信息。"
    "只输出 YES 或 NO，不要输出其他内容。"
)

# LLM 内容合成
LLM_SUMMARY_ENABLED = False
LLM_SUMMARY_MAX_CHARS = 100
LLM_SUMMARY_SYSTEM_PROMPT = (
    "你是清华大学物理系学生会“万有预报”编辑助理。"
    "请将通知压缩成 100 字以内的中文要点摘要，突出和本科生有关的时间、地点、对象、报名或截止信息。"
)
LLM_TRANSITION_ENABLED = False
LLM_TRANSITION_SYSTEM_PROMPT = (
    "你是“万有预报”文案助手。"
    "请根据栏目内容写一句自然衔接语，风格简洁、温和、校园化。"
    "如果本栏目没有内容，请写一句自然的“本周暂无相关信息”类过渡句。"
)
SECTION_DEFAULT_TRANSITIONS = {
    "教务通知": "这周教务安排里有几条和课程节奏直接相关，大家记得看截止时间。",
    "学生会信息": "学生会这边和同学权益、校园活动相关的消息放在这里。",
    "青年科协信息": "科创和青年组织相关的动态，适合关注项目、讲座和实践机会的同学。",
    "学生社团信息": "社团活动和招新消息集中在这一栏，方便大家按兴趣挑着看。",
    "学生社区": "生活面的更新也整理在这里，适合课间快速扫一眼。",
    "图书馆信息": "图书馆这边的活动和资源通知也很值得留意。",
    "新清华学堂": "如果你想给一周安排一点文艺调剂，这一栏可以看看。",
    "物理系学术报告": "天气渐暖，楼里的讲座也慢慢热闹起来了。",
    "学生公益信息": "和志愿服务、公益活动有关的消息整理在这里。",
    "其他公众号信息": "下面这几条来自其他重点公众号，和校园动态联系更紧一些。",
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
