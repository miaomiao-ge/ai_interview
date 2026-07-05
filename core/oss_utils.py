import os
from urllib.parse import quote

from dotenv import load_dotenv

# Keep Aliyun traffic off local/global proxy settings.
os.environ["NO_PROXY"] = "aliyuncs.com,aliyun.com,localhost,127.0.0.1"
for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
    os.environ.pop(key, None)

load_dotenv()

ALI_AK_ID = os.getenv("ALI_AK_ID")
ALI_AK_SECRET = os.getenv("ALI_AK_SECRET")
ALI_OSS_ENDPOINT = os.getenv("ALI_OSS_ENDPOINT")
ALI_OSS_BUCKET_NAME = os.getenv("ALI_OSS_BUCKET_NAME")


def _get_oss2():
    import oss2

    return oss2


def _normalized_endpoint(endpoint: str | None = None) -> str:
    endpoint = (endpoint or ALI_OSS_ENDPOINT or "").strip()
    if endpoint and not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    return endpoint


def _build_bucket(endpoint: str | None = None, bucket_name: str | None = None):
    oss2 = _get_oss2()
    auth = oss2.Auth(ALI_AK_ID, ALI_AK_SECRET)
    return oss2.Bucket(auth, _normalized_endpoint(endpoint), bucket_name or ALI_OSS_BUCKET_NAME)


def _build_public_url(oss_file_name: str, endpoint: str | None = None, bucket_name: str | None = None) -> str:
    clean_endpoint = _normalized_endpoint(endpoint).replace("https://", "").replace("http://", "")
    return f"https://{bucket_name or ALI_OSS_BUCKET_NAME}.{clean_endpoint}/{quote(oss_file_name, safe='/')}"


def upload_to_oss(local_file_path: str, oss_file_name: str, raise_on_error: bool = False) -> str:
    """Upload a local file to Aliyun OSS and return its browser URL."""
    if not os.path.exists(local_file_path):
        if raise_on_error:
            raise FileNotFoundError(local_file_path)
        return ""

    try:
        bucket = _build_bucket()
        bucket.put_object_from_file(oss_file_name, local_file_path)
        url = _build_public_url(oss_file_name)
        print(f"☁️ 成功上传到 OSS: {url}")
        return url
    except Exception as e:
        print(f"❌ OSS 上传失败: {e}")
        if raise_on_error:
            raise
        return ""


def upload_bytes_to_oss(
    data: bytes,
    oss_file_name: str,
    raise_on_error: bool = False,
    endpoint: str | None = None,
    bucket_name: str | None = None,
    quiet: bool = False,
) -> str:
    """Upload in-memory bytes to Aliyun OSS and return its browser URL."""
    try:
        bucket = _build_bucket(endpoint, bucket_name)
        bucket.put_object(oss_file_name, data)
        url = _build_public_url(oss_file_name, endpoint, bucket_name)
        if not quiet:
            print(f"☁️ 成功上传到 OSS: {url}")
        return url
    except Exception as e:
        if not quiet:
            print(f"❌ OSS 上传失败: {e}")
        if raise_on_error:
            raise
        return ""


def sign_oss_url(
    oss_file_name: str,
    expire_seconds: int = 300,
    endpoint: str | None = None,
    bucket_name: str | None = None,
) -> str:
    """Return a short-lived private OSS URL for backend provider calls or admin preview."""
    try:
        bucket = _build_bucket(endpoint, bucket_name)
        return bucket.sign_url("GET", oss_file_name, int(expire_seconds or 300), slash_safe=False)
    except Exception as e:
        print(f"鉂?OSS 绛惧悕 URL 鐢熸垚澶辫触: {e}")
        return ""
