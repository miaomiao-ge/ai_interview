import os
import sys
from types import SimpleNamespace, ModuleType


os.environ.setdefault(
    "MYSQL_URL",
    "mysql+pymysql://test_user:test_password@127.0.0.1:3306/test_interview_db?charset=utf8mb4",
)

sys.modules.setdefault(
    "pymysql",
    SimpleNamespace(
        paramstyle="pyformat",
        threadsafety=1,
        apilevel="2.0",
        connect=lambda *args, **kwargs: None,
    ),
)

aliyunsdkcore_module = sys.modules.setdefault("aliyunsdkcore", ModuleType("aliyunsdkcore"))
aliyunsdkcore_client = sys.modules.setdefault("aliyunsdkcore.client", ModuleType("aliyunsdkcore.client"))
aliyunsdkcore_request = sys.modules.setdefault("aliyunsdkcore.request", ModuleType("aliyunsdkcore.request"))
aliyunsdkcore_client.AcsClient = getattr(aliyunsdkcore_client, "AcsClient", object)
aliyunsdkcore_request.CommonRequest = getattr(aliyunsdkcore_request, "CommonRequest", object)
aliyunsdkcore_module.client = aliyunsdkcore_client
aliyunsdkcore_module.request = aliyunsdkcore_request
