#!/usr/bin/env python3
"""金価格と為替データを取得して、静的サイト(public/)を生成する1ファイル版。標準ライブラリのみ使用。

このファイルだけで動きます(記事・デザイン・初期設定は、下の FILES に入っています)。

置き場所の例(リポジトリの一番上の階層):
    build.py                          このファイル
    .github/workflows/deploy.yml      毎日の自動更新の設定
    config.json                       (任意)公開URL・運営者名・広告URLなどの設定。FILESの初期設定を上書きします
    guides/記事名.html                (任意)記事を足したいときだけ。同じ名前なら、中に入っている記事を置き換えます

手元で試す:
    python build.py
    FX_FIXTURE=テスト用データ.json python build.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape as esc
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "public"
# ----------------------------------------------------------------------
# 中に入っているファイル(記事、デザイン、初期設定)
# ----------------------------------------------------------------------
FILES = {
    "config.json": r'''{
  "site_name": "金価格ノート",
  "tagline": "金の価格を円で毎営業日更新。買い方、税金、価格が動く理由をやさしく解説",
  "base_url": "https://YOUR-NAME.github.io/YOUR-REPO",
  "owner_name": "",
  "contact": "",
  "adsense_client": "",
  "ga_measurement_id": "",
  "pairs": [
    {
      "slug": "usd-jpy",
      "base": "USD",
      "symbol": "JPY",
      "name": "米ドル円",
      "label": "USD/JPY",
      "unit": "1米ドル",
      "blurb": "米ドル円は、1米ドルが何円かを示す、世界で最も取引される為替レートの一つです。金の国際価格はドルで示されるため、円で見た金価格は、このレートの影響を受けます。"
    }
  ],
  "affiliates": {
    "gold": [
      { "name": "田中貴金属工業", "url": "", "text": "純金積立や金地金の取り扱いは、公式サイトで確認できます。" },
      { "name": "三菱マテリアル", "url": "", "text": "純金積立や金地金の取り扱いは、公式サイトで確認できます。" }
    ],
    "securities": [
      { "name": "SBI証券", "url": "", "text": "金ETFや投資信託の取り扱いは、公式サイトで確認できます。" },
      { "name": "楽天証券", "url": "", "text": "金ETFや投資信託の取り扱いは、公式サイトで確認できます。" },
      { "name": "マネックス証券", "url": "", "text": "金ETFや投資信託の取り扱いは、公式サイトで確認できます。" }
    ],
    "fx": []
  }
}
''',
    "content/guides/kin-kakaku-keisan.html": r'''<!-- title: 円建ての金価格を計算する。1グラムあたりの出し方 | desc: 金の国際価格(ドル/オンス)とドル円から、1グラムあたりの円の価格を計算する方法と、数字を入れて試せる計算機です。 | order: 3 -->
<p class="lede">金の国際価格はドル/オンスで示されます。日本で使う円/グラムに直す計算は、3つの数字だけで済みます。</p>

<h2>計算式</h2>
<p class="callout">円/グラム = 国際価格(ドル/オンス) × ドル円 ÷ 31.1035</p>
<p>31.1035は、1トロイオンスのグラム数です。たとえば、{{GOLD_DATE}}時点の国際価格{{GOLD_USD}}ドル、ドル円{{USDJPY}}円で計算すると、1グラムあたり約{{GOLD_JPY_G}}円になります。</p>

<h2>計算機</h2>
<p class="fine">初期値は、このサイトが記録した最新の数字です。自由に書き換えてください。</p>
<div class="sim">
  <div class="fields">
    <label for="c-usd">国際価格(ドル/オンス)<input id="c-usd" type="number" inputmode="decimal" step="0.01" value="{{GOLD_USD_RAW}}"></label>
    <label for="c-fx">ドル円(円)<input id="c-fx" type="number" inputmode="decimal" step="0.01" value="{{USDJPY_RAW}}"></label>
    <label for="c-g">重さ(グラム)<input id="c-g" type="number" inputmode="decimal" step="0.1" value="10"></label>
  </div>
  <div class="res" aria-live="polite">
    <span>1グラムあたり(目安)</span>
    <b id="c-per">-</b>
    <span id="c-total"></span>
  </div>
</div>

<h2>実際の価格とのちがい</h2>
<ul>
<li>貴金属会社の店頭や公式サイトに出ている販売価格には、手数料や諸経費が上乗せされています。</li>
<li>買取価格は、販売価格より低く設定されるのが一般的です。</li>
<li>このサイトの計算結果は、国際価格をもとにした目安で、実際に売買できる価格ではありません。</li>
</ul>
<p>価格が動く理由は、<a href="{{REL}}guides/kin-kakaku-ugoku-riyu.html">金価格が動く理由</a>で解説しています。</p>

<script>
(function () {
  var $ = function (id) { return document.getElementById(id); };
  function update() {
    var usd = parseFloat($('c-usd').value), fx = parseFloat($('c-fx').value), g = parseFloat($('c-g').value);
    if (!(usd > 0) || !(fx > 0)) { $('c-per').textContent = '-'; $('c-total').textContent = ''; return; }
    var per = usd * fx / 31.1034768;
    $('c-per').textContent = Math.round(per).toLocaleString('ja-JP') + '円';
    $('c-total').textContent = g > 0 ? g.toLocaleString('ja-JP') + 'グラムで、約' + Math.round(per * g).toLocaleString('ja-JP') + '円' : '';
  }
  ['c-usd', 'c-fx', 'c-g'].forEach(function (id) { $(id).addEventListener('input', update); });
  update();
})();
</script>
''',
    "content/guides/kin-kakaku-ugoku-riyu.html": r'''<!-- title: 金価格が動く理由。金利・ドル・世界情勢との関係 | desc: 金の価格が動く主な要因を、金利、ドルの強さ、世界情勢、為替に分けて整理します。 | order: 2 -->
<p class="lede">金の価格は、いくつかの要因が重なって動きます。ニュースでよく聞く理由を、順番に整理します。</p>

<h2>ドルで決まる国際価格</h2>
<p>金は世界で、1トロイオンス(約31.1グラム)あたりのドルで値決めされます。国際価格の目安は、{{GOLD_DATE}}時点で{{GOLD_USD}}ドルです。日本で見る金価格は、この国際価格に為替をかけて、円に直したものがもとになります。</p>

<h2>価格を動かすと言われる要因</h2>
<ul>
<li><b>金利。</b>金は利息を生みません。金利が上がると、利息がつく資産のほうが魅力的に見えるため、金には向かい風になりやすいと言われます。</li>
<li><b>ドルの強さ。</b>ドルが強くなると、ドルで値決めされる金は、ほかの通貨を使う人にとって割高になり、需要が弱まりやすいと言われます。</li>
<li><b>世界情勢への不安。</b>戦争や金融不安が起きると、安全な資産と考えられている金が買われることがあります。</li>
<li><b>各国の中央銀行の購入。</b>外貨の準備として、金を買い増す国があります。</li>
<li><b>宝飾品や工業用の需要。</b>実際に使われる量も、価格に影響します。</li>
</ul>
<p class="callout">要因は同時に動き、値動きのあとから理由が説明されることが多くあります。短い期間の値動きを当てるのは難しいため、1日の上下で判断しないことが大切です。</p>

<h2>円で見ると、為替の影響も受ける</h2>
<p>日本で買う金は円建てなので、ドル建ての国際価格が変わらなくても、円安になれば円の価格は上がり、円高になれば下がります。現在のドル円は{{USDJPY}}円です。</p>
<ul>
<li><a href="{{REL}}fx/usd-jpy.html">ドル円の推移</a></li>
<li><a href="{{REL}}price.html">円建ての金価格の推移</a></li>
<li><a href="{{REL}}guides/kin-kakaku-keisan.html">円建ての金価格を、自分で計算してみる</a></li>
</ul>
''',
    "content/guides/kin-no-kaikata.html": r'''<!-- title: 金の買い方4つを比べる。現物・純金積立・ETF・投資信託 | desc: 金の買い方を、現物、純金積立、金ETF、金価格に連動する投資信託の4つに分けて、特徴と注意点を比べます。 | order: 1 -->
<p class="lede">金の買い方はいくつかあり、必要な金額、手間、費用、売るときの扱いが違います。最初に全体を比べてから、自分に合う方法を選びます。</p>

<h2>4つの買い方の比較</h2>
<div class="scroll"><table>
<thead><tr><th>買い方</th><th>特徴</th><th>気をつける点</th></tr></thead>
<tbody>
<tr><td>現物(地金・コイン)</td><td>手元に実物を持てます。まとまった金額で買うことが多いです。</td><td>買う値段と売る値段に差があります。保管の手間や費用もかかります。</td></tr>
<tr><td>純金積立</td><td>毎月決まった金額で、少しずつ買えます。</td><td>手数料や、現物で引き出すときの費用は、会社によって違います。</td></tr>
<tr><td>金ETF</td><td>証券口座で、株と同じように売買できます。</td><td>売買の手数料と、保有している間のコストがかかります。</td></tr>
<tr><td>金価格に連動する投資信託</td><td>少額から積立で買える商品があります。</td><td>信託報酬がかかります。為替の影響を受ける商品もあります。</td></tr>
</tbody></table></div>

<h2>選ぶときに見る点</h2>
<ul>
<li><b>最初の金額。</b>毎月いくらまで続けられるかを、先に決めます。</li>
<li><b>費用。</b>買うとき、売るとき、持っている間の3つで、いくらかかるかを確かめます。</li>
<li><b>売るときの手間。</b>売れるまでの日数と、売るときの手続きを確認します。</li>
<li><b>税金。</b>商品によって扱いが違います。<a href="{{REL}}guides/kin-zeikin.html">金を売ったときの税金</a>も読んでおくと安心です。</li>
</ul>

<p class="callout warn">金は利息や配当を生まず、価格は上下します。買ったときより値段が下がり、損をすることがあります。</p>

<p>いまの金価格の目安は、<a href="{{REL}}price.html">金価格の推移</a>で確認できます。</p>

{{AFF:gold}}
{{AFF:securities}}

<p class="fine">この記事は情報提供を目的としており、特定の会社や商品の購入をすすめるものではありません。費用や条件は変わることがあるため、申し込む前に公式サイトで最新の内容を確認してください。</p>
''',
    "content/guides/kin-zeikin.html": r'''<!-- title: 金を売ったときの税金。現物の売却益の扱い | desc: 金の現物を売って利益が出たときの税金の基本を、譲渡所得、50万円の特別控除、5年超の扱いに分けて整理します。 | order: 4 -->
<p class="lede">金を売って利益が出たときは、税金がかかることがあります。ここでは、金地金やコインなど現物の基本的な扱いを整理します。</p>

<h2>現物の売却益の基本</h2>
<ul>
<li>金地金やコインを売って出た利益は、譲渡所得として、所得税の対象になります。給料などほかの所得と合算して税額を計算します。</li>
<li>譲渡所得には、年間で最大50万円の特別控除があります。</li>
<li>買ってから売るまでの期間が5年を超える場合は、控除した後の金額の2分の1が課税の対象になります。5年以内は、控除した後の金額の全額が対象です。</li>
</ul>

<h2>準備しておきたいこと</h2>
<ul>
<li><b>購入時の記録を残す。</b>領収書や取引の明細を保管して、いくらで買ったかが分かるようにします。</li>
<li><b>売るときの報告。</b>一度に売る金額が200万円を超えると、買い取る業者が、税務署に報告する書類を出す仕組みがあります。</li>
<li><b>申告が必要か確認する。</b>確定申告が必要かどうかは、1年間の所得の状況で決まります。国税庁の案内や、税務署で確認します。</li>
</ul>

<h2>ETFや投資信託の場合</h2>
<p>金ETFや、金価格に連動する投資信託は、商品の種類によって税金の扱いが違うことがあります。購入先の説明と、国税庁の案内で確認してください。</p>

<p class="callout warn">税制は改正されることがあります。最新の内容は国税庁で確認し、個別の判断は税務署や税理士に相談してください。</p>

<p>買い方ごとの違いは、<a href="{{REL}}guides/kin-no-kaikata.html">金の買い方4つを比べる</a>で整理しています。</p>
''',
    "content/pages/about.html": r'''<div class="prose">
<table>
<tbody>
<tr><td>サイト名</td><td>{{SITE}}</td></tr>
<tr><td>運営者</td><td>{{OWNER}}</td></tr>
<tr><td>連絡先</td><td>{{CONTACT}}</td></tr>
</tbody></table>

<h2>このサイトについて</h2>
<p>金の価格を円建てで毎営業日記録し、金の買い方や税金、価格が動く理由を整理するサイトです。金の国際価格は gold-api.com から、ドル円は公的機関が公表する参考レートをオープンな為替データの配信サービス(Frankfurter)から取得しています。</p>
<p>金価格の履歴は、このサイトが毎営業日に記録した数字です。公開した日から日々たまっていきます。</p>

<h2>運営の方針</h2>
<ul>
<li>制度の数字や名称は、公式の情報で確かめて書きます。</li>
<li>特定の商品や会社の購入を、強くすすめることはしません。</li>
<li>広告を含むページには、その旨を表示します。</li>
</ul>
<p>誤りに気づいた場合は、上記の連絡先までお知らせください。</p>
</div>
''',
    "content/pages/disclaimer.html": r'''<div class="prose">
<h2>広告について</h2>
<p>当サイトは、アフィリエイトプログラムなどの広告を含みます。記事内のリンクから口座開設や商品の申し込みがあった場合、運営者が事業者から報酬を受け取ることがあります。広告を含む箇所には「PR」と表示します。報酬の有無によって、記事の内容を変えることはしません。</p>

<h2>投資に関する免責事項</h2>
<ul>
<li>当サイトの情報は、一般的な情報提供を目的としており、投資の勧誘や助言ではありません。</li>
<li>金の価格は上下し、買ったときより値下がりして、損失が出ることがあります。最終的な判断は、ご自身の責任で行ってください。</li>
<li>税金や制度の内容は改正されることがあります。申し込む前に、公式の情報で最新の内容を確認してください。</li>
</ul>

<h2>金価格・為替レートについて</h2>
<p>当サイトに表示する金価格は、金の国際価格とドル円から計算した目安です。国内の貴金属会社や店頭の販売価格・買取価格とは異なります。為替レートは、公的機関が公表する参考レートで、実際に取引するレートとは異なります。取引の判断には、取引先が示す価格を使ってください。</p>
<p>データの遅れや誤りによって生じた損害について、当サイトは責任を負いません。</p>

<h2>リンク先について</h2>
<p>当サイトからリンクした外部サイトの内容については、責任を負いません。</p>
</div>
''',
    "content/pages/privacy.html": r'''<div class="prose">
<h2>個人情報の取り扱い</h2>
<p>{{SITE}}(以下「当サイト」)は、お問い合わせの際にいただいたお名前やメールアドレスなどを、お返事や確認の目的にのみ使います。法令に基づく場合を除き、本人の同意なく第三者に提供することはありません。</p>

<h2>アクセス解析について</h2>
<p>当サイトでは、利用状況を把握するために、アクセス解析ツール(Google アナリティクスなど)を使うことがあります。これらのツールは、Cookie(クッキー)を使ってデータを集めます。集めるデータは匿名で、個人を特定するものではありません。ブラウザの設定でCookieを無効にすると、データの収集を拒否できます。</p>

<h2>広告について</h2>
<p>当サイトでは、第三者が配信する広告(Google AdSenseなど)や、アフィリエイトプログラムによる広告を掲載することがあります。広告の配信事業者は、利用者の興味に応じた広告を表示するために、Cookieを使うことがあります。Googleの広告でのCookieの扱いは、Googleのポリシーと規約のページで確認できます。パーソナライズ広告は、Googleの広告設定のページから無効にできます。</p>

<h2>外部サービスの利用</h2>
<p>当サイトは、文字の表示にGoogle Fontsを使っています。ページを開くと、利用者のブラウザからGoogleのサーバーへ接続が行われます。</p>

<h2>免責事項と著作権</h2>
<p>免責事項は、<a href="disclaimer.html">免責事項・広告表記</a>のページに記載しています。当サイトの文章や画像の著作権は運営者にあり、無断での転載はご遠慮ください。</p>

<h2>改定について</h2>
<p>この方針は、必要に応じて予告なく改定することがあります。</p>
</div>
''',
    "static/style.css": r'''/* Layout: 1 column reading site, max 760px. Header / content / footer. */
:root {
  --bg: #F4F6F8;
  --surface: #FFFFFF;
  --ink: #15222C;
  --muted: #566772;
  --line: #D9E0E5;
  --accent: #0E7490;
  --accent-soft: #DDF0F4;
  --on-accent: #FFFFFF;
  --warn: #8A4B06;
  --warn-soft: #FBEBD3;
  --font: "Zen Kaku Gothic New", "Hiragino Sans", "Yu Gothic", "Noto Sans JP", sans-serif;
  --mono: "DM Mono", ui-monospace, "SF Mono", Menlo, monospace;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0F171D; --surface: #172229; --ink: #E6EEF3; --muted: #9AACB8; --line: #2A3841;
    --accent: #4CC3DC; --accent-soft: #153640; --on-accent: #06222B; --warn: #EBB062; --warn-soft: #3A2A12;
    color-scheme: dark;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font); font-size: 16px; line-height: 1.85; }
a { color: var(--accent); text-underline-offset: 3px; }
a:focus-visible, button:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
.inner { max-width: 760px; margin-inline: auto; padding-inline: 16px; }
main.inner { padding-block: 24px 48px; display: flex; flex-direction: column; gap: 18px; min-width: 0; }
h1 { font-size: clamp(24px, 6vw, 32px); line-height: 1.4; font-weight: 900; margin: 0; text-wrap: balance; }
h2 { font-size: 20px; line-height: 1.5; font-weight: 700; margin: 12px 0 0; text-wrap: balance; }
h3 { font-size: 17px; line-height: 1.5; font-weight: 700; margin: 8px 0 0; }
p { margin: 0; }
.num { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.fine { font-size: 13px; color: var(--muted); line-height: 1.7; }
.stamp { font-size: 13.5px; color: var(--muted); }

.top { background: var(--surface); border-bottom: 1px solid var(--line); }
.top .inner { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-block: 12px; }
.brand { font-weight: 900; font-size: 17px; color: var(--ink); text-decoration: none; }
.top nav { display: flex; gap: 16px; font-size: 14px; }
.top nav a { color: var(--muted); text-decoration: none; }
.top nav a:hover { color: var(--accent); }
.crumb { font-size: 13px; color: var(--muted); }

.hero { display: flex; flex-direction: column; gap: 8px; padding-block: 8px 4px; }
.hero p { color: var(--muted); }

/* rate list */
ul.rates, ul.cards, ul.links { list-style: none; margin: 0; padding: 0; }
ul.rates { display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); overflow: hidden; }
ul.rates li + li { border-top: 1px solid var(--line); }
ul.rates a { display: grid; grid-template-columns: 1fr 110px auto; align-items: center; gap: 12px; padding: 14px 16px; color: inherit; text-decoration: none; }
ul.rates a:hover { background: var(--accent-soft); }
.nm { display: flex; flex-direction: column; line-height: 1.4; min-width: 0; }
.nm small { color: var(--muted); font-family: var(--mono); font-size: 12px; }
.rt { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.4; }
.rt .v { font-size: 20px; font-weight: 500; }
.delta { font-size: 13px; }
.delta.up { color: var(--accent); }
.delta.down { color: var(--warn); }
.delta.flat { color: var(--muted); }
.spark { width: 110px; height: 34px; }
.spark polyline { fill: none; stroke: var(--accent); stroke-width: 1.8; stroke-linejoin: round; stroke-linecap: round; }

/* pair page */
.now { display: flex; flex-direction: column; gap: 2px; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 16px; }
.big { font-size: clamp(36px, 11vw, 52px); line-height: 1.2; font-weight: 500; color: var(--accent); }
.big small { font-size: 18px; margin-left: 4px; color: var(--muted); }
.chart { width: 100%; height: auto; display: block; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; }
.chart text { font-family: var(--mono); font-size: 11.5px; fill: var(--muted); }
.chart .grid { stroke: var(--line); stroke-width: 1; }
.chart .area { fill: var(--accent); fill-opacity: .14; }
.chart .line { fill: none; stroke: var(--accent); stroke-width: 2.4; stroke-linejoin: round; }
.chart .dot { fill: var(--accent); }
.chart .end { fill: var(--ink); font-weight: 500; font-size: 12.5px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14.5px; background: var(--surface); border: 1px solid var(--line); }
th, td { padding: 9px 12px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; white-space: normal; }
th { font-weight: 500; color: var(--muted); font-size: 13px; background: var(--bg); }
td { font-family: var(--mono); font-variant-numeric: tabular-nums; }
td:first-child { font-family: var(--font); }
td small { color: var(--muted); margin-left: 4px; font-size: 11.5px; }

/* cards / links */
ul.cards { display: flex; flex-direction: column; gap: 10px; }
ul.cards a { display: flex; flex-direction: column; gap: 2px; padding: 14px 16px; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; color: inherit; text-decoration: none; }
ul.cards a:hover { border-color: var(--accent); }
ul.cards b { color: var(--accent); line-height: 1.5; }
ul.cards span { font-size: 14px; color: var(--muted); line-height: 1.7; }
ul.links { display: flex; flex-wrap: wrap; gap: 6px 18px; }

/* article */
.prose { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.prose ul, .prose ol { margin: 0; padding-left: 1.4em; display: flex; flex-direction: column; gap: 6px; }
.prose .lede { color: var(--muted); }
.prose td, .prose th { white-space: normal; text-align: left; font-family: var(--font); }
.prose td:first-child { font-weight: 700; }
.callout { background: var(--accent-soft); border-radius: 10px; padding: 12px 14px; font-size: 14.5px; }
.callout.warn { background: var(--warn-soft); color: var(--warn); }

/* affiliate */
.aff { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.aff ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.aff li { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px 12px; }
.aff li > div { flex: 1 1 220px; min-width: 0; }
.aff li p { font-size: 13.5px; color: var(--muted); line-height: 1.7; }
.pr { font-size: 12px; font-weight: 700; color: var(--warn); letter-spacing: .04em; }
.btn { display: inline-block; background: var(--accent); color: var(--on-accent); padding: 8px 16px; border-radius: 8px; font-weight: 700; font-size: 14px; text-decoration: none; }
.btn:hover { filter: brightness(1.08); }

/* simulator widget */
.sim { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.sim .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.sim label { font-size: 13px; color: var(--muted); display: flex; flex-direction: column; gap: 4px; }
.sim input { width: 100%; font-family: var(--mono); font-size: 16px; padding: 9px 10px; background: var(--bg); color: var(--ink); border: 1px solid var(--line); border-radius: 8px; }
.sim .res { font-size: 14px; color: var(--muted); }
.sim .res b { display: block; font-family: var(--mono); font-weight: 500; font-size: clamp(28px, 8vw, 38px); color: var(--accent); line-height: 1.3; }

.foot { border-top: 1px solid var(--line); background: var(--surface); padding-block: 22px; margin-top: 12px; }
.foot .inner { display: flex; flex-direction: column; gap: 10px; }
.foot nav { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 14px; }

@media (max-width: 440px) {
  ul.rates a { grid-template-columns: 1fr auto; }
  ul.rates .spark { display: none; }
}
''',
}

SRC = ROOT / "_src"


def _materialize() -> None:
    if SRC.exists():
        shutil.rmtree(SRC)
    for rel, text in FILES.items():
        p = SRC / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


_materialize()
CFG = json.loads((SRC / "config.json").read_text(encoding="utf-8"))
if (ROOT / "config.json").exists():
    CFG.update(json.loads((ROOT / "config.json").read_text(encoding="utf-8")))
API = "https://api.frankfurter.dev/v1"
CACHE = ROOT / "data" / "fx_cache.json"
JST = timezone(timedelta(hours=9))
SITE = CFG["site_name"]
BASE = CFG["base_url"].rstrip("/")


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# --------------------------------------------------------------------------
# データ取得
# --------------------------------------------------------------------------
def http_json(url: str, tries: int = 3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fx-site-builder/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def fetch_pair(p: dict) -> dict:
    end = date.today()

    def one(days: int) -> dict:
        start = end - timedelta(days=days)
        d = http_json(f"{API}/{start}..{end}?base={p['base']}&symbols={p['symbol']}")
        return {k: float(v[p["symbol"]]) for k, v in d["rates"].items()}

    # daily: 直近の日次データ / long: 1年分(APIの都合で日次でない場合がある)
    return {"daily": one(100), "long": one(400)}


def load_data() -> dict:
    fixture = os.environ.get("FX_FIXTURE")
    if fixture:
        raw = json.loads(Path(fixture).read_text(encoding="utf-8"))
    else:
        cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
        raw = {}
        for p in CFG["pairs"]:
            try:
                raw[p["slug"]] = fetch_pair(p)
            except Exception as e:  # noqa: BLE001
                log(f"[warn] {p['label']} の取得に失敗: {e}")
                if p["slug"] in cache:
                    raw[p["slug"]] = cache[p["slug"]]
                    log(f"[warn] {p['label']} は前回のデータを使います")
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(raw), encoding="utf-8")

    data = {}
    for p in CFG["pairs"]:
        r = raw.get(p["slug"])
        if not r:
            log(f"[warn] {p['label']} のデータがないため、ページを作りません")
            continue
        daily = sorted(r["daily"].items())
        long_ = sorted(r["long"].items())
        if len(daily) < 5:
            log(f"[warn] {p['label']} のデータが少なすぎるため、ページを作りません")
            continue
        data[p["slug"]] = {"daily": daily, "long": long_ or daily}
    if not data:
        sys.exit("為替データを1件も取得できませんでした。公開済みのサイトを壊さないため、ここで終了します。")
    return data


# --------------------------------------------------------------------------
# 表示用の整形
# --------------------------------------------------------------------------
def jp_date(s: str) -> str:
    d = date.fromisoformat(s)
    return f"{d.year}年{d.month}月{d.day}日"


def short_date(s: str, with_year: bool = False) -> str:
    d = date.fromisoformat(s)
    return f"{str(d.year)[2:]}/{d.month}" if with_year else f"{d.month}/{d.day}"


def rate(v: float) -> str:
    return f"{v:,.2f}"


def signed(v: float, digits: int = 2) -> str:
    return f"{v:+,.{digits}f}"


def change(daily: list) -> tuple[float, float]:
    (_, v1), (_, v0) = daily[-1], daily[-2]
    return v1 - v0, (v1 - v0) / v0 * 100


def arrow(diff: float) -> tuple[str, str]:
    if diff > 0:
        return "▲", "up"
    if diff < 0:
        return "▼", "down"
    return "―", "flat"


def last_n_days(points: list, days: int) -> list:
    end = date.fromisoformat(points[-1][0])
    cut = (end - timedelta(days=days)).isoformat()
    return [p for p in points if p[0] >= cut]


def stats(points: list) -> dict:
    hi = max(points, key=lambda x: x[1])
    lo = min(points, key=lambda x: x[1])
    avg = sum(v for _, v in points) / len(points)
    return {"hi": hi, "lo": lo, "avg": avg}


# --------------------------------------------------------------------------
# SVG(グラフ)
# --------------------------------------------------------------------------
def chart_svg(points: list, label: str, with_year: bool = False, dec: int = 1, end_dec: int = 2, unit: str = "円") -> str:
    w, h = 640, 260
    ml, mr, mt, mb = 52, 14, 16, 30
    vals = [v for _, v in points]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.12 or hi * 0.01
    lo, hi = lo - pad, hi + pad
    n = len(points)

    def X(i: int) -> float:
        return ml + (w - ml - mr) * (i / (n - 1))

    def Y(v: float) -> float:
        return h - mb - (h - mt - mb) * ((v - lo) / (hi - lo))

    parts = []
    for k in range(4):
        v = lo + (hi - lo) * k / 3
        y = Y(v)
        parts.append(f'<line class="grid" x1="{ml}" x2="{w - mr}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text x="{ml - 6}" y="{y + 4:.1f}" text-anchor="end">{v:,.{dec}f}</text>')
    marks = [(0, "start"), (n // 2, "middle"), (n - 1, "end")]
    for i, anchor in marks:
        parts.append(
            f'<text x="{X(i):.1f}" y="{h - 8}" text-anchor="{anchor}">{short_date(points[i][0], with_year)}</text>'
        )
    line = "".join(("L" if i else "M") + f"{X(i):.1f} {Y(v):.1f}" for i, (_, v) in enumerate(points))
    area = f"{line}L{X(n - 1):.1f} {h - mb}L{X(0):.1f} {h - mb}Z"
    parts.append(f'<path class="area" d="{area}"/>')
    parts.append(f'<path class="line" d="{line}"/>')
    lx, ly = X(n - 1), Y(points[-1][1])
    parts.append(f'<circle class="dot" cx="{lx:.1f}" cy="{ly:.1f}" r="4"/>')
    parts.append(f'<text class="end" x="{lx - 8:.1f}" y="{ly - 10:.1f}" text-anchor="end">{points[-1][1]:,.{end_dec}f}</text>')
    aria = f"{label}の推移。{jp_date(points[0][0])}から{jp_date(points[-1][0])}まで。最新は{points[-1][1]:,.{end_dec}f}{unit}"
    return f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(aria)}">{"".join(parts)}</svg>'


def spark_svg(points: list) -> str:
    w, h = 110, 34
    vals = [v for _, v in points]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(points)
    pts = " ".join(
        f"{(w - 4) * i / (n - 1) + 2:.1f},{h - 4 - (h - 8) * (v - lo) / span:.1f}" for i, (_, v) in enumerate(points)
    )
    return f'<svg class="spark" viewBox="0 0 {w} {h}" aria-hidden="true"><polyline points="{pts}"/></svg>'


# --------------------------------------------------------------------------
# アフィリエイト枠(URLが空の項目は表示しない)
# --------------------------------------------------------------------------
def aff_box(group: str) -> str:
    items = [a for a in CFG.get("affiliates", {}).get(group, []) if a.get("url")]
    if not items:
        return ""
    rows = "".join(
        f'<li><div><b>{esc(a["name"])}</b><p>{esc(a.get("text", ""))}</p></div>'
        f'<a class="btn" href="{esc(a["url"])}" target="_blank" rel="sponsored nofollow noopener">公式サイトを見る</a></li>'
        for a in items
    )
    return (
        '<aside class="aff"><p class="pr">PR 広告を含みます</p>'
        f"<ul>{rows}</ul>"
        '<p class="fine">条件やキャンペーンは変わることがあります。申し込む前に、必ず公式サイトで最新の内容を確認してください。</p></aside>'
    )


def render_tokens(text: str, rel: str) -> str:
    text = text.replace("{{REL}}", rel).replace("{{SITE}}", esc(SITE))
    for k, v in GOLD.items():
        text = text.replace(k, v)
    text = text.replace("{{OWNER}}", esc(CFG.get("owner_name") or "(運営者名を config.json に設定してください)"))
    text = text.replace("{{CONTACT}}", esc(CFG.get("contact") or "(連絡先を config.json に設定してください)"))
    text = re.sub(r"\{\{AFF:(\w+)\}\}", lambda m: aff_box(m.group(1)), text)
    return text


# --------------------------------------------------------------------------
# ページ共通
# --------------------------------------------------------------------------
def head_scripts() -> str:
    s = ""
    ads = CFG.get("adsense_client")
    if ads:
        s += (
            '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
            f'{esc(ads)}" crossorigin="anonymous"></script>\n'
        )
    ga = CFG.get("ga_measurement_id")
    if ga:
        s += (
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={esc(ga)}"></script>\n'
            "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}"
            f"gtag('js',new Date());gtag('config','{esc(ga)}');</script>\n"
        )
    return s


def page(*, title: str, desc: str, body: str, rel: str, path: str) -> str:
    canon = f"{BASE}/{path}" if path else f"{BASE}/"
    full_title = f"{title}|{SITE}" if path else title
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canon)}">
<meta property="og:title" content="{esc(full_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(canon)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Zen+Kaku+Gothic+New:wght@400;500;700;900&display=swap">
<link rel="stylesheet" href="{rel}static/style.css">
{head_scripts()}</head>
<body>
<header class="top"><div class="inner">
<a class="brand" href="{rel}index.html">{esc(SITE)}</a>
<nav aria-label="メインメニュー"><a href="{rel}price.html">金価格</a><a href="{rel}fx/usd-jpy.html">ドル円</a><a href="{rel}guides/index.html">ガイド</a></nav>
</div></header>
<main class="inner">
{body}
</main>
<footer class="foot"><div class="inner">
<nav aria-label="フッターメニュー"><a href="{rel}about.html">運営者情報</a><a href="{rel}privacy.html">プライバシーポリシー</a><a href="{rel}disclaimer.html">免責事項・広告表記</a></nav>
<p class="fine">掲載内容は情報提供を目的としたもので、投資の勧誘や助言ではありません。投資は元本が保証されず、損失が出ることがあります。最終的な判断はご自身で行ってください。</p>
<p class="fine">© {datetime.now(JST).year} {esc(SITE)}</p>
</div></footer>
</body>
</html>
"""


