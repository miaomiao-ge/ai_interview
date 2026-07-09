import os
import json
from dotenv import load_dotenv
try:
    from aliyunsdkcore.client import AcsClient
    from aliyunsdkcore.request import CommonRequest
except ImportError:
    AcsClient = None
    CommonRequest = None
# 自动寻找并加载项目根目录的 .env 文件
load_dotenv()

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"


def _env_enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _require_production_value(name: str, value: str | None, message: str | None = None) -> str:
    clean_value = (value or "").strip()
    if IS_PRODUCTION and not clean_value:
        raise RuntimeError(message or f"{name} is required when APP_ENV=production")
    return clean_value


MYSQL_URL_ENV = os.getenv("MYSQL_URL")
_require_production_value("MYSQL_URL", MYSQL_URL_ENV)

ALI_APPKEY = os.getenv("ALI_APPKEY")
ALI_APPKEY_EN = os.getenv("ALI_APPKEY_EN") or ALI_APPKEY
ALI_AK_ID = os.getenv("ALI_AK_ID")
ALI_AK_SECRET = os.getenv("ALI_AK_SECRET")
if not all([ALI_APPKEY, ALI_AK_ID, ALI_AK_SECRET]):
    print("WARNING: Aliyun API credentials are incomplete; check .env", flush=True)

# 邮箱配置
SMTP_SERVER = os.getenv("SMTP_SERVER") or os.getenv("XDU_EGLOBAL_SMTP_HOST") or os.getenv("NATCOOP_SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT") or os.getenv("XDU_EGLOBAL_SMTP_PORT") or os.getenv("NATCOOP_SMTP_PORT")
SMTP_SECURITY = (os.getenv("SMTP_SECURITY") or os.getenv("XDU_EGLOBAL_SMTP_SECURITY") or os.getenv("NATCOOP_SMTP_SECURITY") or "ssl").strip().lower()
SMTP_USER = os.getenv("SMTP_USER") or os.getenv("XDU_EGLOBAL_SMTP_USERNAME") or os.getenv("NATCOOP_SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") or os.getenv("XDU_EGLOBAL_SMTP_PASSWORD") or os.getenv("NATCOOP_SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM") or os.getenv("XDU_EGLOBAL_SMTP_FROM") or os.getenv("NATCOOP_SMTP_FROM")

# 🔐 JWT 鉴权配置
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if IS_PRODUCTION:
    _require_production_value("JWT_SECRET_KEY", SECRET_KEY)
    if SECRET_KEY == "fallback-secret-key" or len(SECRET_KEY) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be a non-default secret with at least 32 characters when APP_ENV=production")
else:
    SECRET_KEY = SECRET_KEY or "fallback-secret-key"
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# 注意：.env 读出来的是字符串，必须强制转换为 int 才能用于时间计算
ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_DAYS", 7))

