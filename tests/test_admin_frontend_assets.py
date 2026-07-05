import mimetypes
from pathlib import Path


def test_admin_html_contains_readable_user_management_labels():
    admin_html = Path("frontend/admin/admin.html").read_text(encoding="utf-8")

    expected_labels = [
        "西电 AI 面试系统 - 管理控制台",
        "管理端登录",
        "用户管理",
        "用户名",
        "登录日志",
        "操作日志",
        "退出登录",
    ]

    for label in expected_labels:
        assert label in admin_html


def test_main_registers_mjs_as_javascript():
    main_source = Path("main.py").read_text(encoding="utf-8")

    assert 'mimetypes.add_type("text/javascript", ".mjs")' in main_source
    mimetypes.add_type("text/javascript", ".mjs")
    assert mimetypes.guess_type("admin/report_parser.mjs")[0] == "text/javascript"