def write(path: str, html: str) -> None:
    f = OUT / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(html, encoding="utf-8")


# --------------------------------------------------------------------------
# 各ページ
# --------------------------------------------------------------------------
def summary_text(p: dict, daily: list) -> str:
    d1, v1 = daily[-1]
    _, v0 = daily[-2]
    diff, pct = change(daily)
    if diff > 0:
        move = f"前営業日の{rate(v0)}円から{signed(diff)}円({signed(pct)}%)上昇し、円安方向に動きました"
    elif diff < 0:
        move = f"前営業日の{rate(v0)}円から{signed(diff)}円({signed(pct)}%)下落し、円高方向に動きました"
    else:
        move = f"前営業日の{rate(v0)}円から変わりませんでした"
    return f"{jp_date(d1)}時点の{p['name']}({p['label']})は、{p['unit']}={rate(v1)}円です。{move}。"


def build_pair_page(p: dict, d: dict, all_pairs: list) -> None:
    daily, long_ = d["daily"], d["long"]
    d1, v1 = daily[-1]
    diff, pct = change(daily)
    ar, cls = arrow(diff)
    three = last_n_days(daily, 92)
    s3 = stats(three)
    s1 = stats(long_)
    rows = "".join(
        f"<tr><td>{jp_date(day)}</td><td>{rate(v)}</td></tr>" for day, v in reversed(daily[-10:])
    )
    others = "".join(
        f'<li><a href="{q["slug"]}.html">{esc(q["name"])}({q["label"]})</a></li>' for q in all_pairs if q["slug"] != p["slug"]
    )
    body = f"""
<nav class="crumb" aria-label="パンくず"><a href="../index.html">ホーム</a> / 為替 / {esc(p["name"])}</nav>
<h1>{esc(p["name"])}({p["label"]})の今日のレートと推移</h1>
<p class="stamp">{jp_date(d1)}時点の参考レート</p>
<section class="now">
<div class="big num">{rate(v1)}<small>円</small></div>
<p class="delta {cls}"><span aria-hidden="true">{ar}</span> 前営業日比 <span class="num">{signed(diff)}円({signed(pct)}%)</span></p>
</section>
<p>{esc(summary_text(p, daily))}</p>
<h2>直近3か月の推移</h2>
{chart_svg(three, p["name"] + "の直近3か月")}
<h2>過去1年の推移</h2>
{chart_svg(long_, p["name"] + "の過去1年", with_year=True)}
<h2>高値・安値・平均</h2>
<div class="scroll"><table>
<thead><tr><th></th><th>高値</th><th>安値</th><th>平均</th></tr></thead>
<tbody>
<tr><td>直近3か月</td><td>{rate(s3["hi"][1])}<small>({short_date(s3["hi"][0])})</small></td><td>{rate(s3["lo"][1])}<small>({short_date(s3["lo"][0])})</small></td><td>{rate(s3["avg"])}</td></tr>
<tr><td>過去1年</td><td>{rate(s1["hi"][1])}<small>({short_date(s1["hi"][0], True)})</small></td><td>{rate(s1["lo"][1])}<small>({short_date(s1["lo"][0], True)})</small></td><td>{rate(s1["avg"])}</td></tr>
</tbody></table></div>
<h2>直近10営業日のレート</h2>
<div class="scroll"><table><thead><tr><th>日付</th><th>1通貨あたり(円)</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>{esc(p["name"])}とは</h2>
<p>{esc(p["blurb"])}</p>
<p>円安は、外貨に対して円の価値が下がることで、{esc(p["unit"])}を買うのに必要な円が増えます。円高は、その反対です。金は世界でドル建てで値決めされるため、円安・円高は、円で見た金価格にも影響します。</p>
{aff_box("fx")}
<p class="fine">このレートは、欧州中央銀行などが公表する参考レートです。銀行や証券会社で実際に取引するレートとは異なります。取引の判断には使わず、動きの目安としてご覧ください。</p>
<p>円建ての金価格との関係は、<a href="../guides/kin-kakaku-ugoku-riyu.html">金価格が動く理由</a>で解説しています。</p>
<p><a href="../price.html">金価格の推移を見る</a></p>
"""
    desc = f"{p['name']}({p['label']})の最新レートと、直近3か月・過去1年の推移、高値・安値を毎営業日更新。{jp_date(d1)}時点は{rate(v1)}円です。"
    write(
        f"fx/{p['slug']}.html",
        page(title=f"{p['name']}({p['label']})の今日のレートと推移", desc=desc, body=body, rel="../", path=f"fx/{p['slug']}.html"),
    )