# 并发与状态外置配置
_REDIS_URL_ENV = os.getenv("REDIS_URL")
_require_production_value("REDIS_URL", _REDIS_URL_ENV)
REDIS_URL = _REDIS_URL_ENV or "redis://localhost:6379/0"
REDIS_REQUIRED = _env_enabled("REDIS_REQUIRED", "1" if IS_PRODUCTION else "0")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "ai_interview")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", 7200))
OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", 300))
OTP_EMAIL_LIMIT_PER_WINDOW = int(os.getenv("OTP_EMAIL_LIMIT_PER_WINDOW", 5))
OTP_IP_LIMIT_PER_WINDOW = int(os.getenv("OTP_IP_LIMIT_PER_WINDOW", 20))
OTP_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("OTP_RATE_LIMIT_WINDOW_SECONDS", 3600))
LOGIN_LIMIT_PER_WINDOW = int(os.getenv("LOGIN_LIMIT_PER_WINDOW", 10))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 900))
ADMIN_LOGIN_LIMIT_PER_WINDOW = int(os.getenv("ADMIN_LOGIN_LIMIT_PER_WINDOW", 10))
WORKER_NODE_ID = os.getenv("WORKER_NODE_ID", "local-001")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", 10))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", 20))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", 30))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", 1800))
DB_AUTO_MIGRATE_ON_STARTUP = _env_enabled("DB_AUTO_MIGRATE_ON_STARTUP", "0" if IS_PRODUCTION else "1")
TASK_MAX_RETRIES = int(os.getenv("TASK_MAX_RETRIES", 3))
TASK_POLL_INTERVAL_SECONDS = float(os.getenv("TASK_POLL_INTERVAL_SECONDS", 2))
TASK_QUEUE_NAME = os.getenv("TASK_QUEUE_NAME", "interview_jobs")
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", 1))
MEDIA_RECORD_POLICY = os.getenv("MEDIA_RECORD_POLICY", "av_only")
OSS_PATH_PREFIX = os.getenv("OSS_PATH_PREFIX", "").strip("/")
MEDIA_UPLOAD_MAX_BYTES = int(os.getenv("MEDIA_UPLOAD_MAX_BYTES", 1024 * 1024 * 500))
ANSWER_AUDIO_UPLOAD_MAX_BYTES = int(os.getenv("ANSWER_AUDIO_UPLOAD_MAX_BYTES", 1024 * 1024 * 50))
ASR_FILE_TIMEOUT_SECONDS = int(os.getenv("ASR_FILE_TIMEOUT_SECONDS", 90))
ASR_STREAM_SLEEP_SECONDS = float(os.getenv("ASR_STREAM_SLEEP_SECONDS", 0.005))
ASR_DEBUG_LOG = os.getenv("ASR_DEBUG_LOG", "1").strip().lower() in {"1", "true", "yes", "on"}
ASR_ENABLE_INTERMEDIATE_RESULT = os.getenv("ASR_ENABLE_INTERMEDIATE_RESULT", "1").strip().lower() in {"1", "true", "yes", "on"}
ASR_ENABLE_PUNCTUATION_PREDICTION = os.getenv("ASR_ENABLE_PUNCTUATION_PREDICTION", "1").strip().lower() in {"1", "true", "yes", "on"}
ASR_ENABLE_INVERSE_TEXT_NORMALIZATION = os.getenv("ASR_ENABLE_INVERSE_TEXT_NORMALIZATION", "1").strip().lower() in {"1", "true", "yes", "on"}
ASR_START_TIMEOUT_SECONDS = int(os.getenv("ASR_START_TIMEOUT_SECONDS", 10))
ASR_PING_INTERVAL_SECONDS = int(os.getenv("ASR_PING_INTERVAL_SECONDS", 8))
MAX_ACTIVE_INTERVIEWS = int(os.getenv("MAX_ACTIVE_INTERVIEWS", 300))
MAX_ACTIVE_ASR_CONNECTIONS = int(os.getenv("MAX_ACTIVE_ASR_CONNECTIONS", 300))
ACTIVE_SESSION_TTL_SECONDS = int(os.getenv("ACTIVE_SESSION_TTL_SECONDS", SESSION_TTL_SECONDS))
ASR_CONNECTION_TTL_SECONDS = int(os.getenv("ASR_CONNECTION_TTL_SECONDS", 20 * 60))
LLM_MAX_CONCURRENT = int(os.getenv("LLM_MAX_CONCURRENT", 20))
TTS_MAX_CONCURRENT = int(os.getenv("TTS_MAX_CONCURRENT", 40))
ASR_FILE_MAX_CONCURRENT = int(os.getenv("ASR_FILE_MAX_CONCURRENT", 10))

