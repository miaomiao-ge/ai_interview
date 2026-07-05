import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

from core.config import SMTP_FROM, SMTP_PASSWORD, SMTP_PORT, SMTP_SECURITY, SMTP_SERVER, SMTP_USER


def _build_sender() -> tuple[str, str]:
    from_name, from_addr = parseaddr(SMTP_FROM or "")
    if not from_addr:
        from_name, from_addr = "AI面试系统", SMTP_USER
    return from_name or "AI面试系统", from_addr


def send_verification_email(to_email: str, code: str, purpose: str = "register") -> bool:
    """
    发送邮箱验证码。
    """
    if not all([SMTP_SERVER, SMTP_USER, SMTP_PASSWORD]):
        print(f"未配置 SMTP，控制台模拟发送 -> 邮箱: {to_email}, 验证码: 【{code}】")
        return True

    action_text = "注册新账号" if purpose == "register" else "重置密码"
    from_name, from_addr = _build_sender()

    mail_msg = f"""
    <h2>AI 面试系统</h2>
    <p>您正在尝试 <b>{action_text}</b>。</p>
    <p>您的验证码是：<strong style="color: #4CAF50; font-size: 24px;">{code}</strong></p>
    <p>该验证码 5 分钟内有效，请勿泄露给他人。</p>
    """

    message = MIMEText(mail_msg, "html", "utf-8")
    message["From"] = formataddr((str(Header(from_name, "utf-8")), from_addr))
    message["To"] = to_email
    message["Subject"] = Header(f"【AI面试系统】您的{action_text}验证码", "utf-8")

    try:
        port = int(SMTP_PORT or (465 if SMTP_SECURITY == "ssl" else 587))
        if SMTP_SECURITY == "ssl":
            smtp_obj = smtplib.SMTP_SSL(SMTP_SERVER, port)
        else:
            smtp_obj = smtplib.SMTP(SMTP_SERVER, port)
            if SMTP_SECURITY in {"tls", "starttls"}:
                smtp_obj.starttls()

        smtp_obj.login(SMTP_USER, SMTP_PASSWORD)
        smtp_obj.sendmail(from_addr, [to_email], message.as_string())
        smtp_obj.quit()
        print(f"邮件发送成功 -> {to_email}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False