def load_guides() -> list:
    meta_re = re.compile(r"^<!--\s*title:(.*?)\|\s*desc:(.*?)\|\s*order:\s*(\d+)\s*-->\s*", re.S)
    guides = []
    found = {f.stem: f for f in sorted((SRC / "content" / "guides").glob("*.html"))}
    found.update({f.stem: f for f in sorted((ROOT / "guides").glob("*.html"))})  # 自分で足した記事
    for f in [found[k] for k in sorted(found)]:
        raw = f.read_text(encoding="utf-8")
        m = meta_re.match(raw)
        if not m:
            sys.exit(f"{f.name} の先頭に title / desc / order のコメントがありません")
        guides.append(
            {"slug": f.stem, "title": m.group(1).strip(), "desc": m.group(2).strip(), "order": int(m.group(3)), "body": raw[m.end():]}
        )
    return sorted(guides, key=lambda g: g["order"])


def build_guides(guides: list) -> None:
    for g in guides:
        others = "".join(
            f'<li><a href="{o["slug"]}.html">{esc(o["title"])}</a></li>' for o in guides if o["slug"] != g["slug"]
        )
        body = (
            f'<nav class="crumb" aria-label="パンくず"><a href="../index.html">ホーム</a> / <a href="index.html">ガイド</a></nav>\n'
            f'<article class="prose"><h1>{esc(g["title"])}</h1>\n{render_tokens(g["body"], "../")}\n</article>\n'
            f'<h2>ほかのガイド</h2><ul class="links">{others}</ul>'
        )
        write(
            f"guides/{g['slug']}.html",
            page(title=g["title"], desc=g["desc"], body=body, rel="../", path=f"guides/{g['slug']}.html"),
        )
    items = "".join(
        f'<li><a href="{g["slug"]}.html"><b>{esc(g["title"])}</b><span>{esc(g["desc"])}</span></a></li>' for g in guides
    )
    body = f'<h1>ガイド</h1><p>積立やNISA、為替の基本を、数字や制度の名前を確かめながら整理しています。</p><ul class="cards">{items}</ul>'
    write(
        "guides/index.html",
        page(title="ガイド一覧", desc="NISAの始め方、証券口座の選び方、為替レートの見方、積立シミュレーターのガイド一覧です。", body=body, rel="../", path="guides/index.html"),
    )


