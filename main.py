#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
オーロラ号予約監視スクリプト（環境変数版）
2026年2月の全日程の空き状況をチェックして、変化があればSlackに通知します
"""

import requests
from bs4 import BeautifulSoup
import time
import json
import os
from datetime import datetime

# ========== 設定 ==========
# 環境変数からWebhook URLを取得（セキュリティ対策）
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
CHECK_INTERVAL = 600  # チェック間隔（秒）10分 = 600秒
TARGET_URL = "https://www.ms-aurora.com/abashiri/reserves/new.php?ym=2026-02"
STATE_FILE = "aurora_state.json"  # 状態を保存するファイル

# ========== 関数定義 ==========

def send_slack_notification(message):
    """Slackに通知を送信"""
    try:
        payload = {
            "text": message,
            "username": "オーロラ号監視bot",
            "icon_emoji": ":ship:"
        }
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        if response.status_code == 200:
            print("✓ Slack通知送信成功")
        else:
            print(f"✗ Slack通知送信失敗: {response.status_code}")
    except Exception as e:
        print(f"✗ Slack通知エラー: {e}")


def get_availability_status():
    """予約ページから空き状況を取得"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        response = requests.get(TARGET_URL, headers=headers, timeout=30)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"✗ ページ取得失敗: {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 全テーブルを取得
        tables = soup.find_all('table')
        if len(tables) < 3:
            print("✗ カレンダーテーブルが見つかりません")
            return None
        
        # 3番目のテーブルがカレンダー
        calendar_table = tables[2]  # 0始まりなので[2]が3番目
        
        availability = {}
        
        # まず全日程を満席として初期化
        for i in range(1, 29):  # 2月は最大28日
            availability[f"2月{i}日"] = '×'
        
        # 全てのセルをチェック
        for cell in calendar_table.find_all('td'):
            # リンクがあるセルのみ処理
            link = cell.find('a')
            if link and 'ynj=' in link.get('href', ''):
                # 日付を抽出
                href = link.get('href')
                date_str = href.split('ynj=')[1].split('#')[0]  # 例: 2026-2-2
                day = date_str.split('-')[-1]
                day_key = f"2月{day}日"
                
                # emタグの中身を取得（○や△が入ってる）
                em_tag = link.find('em')
                if em_tag:
                    status_text = em_tag.get_text(strip=True)
                    
                    if '○' in status_text:
                        availability[day_key] = '○'
                        print(f"✓ {day_key}: ○ を検出")
                    elif '△' in status_text:
                        availability[day_key] = '△'
                        print(f"✓ {day_key}: △ を検出")
        
        # デバッグ：検出した空き状況を表示
        available = [k for k, v in availability.items() if v in ['○', '△']]
        print(f"空きのある日: {len(available)}日")
        
        return availability
        
    except Exception as e:
        print(f"✗ データ取得エラー: {e}")
        import traceback
        traceback.print_exc()
        return None


def load_previous_state():
    """前回の状態を読み込み"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_current_state(state):
    """現在の状態を保存"""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"✗ 状態保存エラー: {e}")


def compare_and_notify(current_status, previous_status):
    """状態を比較して変更があれば通知"""
    if not previous_status:
        # 初回実行
        message = "🚢 *オーロラ号監視を開始しました*\n\n"
        message += "📅 *2026年2月の現在の空き状況:*\n"
        
        # 空きがある日をリストアップ
        available_days = []
        for day in sorted(current_status.keys(), key=lambda x: int(x.replace('2月', '').replace('日', ''))):
            status = current_status[day]
            if status in ['○', '△']:
                available_days.append(f"  • {day}: {status}")
        
        if available_days:
            message += "\n".join(available_days)
        else:
            message += "  現在空きのある日はありません（全て満席）"
        
        message += f"\n\n⏰ {CHECK_INTERVAL // 60}分おきに監視します"
        send_slack_notification(message)
        return
    
    # 変更を検出
    changes = []
    for day in sorted(current_status.keys(), key=lambda x: int(x.replace('2月', '').replace('日', ''))):
        current = current_status[day]
        previous = previous_status.get(day, '×')
        
        if current != previous:
            emoji = "🎉" if current in ['○', '△'] else "😢"
            changes.append(f"{emoji} *{day}*: {previous} → {current}")
    
    if changes:
        message = "🚨 *オーロラ号の空き状況が変わりました！*\n\n"
        message += "\n".join(changes)
        message += f"\n\n🔗 予約ページ: {TARGET_URL}"
        send_slack_notification(message)
        print(f"✓ 変更検出: {len(changes)}件")
    else:
        print("変更なし")


def main():
    """メイン処理"""
    print("=" * 50)
    print("オーロラ号予約監視スクリプト起動")
    print("=" * 50)
    
    # Webhook URLのチェック
    if not SLACK_WEBHOOK_URL:
        print("\n⚠️  エラー: Slack Webhook URLが設定されていません！")
        print("環境変数 SLACK_WEBHOOK_URL を設定してください。")
        return
    
    print(f"監視URL: {TARGET_URL}")
    print(f"チェック間隔: {CHECK_INTERVAL}秒（{CHECK_INTERVAL // 60}分）")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nCtrl+C で停止できます\n")
    
    try:
        while True:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] チェック中...")
            
            # 現在の状況を取得
            current_status = get_availability_status()
            
            if current_status:
                # 前回の状態を読み込み
                previous_status = load_previous_state()
                
                # 比較して通知
                compare_and_notify(current_status, previous_status)
                
                # 現在の状態を保存
                save_current_state(current_status)
            else:
                print("✗ 状態取得に失敗しました")
            
            # 次のチェックまで待機
            print(f"次のチェック: {CHECK_INTERVAL}秒後...")
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\n監視を停止しました")
    except Exception as e:
        print(f"\n✗ 予期しないエラー: {e}")


if __name__ == "__main__":
    main()
