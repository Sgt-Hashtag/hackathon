import os
from twilio.rest import Client

# --- CONFIG ---
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

client = Client(ACCOUNT_SID, AUTH_TOKEN)

def send_invitation_sms(name, phone, policy_id="policy_99", policy_name="Urban Green Space"):
    """Generates and sends the Habermasian invitation"""
    body = (
        f"Hi {name}, the new policy '{policy_name}' affects your area. "
        f"As a resident, your input is prioritized. "
        f"Chat with us: https://t.me/Community101Bot?start={policy_id}"
    )
    try:
        message = client.messages.create(
            body=body,
            from_=TWILIO_NUMBER,
            to=phone
        )
        return message.sid
    except Exception as e:
        print(f"❌ Twilio Error for {phone}: {e}")
        return None