GOLD_API = "https://api.gold-api.com/price/XAU"
OZ_G = 31.1034768  # 1トロイオンスのグラム数
GOLD: dict = {}  # 記事の中で使う数値({{GOLD_USD}} など)


def jpy_g(x: dict) -> float:
    return x["usd"] * x["fx"] / OZ_G


def fetch_prev_gold() -> list:
    """前回までの履歴を、公開中のサイトから読み込む。取得に失敗したら、履歴を失わないよう終了する。"""
    if "YOUR-NAME" in BASE:
        log("[warn] base_url が初期値のため、前回までの金価格の履歴は読み込みません")
        return []
    url = f"{BASE}/data/gold.json"
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gold-site-builder/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                items = json.load(r)
            return [x for x in items if all(k in x for k in ("d", "usd", "fx"))]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log("[info] 前回の金価格の履歴はありません(初回の公開)")
                return []
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 * (i + 1))
    sys.exit(f"前回までの金価格の履歴を読み込めませんでした({last})。履歴を失わないため、ここで終了します。")


def fetch_latest_gold():
    try:
        d = http_json(GOLD_API)
        usd = float(d["price"])
        stamp = str(d.get("updatedAt") or "")[:10]
        if not re.match(r"\d{4}-\d{2}-\d{2}$", stamp):
            stamp = datetime.now(timezone.utc).date().isoformat()
        if usd <= 0:
            raise ValueError("価格が0以下です")
        return {"d": stamp, "usd": usd}
    except Exception as e:  # noqa: BLE001
        log(f"[warn] 金価格の取得に失敗: {e}")
        return None


