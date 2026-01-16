import smtplib
from email.message import EmailMessage
from datetime import datetime

from email_credentials import (
    SMTP_EMAIL,
    SMTP_PASSWORD,
    SMTP_SERVER,
    SMTP_PORT,
)


def send_certificate_email(user, certificate):
    """
    Sends certificate issuance email after successful payment.
    """

    verify_url = f"https://ips-photoart.github.io/verify/{certificate.certificate_code}"
    download_url = f"https://ips-photoart.github.io/certificate/{certificate.certificate_code}/download"

    subject = "Issuance of Certificate – Indian Photographic Society"

    text_content = f"""
To,
{user.full_name}

This is to inform you that upon successful completion of the prescribed assessment
and confirmation of payment, your Certificate has been duly issued by the
Indian Photographic Society.

Certificate Code : {certificate.certificate_code}
Result           : {certificate.grade} ({certificate.percentage}%)
Date of Issue    : {certificate.issued_at.strftime('%d %B %Y')}

Verification Link:
{verify_url}

Download Link:
{download_url}

This is a system-generated email.
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Certificate Issued</title>
</head>
<body style="font-family:Arial, Helvetica, sans-serif;">

  <h2>Indian Photographic Society</h2>
  <p><strong>Certificate Issuance Notification</strong></p>

  <p>
    To,<br>
    <strong>{user.full_name}</strong>
  </p>

  <p>
    Your certificate has been successfully issued after confirmation of payment.
  </p>

  <table cellpadding="6">
    <tr><td><strong>Certificate Code</strong></td><td>{certificate.certificate_code}</td></tr>
    <tr><td><strong>Result</strong></td><td>{certificate.grade} ({certificate.percentage}%)</td></tr>
    <tr><td><strong>Date of Issue</strong></td><td>{certificate.issued_at.strftime('%d %B %Y')}</td></tr>
  </table>

  <p>
    <a href="{verify_url}">Verify Certificate</a><br>
    <a href="{download_url}">Download Certificate</a>
  </p>

  <p>
    This is an automated system email. Please do not reply.
  </p>

</body>
</html>
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_EMAIL
    msg["To"] = user.email

    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)
