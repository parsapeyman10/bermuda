# Black Bermuda — Desktop GUI

نسخه‌ی دسکتاپیِ همان شبیه‌ساز (PyQt6) — کندل‌به‌کندل، کاملاً آفلاین، **بدون هیچ تغییری در منطق تحلیل**؛
لایه‌ی دسکتاپ فقط یک پوسته‌ی نازک روی همان `simulator/server.py:analyse_payload` و `bermuda_detector/bermuda_core.py` است.
A native PyQt6 desktop front-end for the same offline v0.4 replay simulator. No lookahead, no network, no new analysis logic.

## نصب روی هر ویندوز / Install on any Windows PC

```bat
install_gui.bat
```

اسکریپت: پایتون ۳٫۱۰+ را پیدا می‌کند (`py -3` یا `python`)، یک `.venv` محلی در ریشه‌ی مخزن می‌سازد،
وابستگی‌ها را از `bermuda_gui/requirements.txt` نصب می‌کند، import را راستی‌آزمایی می‌کند و یک میانبر
«Black Bermuda GUI» روی دسکتاپ می‌سازد (آیکن: `bermuda_gui/assets/icon.ico`).
اجرا بدون میانبر: `run_gui.bat` یا `python -m bermuda_gui` از ریشه‌ی مخزن.

پیش‌نیاز: فقط [Python 3.10+](https://www.python.org/downloads/) با چک‌خوردنیِ «Add to PATH». همه‌چیزِ دیگر خودکار نصب می‌شود.

> روی لینوکس/مک هم اجرا می‌شود (`python3 -m bermuda_gui`)، فقط میانبر دسکتاپ و `.bat` ویندوزی هستند.

## ویژگی‌ها

- **همان تجربه‌ی وب، بومی**: کندل + ابر ایچیموکو + مثلث/wedge/zone + پنجره‌های زمانی (تخت‌بودن Senkou B با چک ۲۶ باری) + برچسب حمایت/مقاومت و cover + zone ∩ پنجره روی بار جاری + چیپ‌های تأیید (Time / قیمت داخل zone / Chikou / Double Bermuda §6.13).
- **Transport کامل**: پخش/مکث با سرعت ۰٫۵× تا ۸×، قدم ±۱/±۱۰، پرش به ابتدا/انتها، اسلایدر بار، میانبرها (Space, ←/→, Shift+←/→, Home/End).
- **Zone map تعاملی**: اسکن پس‌زمینه با پارامترهای فعلی در یک `QThread` (UI قفل نمی‌کند)؛ tickهای آبی/قرمز زیر نمودار + minimap سیگنال؛ کلیک برای جهش.
- **پارامترهای زنده**: deg, eps, min_dy, min_dx, angle_max, mincover, H — هر تغییر، تحلیل (با cache LRU) و zone map را دوباره می‌سازد.
- **فیلتر جهت setup (§5.2/5.3)**: «هر دو / فروش / خرید» — تحلیل و zone map فقط در جهت انتخابی.
- **سطوح زمانی §8**: لایه‌ی «سطوح زمانی §8» + کارت «سطوح زمانی §8» (افقی رأس نهایی، سه سطح تلاقی پا، همراه با `assumption` روش 12.4).
- **Fractal (§7.2/7.3)**: دکمه‌ی «⧖ Fractal» — زیر-تایم‌فریم synthetic قطعی (پل بروانی seeded pinned به OHLC پایه؛ دموی هندسی آموزشی، نه داده‌ی واقعی). خروجی: ناحیه‌ی باریک‌تر teal یا «zone کلاسیک ماند (7.2.8)».
- **بارگذاری CSV شما**: دکمه‌ی «＋ CSV» — ستون‌های `date,open,high,low,close` (حداقل ۲۰۰ بار)؛ اعتبارسنجی محلی؛ در حافظه ثبت می‌شود و در combo با آیکن 📄 ظاهر می‌شود.
- **لایه‌ها و تم**: ۱۲ لایه‌ی قابل خاموش/روشن، تم تیره‌ی ترمینال پژوهشی (QSS)، ظاهر فارسی با اعداد/متغیرها به لاتین.
- **خروجی PNG**: ذخیره‌ی مستقیم وضعیت فعلی نمودار.

## معماری (اصول روز دنیا)

```
bermuda_gui/
├── app.py         # bootstrap: QApplication، استایل Fusion + build_qss()، آیکن
├── theme.py       # توکن‌های طراحی + QSS (تنها منبع حقیقت ظاهر)
├── paths.py       # تکیه‌گاه sys.path (ریشه + bermuda_detector/ + simulator/)
├── data.py        # لایه‌ی سرویس: AnalyseService — LRU cache، sweep (QThread)، fractal on-demand، register CSV، CSV register، بدون Qt
├── chart.py       # ChartWidget/MinimapWidget — رندر QPainter (کندل/ابر/زون/crosshair)
├── main_window.py # پوسته‌ی نازک UI: transport bar، پنل کناری، میانبرها؛ هیچ منطق تحلیلی ندارد
└── assets/        # icon.png / icon.ico
```

- **Service/UI separation**: `data.AnalyseService` کاملاً بدون Qt است و با تستِ `tests/test_gui_service.py` پوشش داده می‌شود. UI هرگز `bermuda_core` را مستقیم صدا نمی‌زند.
- **Single source of truth**: همان `analyse_payload` سروری؛ یعنی GUI و وب نسخه‌ی وب همیشه خروجی یکسان می‌دهند.
- **Cache + background work**: تحلیل ~۲۰ms با LRU cached است؛ sweep سنگین (کل تاریخچه) در thread جدا با نوار پیشرفت اجرا می‌شود.
- **Fail-safe**: شکست sweep روی یک بار، کل اسکن را نمی‌کشد؛ خطای import در `closeEvent`، thread را تمیز متوقف می‌کند.

## محدودیت‌ها (همان هشدارهای اصلی)

انتخاب سیاست مثلث، آستانه‌ها (deg/eps/…) و پنجره‌های زمانی روی داده‌ی واقعی **اعتبارسنجی نشده‌اند**؛ GOOG نمونه‌ی روزانه‌ی matplotlib است و روی FX 1h چیزی تست نشده. هیچ edge معاملاتی ادعا نمی‌شود — ابزار برای آموزش و پژوهش است. پلتفرم هدف ویندوز است؛ روی لینوکس بدون کتابخانه‌های سیستمیِ Qt6 (مثل `libxkbcommon`) ممکن است بالا نیاید.