ALI_FACEBODY_ENDPOINT = os.getenv("ALI_FACEBODY_ENDPOINT", "facebody.cn-shanghai.aliyuncs.com")
FACE_VERIFY_ENABLED = os.getenv("FACE_VERIFY_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
FACE_COMPARE_THRESHOLD = float(os.getenv("FACE_COMPARE_THRESHOLD", 70))
FACE_LIVENESS_REQUIRED = os.getenv("FACE_LIVENESS_REQUIRED", "1").strip().lower() in {"1", "true", "yes", "on"}
FACE_VERIFY_TTL_SECONDS = int(os.getenv("FACE_VERIFY_TTL_SECONDS", 300))
FACE_IMAGE_SIGN_EXPIRE_SECONDS = int(os.getenv("FACE_IMAGE_SIGN_EXPIRE_SECONDS", 300))
FACE_IMAGE_MAX_BYTES = int(os.getenv("FACE_IMAGE_MAX_BYTES", 2 * 1024 * 1024))
FACE_CONSENT_VERSION = os.getenv("FACE_CONSENT_VERSION", "2026-06-01")
FACE_OSS_ENDPOINT = os.getenv("FACE_OSS_ENDPOINT") or os.getenv("ALI_OSS_ENDPOINT")
FACE_OSS_BUCKET_NAME = os.getenv("FACE_OSS_BUCKET_NAME") or os.getenv("ALI_OSS_BUCKET_NAME")
XIDIAN_STUDENT_API_BASE_URL = os.getenv(
    "XIDIAN_STUDENT_API_BASE_URL",
    "https://xdgjxs.xidian.edu.cn/smjFrame/foreignStudentInfo",
).rstrip("/")
XIDIAN_STUDENT_APP_KEY = (os.getenv("XIDIAN_STUDENT_APP_KEY") or "").strip()
XIDIAN_STUDENT_APP_SECRET = (os.getenv("XIDIAN_STUDENT_APP_SECRET") or "").strip()
XIDIAN_STUDENT_REQUEST_TIMEOUT_SECONDS = float(os.getenv("XIDIAN_STUDENT_REQUEST_TIMEOUT_SECONDS", 120))
XIDIAN_STUDENT_PHOTO_MAX_BYTES = int(os.getenv("XIDIAN_STUDENT_PHOTO_MAX_BYTES", 5 * 1024 * 1024))
PROCTORING_ENABLED = os.getenv("PROCTORING_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
PROCTORING_INTERVAL_SECONDS = int(os.getenv("PROCTORING_INTERVAL_SECONDS", 10))
PROCTORING_IDENTITY_RECHECK_INTERVAL_SECONDS = int(os.getenv("PROCTORING_IDENTITY_RECHECK_INTERVAL_SECONDS", 10))
PROCTORING_MIN_INTERVAL_SECONDS = int(os.getenv("PROCTORING_MIN_INTERVAL_SECONDS", 8))
PROCTORING_STORE_RAW_RESULT = os.getenv("PROCTORING_STORE_RAW_RESULT", "0").strip().lower() in {"1", "true", "yes", "on"}
EXTERNAL_RESULT_API_KEY = (os.getenv("EXTERNAL_RESULT_API_KEY") or "").strip()
EXTERNAL_RESULT_APP_KEY = (os.getenv("EXTERNAL_RESULT_APP_KEY") or "").strip()
EXTERNAL_RESULT_APP_SECRET = (os.getenv("EXTERNAL_RESULT_APP_SECRET") or "").strip()
EXTERNAL_RESULT_TOKEN_EXPIRE_SECONDS = int(os.getenv("EXTERNAL_RESULT_TOKEN_EXPIRE_SECONDS", 24 * 3600))


def get_aliyun_asr_appkey(language: str = "zh") -> str:
    return ALI_APPKEY_EN if (language or "").lower().startswith("en") and ALI_APPKEY_EN else ALI_APPKEY


def get_aliyun_asr_start_options() -> dict:
    return {
        "aformat": "pcm",
        "sample_rate": 16000,
        "ch": 1,
        "enable_intermediate_result": ASR_ENABLE_INTERMEDIATE_RESULT,
        "enable_punctuation_prediction": ASR_ENABLE_PUNCTUATION_PREDICTION,
        "enable_inverse_text_normalization": ASR_ENABLE_INVERSE_TEXT_NORMALIZATION,
        "timeout": ASR_START_TIMEOUT_SECONDS,
        "ping_interval": ASR_PING_INTERVAL_SECONDS,
    }

# 管理员账号
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
SUPER_ADMIN_USERNAME = os.getenv("SUPER_ADMIN_USERNAME")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD")
_require_production_value("SUPER_ADMIN_USERNAME", SUPER_ADMIN_USERNAME)
_require_production_value("SUPER_ADMIN_PASSWORD", SUPER_ADMIN_PASSWORD)
if IS_PRODUCTION and SUPER_ADMIN_PASSWORD == "super_admin123":
    raise RuntimeError("SUPER_ADMIN_PASSWORD must not use the development default when APP_ENV=production")

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not DASHSCOPE_API_KEY:
    print("WARNING: DASHSCOPE_API_KEY is not configured", flush=True)
LLM_BASE_URL = os.getenv("LLM_BASE_URL")

# 缓存 Token，阿里云的 Token 有效期为 24 小时，不需要每次都请求
_cached_token = None


def get_aliyun_token():
    global _cached_token
    if _cached_token:
        return _cached_token

    if AcsClient is None or CommonRequest is None:
        print("Failed to get Aliyun token: aliyunsdkcore is not installed", flush=True)
        return ""

    try:
        # 创建客户端实例
        client = AcsClient(ALI_AK_ID, ALI_AK_SECRET, 'cn-shanghai')
        # 创建请求并设置参数
        request = CommonRequest()
        request.set_method('POST')
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
        request.set_version('2019-02-28')
        request.set_action_name('CreateToken')

        # 发起请求并解析结果
        response = client.do_action_with_exception(request)
        jss = json.loads(response)
        _cached_token = jss['Token']['Id']
        print(f"Aliyun temporary token acquired: {_cached_token[:6]}***", flush=True)
        return _cached_token
    except Exception as e:
        print(f"Failed to get Aliyun token: {e}", flush=True)
        return ""
