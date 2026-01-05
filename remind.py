import os
import requests
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DB_ID = os.environ["NOTION_DB_ID"]
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

# ===== Notionの列名（違ったらここだけ変える）=====
TITLE_PROP = "名前"         # Title
TAGS_PROP = "タグ"          # Multi-select
STATUS_PROP = "ステータス"  # Status or Select
ASSIGNEE_PROP = "割り振り"  # People
DUE_PROP = "期限"           # Date
# ===============================================

DONE_STATUSES = {"完了", "Done"}  # 完了扱いの名称（必要なら追加）

def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

def slack_post(text: str):
    r = requests.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=30)
    r.raise_for_status()

def notion_query_due_today():
    today = datetime.now(JST).date()
    payload = {
        "filter": {
            "property": DUE_PROP,
            "date": {"equals": str(today)}
        },
        "page_size": 100
    }
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    r = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["results"], str(today)

def get_title(page):
    prop = page["properties"].get(TITLE_PROP, {})
    items = prop.get("title", [])
    return "".join(x.get("plain_text", "") for x in items) or "(無題)"

def get_due(page):
    d = page["properties"].get(DUE_PROP, {}).get("date")
    return (d or {}).get("start", "")[:10] if d else None

def get_status(page):
    prop = page["properties"].get(STATUS_PROP, {})
    if prop.get("status"):
        return prop["status"]["name"]
    if prop.get("select"):
        return prop["select"]["name"]
    return None

def get_tags(page):
    prop = page["properties"].get(TAGS_PROP, {})
    ms = prop.get("multi_select") or []
    return [x.get("name", "") for x in ms if x.get("name")]

def get_assignees(page):
    prop = page["properties"].get(ASSIGNEE_PROP, {})
    people = prop.get("people") or []
    # Slackのユーザー名と一致させる必要はないので、Notion表示名をそのまま出す
    return [p.get("name", "") for p in people if p.get("name")]

def main():
    pages, today_str = notion_query_due_today()

    targets = []
    for p in pages:
        status = get_status(p)
        if status in DONE_STATUSES:
            continue
        targets.append(p)

    if not targets:
        print("No targets.")
        return

    lines = []
    for p in targets:
        title = get_title(p)
        due = get_due(p) or today_str
        status = get_status(p) or "-"
        tags = get_tags(p)
        assignees = get_assignees(p)
        url = p.get("url", "")

        tag_text = f" / タグ: {', '.join(tags)}" if tags else ""
        asg_text = f" / 割り振り: {', '.join(assignees)}" if assignees else ""

        lines.append(f"• {due} / {status}{tag_text}{asg_text}\n  {title}\n  {url}")

    msg = "⏰【本日期限】未完了のNotion項目\n" + "\n\n".join(lines)
    slack_post(msg)
    print(f"Posted {len(targets)} items.")

if __name__ == "__main__":
    main()
