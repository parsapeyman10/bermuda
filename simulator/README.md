# Black Bermuda Simulator (shebehsaaz)

بازتولید تعاملیِ کل pipeline پروژه‌ی `bermuda_detector` روی نمودار قیمت — کندل‌به‌کندل، مطابق فایل روش `black_bermuda_method.txt`.
An interactive, fully offline replay simulator for the Black Bermuda detector (v0.4 + method-completion v1.1 pipeline):
candles + Ichimoku cloud + Senkou-A extremes → steep legs → triangles → wedges → zones → flat-Senkou-B time windows,
plus the §7.2/7.3 fractal models, the §8 time-based price levels, the §5.2/5.3 setup direction filter and the §6.13 double-Bermuda confirmation.

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
- **پارامترهای زنده**: deg, eps, min_dy, min_dx, angle_max, mincover, H — هر تغییر، cache و zone map را دوباره می‌سازد. پیش‌فرض `angle_max=90` مطابق قاعده‌ی سخت §4.9 روش (رأس ≤ ۹۰°).
- **فیلتر جهت setup (§5.2/5.3)**: «هر دو / فروش / خرید» — zones و مثلث‌ها فقط در جهت انتخابی اعمال می‌شوند (`setup=both|sell|buy`).
- **سطوح زمانی §8**: خط افقی از رأس مثلث نهایی، خطوط عمودی apex/+9/+17/+26 و سه سطح قیمت (تلاقی پاهای کپی‌شده‌ی مثلث — فرض مستند در payload؛ §12.4 روش این هندسه را دقیق معین نکرده). قابل خاموش/روشن با لایه‌ی «سطوح زمانی §8».
- **Fractal (§7.2/7.3)**: دکمه‌ی «⧖ Fractal» ناحیه‌ی باریک‌تر (narrow zone) را با زیر-تایم‌فریم‌های **synthetic قطعی** (پل بروانی seeded pinned به OHLC پایه — دموی هندسی آموزشی، نه داده‌ی واقعی intraday) محاسبه می‌کند. زیرنمودار روی corpus شوک روزانه معمولاً صفر مثلث واجد شرایط می‌یابد → «zone کلاسیک ماند (7.2.8)». برای تمرین واقعی، CSV واقعی بارگذاری کنید.
- **بارگذاری CSV شما**: دکمه‌ی «＋ CSV» — ستون‌های `date,open,high,low,close` (حداقل ۲۰۰ بار، prices مثبت، high≥low)؛ اعتبارسنجی سمت سرور؛ بدون ذخیره‌ی دائمی (حافظه‌فقط در این پروسه).
- **Double Bermuda (§6.13)**: بنر طلایی وقتی هم قیمت و هم Chikou داخل یک zone باشند؛ چیپ‌های «Time ✔ / قیمت داخل zone / Chikou ✔» روی هر zone.
- لایه‌های قابل روشن/خاموش، crosshair + OHLC tooltip، زوم با چرخ ماوس، خروجی PNG نمودار.

## ساختار

```
simulator/
├── server.py        # Flask: API (/api/data, /api/analyse, /api/sweep, /api/csv) + static
├── datasets.py      # ثبات داده: GOOG واقعی + مولد OHLC مصنوعی (seeded) + CSV اختصاصی (in-memory)
├── fractal.py       # §7.2/7.3: sub-division قطعی + تحلیل fractal/box + narrowing
└── static/
    ├── index.html   # چیدمان RTL (فارسی) با اصطلاحات انگلیسی
    ├── style.css    # تم تیره‌ی ترمینال پژوهشی
    └── app.js       # کانواس: رندر شمع/ابر/مثلث/zone + minimap + منطق پخش
```

## API

- `GET /api/datasets`
- `GET /api/data?ds=goog|bull|bear|range|shock|csv:<id>`
- `GET /api/analyse?ds=…&xc=بار&deg=&eps=&min_dy=&min_dx=&angle_max=&mincover=&H=&setup=both|sell|buy[&fractal=box|fractal]`
  - پاسخ شامل `setup`، `levels` (§8: افقی/عمودی‌ها/سطوح + `assumption`)، `double_bermuda` (§6.13)، `sb_flats`، و تأییدهای هر zone (`time_confirmed`, `price_in_zone`, `chikou_in_zone`) است.
  - با `fractal=box|fractal` کلید `fractal` هم ضمیمه می‌شود: `{final, kept, box, narrow_zone|null, note, tf_note}`.
- `POST /api/csv` (multipart، فیلد `file`، فقط `.csv`، حداکثر ۸ MB) → `{id, label, bars}`؛ فایل موقت در `simulator/uploads/` (در .gitignore)؛ تحلیل‌پذیر با همان `csv:<id>`.
- `GET /api/sweep?ds=…&step=2&setup=both|sell|buy&…پارامترها` → `{status: cached|running, job?}`; رویش با `GET /api/sweep/status/<job>` پول کنید. کلید cache شامل `setup` است.

## محدودیت‌ها (از README اصلی)

انتخاب سیاست مثلث، آستانه‌ها (deg/eps/…) و پنجره‌های زمانی روی داده‌ی واقعی **اعتبارسنجی نشده‌اند**؛ GOOG نمونه است و روی FX 1h چیزی تست نشده. هیچ edge معاملاتی ادعا نمی‌شود — ابزار برای آموزش و پژوهش است.

## آزمون‌ها / Tests

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -q          # ۵۵ تست: wedge math، ground-truth مثلث/zone، API، consistency، fractal (synthetic narrowing)
.venv/bin/python simulator/validate.py        # گزارش اعتبارسنجی روی corpus مصنوعی + GOOG + کنترل noise
```

تست‌ها شامل: half-plane clipping و wedge interiors، مثلث‌های ساخته‌شده‌ی دستی با apexهای معلوم، zone با هم‌پوشانی ساخته‌شده‌ی دستی (crossed cones)، چک ۲۶ باری Senkou B، golden regression روی shock@204 (با `angle_max=180` — صریحاً چون corpus شوک روزانه با قاعده‌ی سخت §4.9 (≤۹۰°) هیچ مثلثی نمی‌سازد؛ قاعده روی تایم‌فریم‌های پایین روش اعمال می‌شود)، invariant پلی‌گون zone (inside تمام bounding wedges + برش H)، OHLC invariants برای همه‌ی دیتاست‌ها، JSON hygiene (NaN هرگز صادر نمی‌شود)، تست‌های واحد fractal (انتقال مختصات زیر-تایم‌فریم→پایه، clip ناحیه‌ی باریک، empty-case)، و یک test suite استاتیک که از بازگشت مسیرهای مطلق قدیمی جلوگیری می‌کند.

گزارش اعتبارسنجی (deg=8): GOOG ≈ ۴٫۳٪ بارهای zone (هم‌خونی با README اصلی)، سناریوهای موج‌دار ۲–۳۸٪، **noise خالص = ۰٪**، invariant failures = ۰. touch rate توصیفی است، نه ادعای edge.