def load_gold(fx_last: tuple) -> list:
    fixture = os.environ.get("GOLD_FIXTURE")
    if fixture:
        raw = json.loads(Path(fixture).read_text(encoding="utf-8"))
        prev, latest = raw.get("prev", []), raw.get("latest")
    else:
        prev, latest = fetch_prev_gold(), fetch_latest_gold()
    hist = {x["d"]: x for x in prev}
    if latest:
        hist[latest["d"]] = {"d": latest["d"], "usd": latest["usd"], "fx": fx_last[1]}
    if not hist:
        sys.exit("金価格を1件も取得できませんでした。公開済みのサイトを壊さないため、ここで終了します。")
    items = [hist[k] for k in sorted(hist)][-1500:]
    x = items[-1]
    GOLD.update(
        {
            "{{GOLD_USD}}": f"{x['usd']:,.2f}",
            "{{GOLD_USD_RAW}}": f"{x['usd']:.2f}",
            "{{USDJPY}}": f"{x['fx']:,.2f}",
            "{{USDJPY_RAW}}": f"{x['fx']:.2f}",
            "{{GOLD_JPY_G}}": f"{jpy_g(x):,.0f}",
            "{{GOLD_DATE}}": jp_date(x["d"]),
        }
    )
    return items


def build_price(items: list) -> None:
    last = items[-1]
    g = jpy_g(last)
    pts_jpy = [(x["d"], jpy_g(x)) for x in items]
    pts_usd = [(x["d"], x["usd"]) for x in items]
    if len(items) >= 2:
        s = stats(pts_jpy)
        charts = (
            "<h2>円建て(1グラムあたり)の推移</h2>"
            + chart_svg(pts_jpy[-120:], "金価格(円/g)", dec=0, end_dec=0, unit="円/g")
            + "<h2>国際価格(ドル/オンス)の推移</h2>"
            + chart_svg(pts_usd[-120:], "金の国際価格(ドル/オンス)", dec=0, end_dec=0, unit="ドル")
            + "<h2>記録した期間の高値・安値</h2>"
            + '<div class="scroll"><table><thead><tr><th></th><th>高値</th><th>安値</th><th>平均</th></tr></thead><tbody>'
            + f'<tr><td>円/g({len(items)}日分)</td><td>{s["hi"][1]:,.0f}<small>({short_date(s["hi"][0], True)})</small></td>'
            + f'<td>{s["lo"][1]:,.0f}<small>({short_date(s["lo"][0], True)})</small></td><td>{s["avg"]:,.0f}</td></tr></tbody></table></div>'
        )
    else:
        charts = '<p class="callout">金価格の履歴は、このサイトを公開した日から、毎営業日1件ずつたまっていきます。グラフは、2日分以上たまると表示されます。</p>'
    rows = "".join(
        f'<tr><td>{jp_date(x["d"])}</td><td>{jpy_g(x):,.0f}</td><td>{x["usd"]:,.2f}</td><td>{x["fx"]:,.2f}</td></tr>'
        for x in reversed(items[-20:])
    )
    body = f"""
<nav class="crumb" aria-label="パンくず"><a href="index.html">ホーム</a> / 金価格</nav>
<h1>金価格の推移(円/g・ドル/オンス)</h1>
<p class="stamp">{jp_date(last["d"])}時点の目安</p>
<section class="now">
<div class="big num">{g:,.0f}<small>円/g</small></div>
<p class="stamp">国際価格 {last["usd"]:,.2f}ドル/オンス × ドル円 {last["fx"]:,.2f}円 ÷ {OZ_G:.4f}グラム</p>
</section>
<p class="callout warn">この価格は、国際価格と為替から計算した目安です。国内の店頭や、貴金属会社が公表する販売価格・買取価格とは異なります。実際に売買するときは、取扱会社の価格を確認してください。</p>
{charts}
<h2>直近の記録</h2>
<div class="scroll"><table><thead><tr><th>日付</th><th>円/g</th><th>ドル/オンス</th><th>ドル円</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>計算のしかた</h2>
<p>金の国際価格は、1トロイオンス(約31.1グラム)あたりのドルで示されます。これにドル円を掛けて、グラム数で割ると、円建ての1グラムあたりの価格が分かります。くわしくは、<a href="guides/kin-kakaku-keisan.html">円建ての金価格を計算する</a>で、自分で数字を入れて試せます。</p>
{aff_box("gold")}
<p class="fine">金の国際価格は gold-api.com、ドル円は欧州中央銀行などが公表する参考レート(Frankfurter)から取得しています。履歴は、このサイトが毎営業日に記録したものです。</p>
"""
    desc = f"金価格を円建て(1グラムあたり)で毎営業日更新。{jp_date(last['d'])}時点の目安は{g:,.0f}円/gです。ドル建ての国際価格との推移も確認できます。"
    write("price.html", page(title="金価格の推移(円/g)", desc=desc, body=body, rel="", path="price.html"))


