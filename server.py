"""
Trading News Report — Daily Bias Dashboard
Separate Railway app, does not touch apex-tracker
"""
from flask import Flask, jsonify
from flask_cors import CORS
import os

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/health')
def health():
    from datetime import datetime
    return jsonify({'status': 'running', 'time': datetime.utcnow().isoformat()})

@app.route('/api/calendar')
def calendar():
    """Fetch economic calendar from tradingeconomics / investing.com via scrape"""
    import requests
    from datetime import datetime, timezone
    try:
        # Use forexfactory calendar API (free, no key needed)
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        r = requests.get(url, timeout=10)
        data = r.json()
        # Filter for today and high/medium impact
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        filtered = []
        for event in data:
            event_date = event.get('date', '')[:10]
            if event_date == today and event.get('impact') in ['High', 'Medium']:
                filtered.append({
                    'time': event.get('date', ''),
                    'currency': event.get('country', ''),
                    'event': event.get('title', ''),
                    'impact': event.get('impact', ''),
                    'forecast': event.get('forecast', ''),
                    'previous': event.get('previous', '')
                })
        return jsonify({'events': filtered, 'source': 'forexfactory'})
    except Exception as e:
        return jsonify({'events': [], 'error': str(e)})

@app.route('/api/market')
def market():
    """Fetch futures prices and VIX"""
    import requests
    from datetime import datetime, timezone
    results = {}
    symbols = {
        'MNQ': 'MNQ=F',
        'MES': 'MES=F', 
        'MGC': 'MGC=F',
        'MCL': 'MCL=F',
        'VIX': '^VIX',
        'DXY': 'DX-Y.NYB'
    }
    try:
        # Use Yahoo Finance for quick quotes
        tickers = ' '.join(symbols.values())
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={tickers}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        quotes = data.get('quoteResponse', {}).get('result', [])
        for q in quotes:
            sym = q.get('symbol', '')
            for name, yf_sym in symbols.items():
                if sym == yf_sym:
                    results[name] = {
                        'price': q.get('regularMarketPrice', 0),
                        'change': q.get('regularMarketChange', 0),
                        'change_pct': q.get('regularMarketChangePercent', 0),
                        'prev_close': q.get('regularMarketPreviousClose', 0),
                        'day_high': q.get('regularMarketDayHigh', 0),
                        'day_low': q.get('regularMarketDayLow', 0),
                    }
    except Exception as e:
        results['error'] = str(e)
    return jsonify(results)

@app.route('/api/news')
def news():
    """Fetch market news headlines"""
    import requests
    try:
        # Use Yahoo Finance news RSS
        url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ES=F,NQ=F,GC=F,CL=F&region=US&lang=en-US"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall('.//item')[:15]:
            title = item.find('title')
            link  = item.find('link')
            pubdate = item.find('pubDate')
            items.append({
                'title': title.text if title is not None else '',
                'link':  link.text  if link  is not None else '',
                'date':  pubdate.text if pubdate is not None else ''
            })
        return jsonify({'headlines': items})
    except Exception as e:
        return jsonify({'headlines': [], 'error': str(e)})

@app.route('/api/bias')
def bias():
    """Compute daily bias for each instrument based on market data"""
    import requests
    from datetime import datetime, timezone
    biases = {}
    symbols = {
        'MNQ': 'MNQ=F',
        'MES': 'MES=F',
        'MGC': 'MGC=F', 
        'MCL': 'MCL=F'
    }
    try:
        tickers = ' '.join(symbols.values())
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={tickers}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        quotes = data.get('quoteResponse', {}).get('result', [])
        for q in quotes:
            sym = q.get('symbol', '')
            for name, yf_sym in symbols.items():
                if sym == yf_sym:
                    chg_pct = q.get('regularMarketChangePercent', 0)
                    price   = q.get('regularMarketPrice', 0)
                    prev    = q.get('regularMarketPreviousClose', 1)
                    high    = q.get('regularMarketDayHigh', price)
                    low     = q.get('regularMarketDayLow',  price)
                    rng     = high - low
                    mid     = (high + low) / 2
                    
                    if chg_pct > 0.3:
                        bias = 'BULLISH'
                    elif chg_pct < -0.3:
                        bias = 'BEARISH'
                    else:
                        bias = 'NEUTRAL'

                    biases[name] = {
                        'bias': bias,
                        'change_pct': round(chg_pct, 2),
                        'price': price,
                        'range': round(rng, 2),
                        'above_mid': price > mid
                    }
    except Exception as e:
        biases['error'] = str(e)
    return jsonify(biases)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
