# Black Bermuda Simulator (shebehsaaz)

بازتولید تعاملیِ کل pipeline نسخه v0.4 پروژه‌ی `bermuda_detector` روی نمودار قیمت — کندل‌به‌کندل.
An interactive, fully offline replay simulator for the Black Bermuda detector (v0.4 pipeline):
candles + Ichimoku cloud + Senkou-A extremes → steep legs → triangles → wedges → zones → flat-Senkou-B time windows.

## اجرا / Run

```bash
# از ریشه‌ی مخزن — یک بار:
python3 -m venv .venv
.venv/bin/pip install numpy pandas scipy matplotlib opencv-python-headless flask

# هر بار:
.venv/bin/python simulator/server.py        # http://0.0.0.0:8778
```

پورت با متغیر محیطی `PORT` عوض می‌شود. تمام محاسبات محلی است؛ داده‌ی GOOG داخل خود matplotlib است.

## ویژگی‌ها

- **بازتورید کندل‌به‌کندل**: پخش/مکث/قدم/پرش، سرعت ۰٫۵× تا ۸×، کلیدهای میانبر (Space, ←/→)، اسلایدر بار.
- **محاسبه‌ی زنده‌ی pipeline در هر بار** (بدون lookahead؛ میانگین ≈۲۰ms در این ماشین) — مثلث‌ها، wedgeها، zoneها با برچسب حمایت/مقاومت و پوشش (cover) و برش H ATR.
- **Zone map**: اسکن پس‌زمینه‌ی کل تاریخچه با پارامترهای فعلی؛ نمایش tickهای رنگی (آبی=حمایت / قرمز=مقاومت) زیر نمودار؛ کلیک/درگ برای جهش.
- **داده‌ها**: GOOG واقعی روزانه (matplotlib sample) + ۴ سناریوی مصنوعیِ seeded (bull / bear / range / shock) با موج‌های ایچیموکویی آشکار برای آموزش.
- **پارامترهای زنده**: deg, eps, min_dy, min_dx, angle_max, mincover, H — هر تغییر، cache و zone map را دوباره می‌سازد.
- لایه‌های قابل روشن/خاموش، crosshair + OHLC tooltip، زوم با چرخ ماوس، خروجی PNG نمودار.

## ساختار

```
simulator/
├── server.py        # Flask: API (/api/data, /api/analyse, /api/sweep) + static
├── datasets.py      # ثبات داده: GOOG واقعی + مولد OHLC مصنوعی (seeded)
└── static/
    ├── index.html   # چیدمان RTL (فارسی) با اصطلاحات انگلیسی
    ├── style.css    # تم تیره‌ی ترمینال پژوهشی
    └── app.js       # کانواس: رندر شمع/ابر/مثلث/zone + minimap + منطق پخش
```

## API

- `GET /api/datasets`
- `GET /api/data?ds=goog|bull|bear|range|shock`
- `GET /api/analyse?ds=…&xc=بار&deg=&eps=&min_dy=&min_dx=&angle_max=&mincover=&H=`
- `GET /api/sweep?ds=…&step=2&…پارامترها` → `{status: cached|running, job?}`; رویش با `GET /api/sweep/status/<job>` پول کنید.

## محدودیت‌ها (از README اصلی)

انتخاب سیاست مثلث، آستانه‌ها (deg/eps/…) و پنجره‌های زمانی روی داده‌ی واقعی **اعتبارسنجی نشده‌اند**؛ GOOG نمونه است و روی FX 1h چیزی تست نشده. هیچ edge معاملاتی ادعا نمی‌شود — ابزار برای آموزش و پژوهش است.

## آزمون‌ها / Tests

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -q          # ۴۳ تست: wedge math، ground-truth مثلث/zone، API، consistency
.venv/bin/python simulator/validate.py        # گزارش اعتبارسنجی روی corpus مصنوعی + GOOG + کنترل noise
```

تست‌ها شامل: half-plane clipping و wedge interiors، مثلث‌های ساخته‌شده‌ی دستی با apexهای معلوم، zone با هم‌پوشانی ساخته‌شده‌ی دستی (crossed cones)، چک ۲۶ باری Senkou B، golden regression روی shock@204 (tris≥3, zones≥1)، invariant پلی‌گون zone (inside تمام bounding wedges + برش H)، OHLC invariants برای همه‌ی دیتاست‌ها، JSON hygiene (NaN هرگز صادر نمی‌شود)، و یک test suite استاتیک که از بازگشت مسیرهای مطلق قدیمی جلوگیری می‌کند.

گزارش اعتبارسنجی (deg=8): GOOG ≈ ۴٫۳٪ بارهای zone (هم‌خونی با README اصلی)، سناریوهای موج‌دار ۲–۳۸٪، **noise خالص = ۰٪**، invariant failures = ۰. touch rate توصیفی است، نه ادعای edge.