def build_index(items: list, data: dict, guides: list) -> None:
    last = items[-1]
    g = jpy_g(last)
    delta = ""
    if len(items) >= 2:
        pg = jpy_g(items[-2])
        diff = g - pg
        ar, cls = arrow(diff)
        delta = f'<p class="delta {cls}"><span aria-hidden="true">{ar}</span> 前回の記録比 <span class="num">{signed(diff, 0)}円({signed(diff / pg * 100)}%)</span></p>'
        chart = "<h2>金価格の推移(円/g)</h2>" + chart_svg(
            [(x["d"], jpy_g(x)) for x in items][-90:], "金価格(円/g)", dec=0, end_dec=0, unit="円/g"
        )
    else:
        chart = '<p class="callout">金価格の履歴は、このサイトを公開した日から、毎営業日1件ずつたまっていきます。グラフは、2日分以上たまると表示されます。</p>'
    cards = "".join(
        f'<li><a href="guides/{x["slug"]}.html"><b>{esc(x["title"])}</b><span>{esc(x["desc"])}</span></a></li>' for x in guides
    )
    body = f"""
<section class="hero">
<h1>金の価格を円で、<wbr>毎営業日更新</h1>
<p>{esc(CFG["tagline"])}</p>
</section>
<section class="now">
<p class="stamp">1グラムあたりの金価格(目安)・{jp_date(last["d"])}時点</p>
<div class="big num">{g:,.0f}<small>円/g</small></div>
{delta}
<p class="stamp">国際価格 {last["usd"]:,.2f}ドル/オンス、ドル円 {last["fx"]:,.2f}円</p>
</section>
{chart}
<p class="fine">国際価格と為替から計算した目安です。国内の販売価格・買取価格とは異なります。<a href="price.html">金価格の推移をくわしく見る</a>、<a href="fx/usd-jpy.html">ドル円の推移を見る</a>。</p>
<section>
<h2>金の基本ガイド</h2>
<ul class="cards">{cards}</ul>
</section>
"""
    write("index.html", page(title=f"{SITE} 金価格の推移と、金の買い方ガイド", desc=CFG["tagline"], body=body, rel="", path=""))


