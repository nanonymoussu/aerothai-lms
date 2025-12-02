import json
import re
import sys
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from bs4.element import AttributeValueList

# --- CONFIGURATIONS ---
USERNAME = "YOUR_USERNAME"
PASSWORD = "YOUR_PASSWORD"
USER_ID = "YOUR_USERID"  # Example: "3759"
BASE_URL = "https://lms.aerothai.co.th"
# ----------------------


def get_video_id(html_content: str) -> str | AttributeValueList | None:
    patterns: list[str] = [
        r'["\']videoId["\']\s*:\s*(\d+)',
        r'videoId\s*[:=]\s*["\']?(\d+)["\']?',
        r'data-video-id=["\']?(\d+)["\']?',
        r'evaid=["\']?(\d+)["\']?',
    ]
    for pattern in patterns:
        if match := re.search(pattern=pattern, string=html_content, flags=re.IGNORECASE):
            return match.group(1)

    # Fallback: Search in input fields
    soup = BeautifulSoup(markup=html_content, features="html.parser")
    if input_tag := (
        soup.find(name="input", attrs={"id": "videoId"})
        or soup.find(name="input", attrs={"name": "videoId"})
    ):
        return input_tag.get(key="value")

    return None


def get_video_duration(html_content: str) -> int:
    patterns: list[str] = [
        r'["\']duration["\']\s*:\s*(\d+)',
        r"duration\s*[:=]\s*(\d+)",
        r'data-duration=["\']?(\d+)["\']?',
    ]
    for pattern in patterns:
        if match := re.search(pattern=pattern, string=html_content, flags=re.IGNORECASE):
            return int(match.group(1))

    return 3000


def main() -> None:
    # Check arguments
    if len(sys.argv) < 2:
        print("Usage: uv run main.py <URL> [DURATION] or python main.py <URL> [DURATION]")
        sys.exit(1)

    url: str = sys.argv[1]

    # Minutes -> Seconds
    custom_duration: int | None = None
    if len(sys.argv) >= 3:
        try:
            minutes_input: float = float(sys.argv[2])
            custom_duration: int | None = int(minutes_input * 60)
        except ValueError:
            print("❌ Error. Time argument must be a number (minutes).")
            sys.exit(1)

    params: dict[str, list[str]] = parse_qs(qs=urlparse(url=url).query)

    try:
        course_id: str = url.split(sep="/Index/")[1].split(sep="?")[0]
        csm: str | None = params.get("csm", [None])[0]
        cb: str | None = params.get("cb", [None])[0]
        cs: str | None = params.get("cs", [None])[0]
    except IndexError:
        print("❌ Invalid URL format")
        sys.exit(1)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
    )

    # 1. Login
    print("[*] Logging in...")
    try:
        r_login_page: requests.Response = session.get(url=f"{BASE_URL}/Account/Login")
        token_input: Tag | None = BeautifulSoup(
            markup=r_login_page.text, features="html.parser"
        ).find(name="input", attrs={"name": "__RequestVerificationToken"})
        token: str | AttributeValueList = token_input["value"] if token_input else ""
        r_login: requests.Response = session.post(
            url=f"{BASE_URL}/Account/Login",
            data={
                "Username": USERNAME,
                "Password": PASSWORD,
                "RememberMe": "true",
                "__RequestVerificationToken": token,
            },
        )

        if r_login.json().get("Success") != "Success":
            print(f"❌ Login Failed: {r_login.json().get('Message')}")
            sys.exit(1)

        user_id: str = r_login.json().get("UserID") or USER_ID
        print(f"✅ Login Success! (User ID: {user_id})")
    except Exception as error:
        print(f"❌ Login Error: {error}")
        sys.exit(1)

    # 2. Scrape Video Info
    print("[*] Scraping Video Info...")
    session.headers.update(
        {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    )
    r_page: requests.Response = session.get(url=url)

    video_id: str | AttributeValueList | None = get_video_id(html_content=r_page.text)
    if not video_id:
        print("❌ Could not find Video ID. Check if URL is correct.")
        sys.exit(1)

    duration: int
    if custom_duration:
        duration = custom_duration
    else:
        duration = get_video_duration(html_content=r_page.text)

    print(f"✅ Video ID: {video_id}, Duration: {duration} seconds")

    # 3. Send Progress (Multipart/Form-Data)
    print(f"[*] Sending Progress Update ({duration}s)...")

    # Create timestamp array
    ts_array: list[str] = [str(i) for i in range(1, duration + 1)]

    inner_data: dict[str, object] = {
        "courseId": int(course_id),
        "courseBatchId": cb,
        "courseSectionId": int(str(cs)),
        "courseSectionModuleId": int(str(csm)),
        "videoId": int(str(video_id)),
        "userId": str(user_id),
        "timestamp": ts_array,
        "progress": 100,
    }

    form_data: dict[str, str] = {
        "courseId": str(course_id),
        "courseSectionModuleId": str(csm),
        "cb": str(cb),
        "progressData": json.dumps(inner_data),
    }

    session.headers.update(
        {"Referer": url, "Accept": "application/json, text/javascript, */*; q=0.01"}
    )
    if "Content-Type" in session.headers:
        del session.headers["Content-Type"]

    r_update: requests.Response = session.post(
        url=f"{BASE_URL}/Learning/UpdateProgressData/", data=form_data
    )

    if r_update.status_code == 200 and "Login" not in r_update.text:
        print(f"🎉 Success! Response: {r_update.text}")
    else:
        print(f"❌ Failed: {r_update.status_code} - {r_update.text[:100]}")


if __name__ == "__main__":
    main()
