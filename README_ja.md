# Workbook Analyzer for Tableau

[![License: Polyform Noncommercial](https://img.shields.io/badge/License-Polyform_NC-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)

> **English README**: [README.md](README.md)

Tableau Cloudの**ワークブック分析に特化した**軽量ローカルWebアプリです。
リビジョン差分比較と計算フィールド依存関係分析に絞り込んだ設計で、数秒で起動します。

---

## なぜこのツールが必要か

[Cloud Admin Kit for Tableau](https://github.com/brave-data/Cloud_Admin_Kit_for_Tableau) はサイト全体の管理ダッシュボードですが、大規模サイトではワークブック・データソース・ビュー・ユーザー・スケジュールを全件取得するため、初回ロードに10〜30分以上かかることがあります。

**Workbook Analyzer** は起動時にワークブック一覧だけを取得（300件で約10秒）し、個々のワークブック分析はオンデマンドで実行します。特定のワークブックを深く分析したい場合に最適なツールです。

---

## 主な機能

### 1. リビジョン差分比較

ワークブックの任意の2リビジョンを比較して、何が変わったかを確認します。

- 名前またはプロジェクト名でワークブックを検索
- Base（比較元）と Head（比較先）のリビジョンを選択
- **追加 / 削除 / 変更** をカテゴリ別に表示：
  - **計算フィールド** — フィールド名・データソース・変更前後のフォーミュラ
  - **フィルター** — カテゴリ・数値・相対日付・上位Nフィルター
  - **接続データソース** — 追加・削除
  - **シート** — ワークシート・ダッシュボード・ストーリーの追加・削除
- 取得結果はリビジョンペアごとにキャッシュ

### 2. 計算フィールド依存関係分析

ワークブックをダウンロードして計算フィールドの依存関係を可視化します。

- フォーミュラ表示付きフィールド一覧（名前・フォーミュラで絞り込み可能）
- **Sankeyチャート**でどのフィールドがどのフィールドを参照しているかを視覚化

---

## クイックスタート

```bash
git clone https://github.com/brave-data/Workbook_Analyzer_for_Tableau.git
cd Workbook_Analyzer_for_Tableau
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Tableau Cloudの認証情報を入力
python main.py
```

ブラウザで **http://localhost:8001** を開きます。ワークブック一覧は数秒で表示されます。

---

## 設定

```ini
TABLEAU_SERVER_URL=https://10ay.online.tableau.com
TABLEAU_SITE_NAME=mycompany
TABLEAU_TOKEN_NAME=my-pat-name
TABLEAU_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxx
PORT=8001                                  # デフォルト: 8001（8000と競合しないよう設定済み）
```

---

## 技術スタック

- **バックエンド**: Python 3.11+、FastAPI、uvicorn、tableauserverclient、defusedxml
- **フロントエンド**: Bootstrap 5.3、Bootstrap Icons、D3.js（Sankey）