def build_pages() -> None:
    pages = {
        "about": ("運営者情報", "このサイトの運営者情報です。"),
        "privacy": ("プライバシーポリシー", "個人情報の取り扱いと、アクセス解析・広告についての方針です。"),
        "disclaimer": ("免責事項・広告表記", "掲載情報の免責事項と、広告(アフィリエイト)についての表記です。"),
    }
    for slug, (title, desc) in pages.items():
        raw = (SRC / "content" / "pages" / f"{slug}.html").read_text(encoding="utf-8")
        body = f'<article class="prose"><h1>{esc(title)}</h1>\n{render_tokens(raw, "")}</article>'
        write(f"{slug}.html", page(title=title, desc=desc, body=body, rel="", path=f"{slug}.html"))


def build_meta(urls: list) -> None:
    today = datetime.now(JST).date().isoformat()
    items = "".join(f"<url><loc>{BASE}/{u}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>\n')
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    write(".nojekyll", "")


def main() -> None:
    if "YOUR-NAME" in CFG["base_url"]:
        log("[warn] config.json の base_url がまだ初期値です。公開後のURLに書き換えてください。")
    if not CFG.get("owner_name") or not CFG.get("contact"):
        log("[warn] config.json の owner_name / contact が空です。運営者情報ページに反映されます。公開前に設定してください。")

    data = load_data()
    if "usd-jpy" not in data:
        sys.exit("ドル円のデータがないため、円建ての金価格を計算できません。")
    items = load_gold(data["usd-jpy"]["daily"][-1])
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(SRC / "static", OUT / "static")

    built = [p for p in CFG["pairs"] if p["slug"] in data]
    for p in built:
        build_pair_page(p, data[p["slug"]], built)
    guides = load_guides()
    build_guides(guides)
    build_index(items, data, guides)
    build_price(items)
    write("data/gold.json", json.dumps(items, ensure_ascii=False))
    build_pages()

    urls = ["", "price.html", "guides/index.html", "about.html", "privacy.html", "disclaimer.html"]
    urls += [f"fx/{p['slug']}.html" for p in built] + [f"guides/{g['slug']}.html" for g in guides]
    build_meta(urls)
    log(f"完了: 金価格{len(items)}日分、為替ページ{len(built)}件、ガイド{len(guides)}件を public/ に出力しました。")


if __name__ == "__main__":
    main()
