import os, sys, requests
from dotenv import load_dotenv
load_dotenv("/root/.env")

RESEND_KEY = os.getenv("RESEND_API_KEY")
def send(to, subject, text):
    payload = {"from": "Empire AI <hello@empire-ai.co.uk>", "to": [to], "subject": subject, "text": text}
    r = requests.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"}, json=payload)
    print(to, r.status_code)
    return r.status_code == 200
if __name__ == "__main__":
    send(sys.argv[1], sys.argv[2], sys.argv[3])
