"""
Trading News Report — Daily Bias Dashboard
Separate Railway app, does not touch apex-tracker
"""
from flask import Flask, jsonify
from flask_cors import CORS
import os, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

STOOQ_MAP = {
    'MNQ': 'mnq.f',
    'MES': 'mes.f',
    'MGC': 'mgc.f',
    'MCL': 'mcl.f',
    'VIX': '^vix',
    'DXY': 'dx.f',
}

YF_MAP = {
    'MNQ': 'MNQ=F',
    'MES': 'MES=F',
    'MGC': 'MGC=F',
    'MCL': 'MCL=F',
    'VIX': '^VIX',
    'DXY': 'DX-Y.NYB',
}

def fetch_market_data():
    """Fetch prices from Stooq with Yahoo Finance fallback"""
    results = {}

    # Primary: Stooq
    for name, sym in STOOQ_MAP.items():
        try:
            url = f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=json"
            r = requests.get(url, headers=HEADERS, timeout=8)
            q = r.json().get('symbols', [{}])[0]
            price = float(q.get('Close', 0) or 0)
            open_ = float(q.get('Open',  0) or 0)
            high  = float(q.get('High',  0) or 0)
            low   = float(q.get('Low',   0) or 0)
            if price > 0:
                chg     = price - open_ if open_ > 0 else 0
                chg_pct = (chg / open_ * 100) if open_ > 0 else 0
                results[name] = {
                    'price':      round(price, 2),
                    'change':     round(chg, 2),
                    'change_pct': round(chg_pct, 2),
                    'day_high':   round(high, 2),
                    'day_low':    round(low, 2),
                    'open':       round(open_, 2),
                    'source':     'stooq'
                }
        except:
            pass

    # Fallback: Yahoo Finance for anything missing
    missing = [k for k in STOOQ_MAP if results.get(k, {}).get('price', 0) == 0]
    if missing:
        try:
            tickers = ' '.join([YF_MAP[k] for k in missing if k in YF_MAP])
            url = f"https://query2.finance.yahoo.com/v8/finance/quote?symbols={tickers}"
            r = requests.get(url, headers=HEADERS, timeout=8)
            for q in r.json().get('quoteResponse', {}).get('result', []):
                sym = q.get('symbol', '')
                for name, yf_sym in YF_MAP.items():
                    if sym == yf_sym and name in missing:
                        price = q.get('regularMarketPrice', 0)
                        if price:
                            results[name] = {
                                'price':      round(price, 2),
                                'change':     round(q.get('regularMarketChange', 0), 2),
                                'change_pct': round(q.get('regularMarketChangePercent', 0), 2),
                                'day_high':   round(q.get('regularMarketDayHigh', 0), 2),
                                'day_low':    round(q.get('regularMarketDayLow', 0), 2),
                                'open':       round(q.get('regularMarketOpen', price), 2),
                                'source':     'yahoo'
                            }
        except:
            pass

    return results


@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/health')
def health():
    return jsonify({'status': 'running', 'time': datetime.utcnow().isoformat()})

@app.route('/api/market')
def market():
    return jsonify(fetch_market_data())

@app.route('/api/bias')
def bias():
    results = {}
    data = fetch_market_data()
    for name in ['MNQ', 'MES', 'MGC', 'MCL']:
        d = data.get(name, {})
        price     = d.get('price', 0)
        chg_pct   = d.get('change_pct', 0)
        high      = d.get('day_high', price)
        low       = d.get('day_low',  price)
        rng       = round(high - low, 2) if high and low else 0
        mid       = (high + low) / 2 if high and low else price

        if price == 0:
            results[name] = {'bias': 'NO DATA', 'change_pct': 0, 'price': 0, 'range': 0}
            continue

        if chg_pct > 0.3:
            bias_label = 'BULLISH'
        elif chg_pct < -0.3:
            bias_label = 'BEARISH'
        else:
            bias_label = 'NEUTRAL'

        results[name] = {
            'bias':       bias_label,
            'change_pct': round(chg_pct, 2),
            'price':      price,
            'range':      rng,
            'above_mid':  price > mid,
            'high':       high,
            'low':        low
        }
    return jsonify(results)

@app.route('/api/calendar')
def calendar():
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        r = requests.get(url, timeout=10)
        data = r.json()
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        filtered = []
        for event in data:
            event_date = event.get('date', '')[:10]
            if event_date == today and event.get('impact') in ['High', 'Medium']:
                filtered.append({
                    'time':     event.get('date', ''),
                    'currency': event.get('country', ''),
                    'event':    event.get('title', ''),
                    'impact':   event.get('impact', ''),
                    'forecast': event.get('forecast', ''),
                    'previous': event.get('previous', '')
                })
        return jsonify({'events': filtered, 'source': 'forexfactory'})
    except Exception as e:
        return jsonify({'events': [], 'error': str(e)})

@app.route('/api/news')
def news():
    headlines = []
    sources = [
        ("https://www.forexfactory.com/rss.php?news",                  "Forex Factory"),
        ("https://feeds.marketwatch.com/marketwatch/realtimeheadlines/","MarketWatch"),
        ("https://www.investing.com/rss/news_301.rss",                  "Investing.com"),
    ]
    for url, source in sources:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            root = ET.fromstring(r.content)
            for item in root.findall('.//item')[:8]:
                title   = item.find('title')
                link    = item.find('link')
                pubdate = item.find('pubDate')
                if title is not None and title.text:
                    headlines.append({
                        'title':  title.text.strip(),
                        'link':   link.text.strip() if link is not None else '',
                        'date':   pubdate.text.strip() if pubdate is not None else '',
                        'source': source
                    })
        except:
            pass

    seen, unique = set(), []
    for h in headlines:
        key = h['title'][:60]
        if key not in seen:
            seen.add(key)
            unique.append(h)

    return jsonify({'headlines': unique[:20]})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
