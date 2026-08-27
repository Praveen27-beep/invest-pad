"""Send a test email via Mailgun's HTTP API. Reads credentials from the environment --
run via `python -m dotenv run -- python scripts/mailgun_send.py` or export
MAILGUN_API_KEY / MAILGUN_DOMAIN / MAILGUN_BASE_URL first."""

import os

import requests


def send_simple_message() -> requests.Response:
    domain = os.environ["MAILGUN_DOMAIN"]
    base_url = os.environ["MAILGUN_BASE_URL"]
    return requests.post(
        f"{base_url}/v3/{domain}/messages",
        auth=("api", os.environ["MAILGUN_API_KEY"]),
        data={
            "from": f"Mailgun Sandbox <postmaster@{domain}>",
            "to": "PARASURAMA PRAVEEN M MUTHUKUMAR <praveen.muthukumar99@gmail.com>",
            "subject": "Hello PARASURAMA PRAVEEN M MUTHUKUMAR",
            "text": "Congratulations PARASURAMA PRAVEEN M MUTHUKUMAR, you just sent an email with Mailgun! You are truly awesome!",
        },
    )


if __name__ == "__main__":
    response = send_simple_message()
    print(response.status_code, response.json())
