import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.config import settings

def send_email(
    receiver_email: str,
    subject: str,
    content_body: str,
):
    # setting sender
    sender = settings.emaling.host_user

    # set email message
    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = receiver_email
    message["Subject"] = subject

    message.attach(
        MIMEText(content_body, "plain")
    )

    # set email connection and send
    with smtplib.SMTP("smtp.gmail.com", settings.emaling.port) as connection:
        connection.starttls()
        # login to sender
        connection.login(sender, settings.emaling.host_password)
        # send email message
        connection.send_message(message)
