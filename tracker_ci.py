import json, os, sys, requests
from datetime import datetime
from pathlib import Path
import pytz

TW = pytz.timezone("Asia/Taipei")
STATE_FILE = Path("state.json")

def now_tw(): return datetime.now(TW)
def now_str(): return now_tw().strftime("%Y/%m/%d %H:%M:%S")
def parse_tw(s):
    return TW.localize(datetime.strptime(s, "%Y-%m-%d %H:%M"))

def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

def save_state(s):
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))

def get_active_rule(cfg):
    now = now_tw()
    for rule in cfg.get("schedules", []):
        try:
            if parse_tw(rule["start"]) <= now <= parse_tw(rule["end"]):
                return rule
        except Exception:
            pass
    return None

def fetch_product(url):
    json_url = url.rstrip("/")
    if not json_url.endswith(".json"):
        json_url += ".json"
    try:
        r = requests.get(json_url, timeout=15, headers={"User-Agent": "KMonstar-CI/1.0"})
        r.raise_for_status()
        d = r.json()
        v = d.get("variants", [])
        return {"id": d.get("id"), "title": d.get("title", "（未知）"),
                "inventory_quantity": v[0].get("inventory_quantity", 0) if v else 0}
    except Exception as e:
        print(f"[錯誤] {e}"); return None

def get_name(cfg, p_cfg, fetched):
    pid = str(fetched.get("id", ""))
    if pid in cfg.get("id_name_map", {}): return cfg["id_name_map"][pid]
    if p_cfg.get("custom_name"): return p_cfg["custom_name"]
    return fetched.get("title", "（未知）")

def send_dc(url, msg):
    if not url: print(msg); return
    try: requests.post(url, json={"content": msg}, timeout=10).raise_for_status()
    except Exception as e: print(f"[DC錯誤] {e}")

def main():
    cfg     = json.loads(Path("config.json").read_text(encoding="utf-8"))
    state   = load_state()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL") or cfg.get("discord_webhook_url", "")
    rule    = get_active_rule(cfg)

    print(f"[CI] {now_str()}")
    if not rule:
        print("[CI] 不在排程時段，結束"); sys.exit(0)

    for p_cfg in cfg.get("products", []):
        url = p_cfg.get("url", "").strip()
        if not url: continue
        f = fetch_product(url)
        if not f: continue

        pid      = str(f["id"])
        name     = get_name(cfg, p_cfg, f)
        inv_now  = f["inventory_quantity"]
        inv_prev = state.get(pid)

        if inv_prev is not None and inv_now != inv_prev:
            diff = inv_prev - inv_now 
            sign = f"+{diff}" if diff > 0 else str(diff)
            msg = f"❗️【銷量變動】\n活動：{name}\n時間：{now_str()}\n庫存：{inv_now} ({sign})"
            print(msg); send_dc(webhook, msg)

        msg = f"【自動更新】\n活動：{name}\n時間：{now_str()}\n庫存：{inv_now}"
        print(msg); send_dc(webhook, msg)
        state[pid] = inv_now

    save_state(state)

if __name__ == "__main__":
    main()
