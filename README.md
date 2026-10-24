# store-review-downloader

公開されている App Store と Google Play のレビューを、直近 6 ヶ月分ダウンロードします。星だけの評価は含まれません。

Python 3 の標準ライブラリだけで動きます。追加のインストールはありません。

## 設定

対象アプリは環境変数で指定します。リポジトリ直下の `.env` も読みます。シェルにすでに設定されている値が優先されます。

```
PROJECT=myapp
APP_NAME=My App
IOS_APP_ID=1234567890
ANDROID_PACKAGE=com.example.myapp
```

| 変数 | 内容 |
| --- | --- |
| `PROJECT` | 出力ファイル名に使う識別子。英数字、ハイフン、アンダースコア |
| `APP_NAME` | サマリーに書く表示名 |
| `IOS_APP_ID` | App Store の数値 ID |
| `ANDROID_PACKAGE` | Google Play のパッケージ名 |

`.env.example` をコピーして値を入れます。

```
cp .env.example .env
```

## 実行

```
python3 download_reviews.py
python3 download_play_reviews.py
```

ファイルはスクリプトと同じディレクトリに書き出します。

- `{PROJECT}-ios-reviews-past-6-months.csv`
- `{PROJECT}-ios-reviews-past-6-months.json`
- `summary.json`
- `{PROJECT}-android-reviews-past-6-months.csv`
- `{PROJECT}-android-reviews-past-6-months.json`
- `summary-play.json`

CSV は Excel で開けるように UTF-8 BOM 付きです。

## 取得できる範囲

App Store は customer reviews RSS です。並び順ごとに最大 10 ページ、1 ページ 50 件です。開発者の返信は含まれません。

Google Play はストアサイトと同じ公開エンドポイントです。レビューは世界共通で、`gl=jp` はストアフロントの指定であり、投稿者の国ではありません。タイトルはなく、返信がある場合だけ本文と日時を含めます。

どちらも日本のストアフロント（`jp` / `ja`）で、更新日が直近 6 ヶ月より古いレビューは捨てます。
