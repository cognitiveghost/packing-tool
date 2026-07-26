# Уніфікована UI/UX дизайн-система для Packing Tool та Shopify Fulfillment Tool

Date: 2026-07-26
Status: Approved

## Контекст

Обидва застосунки — незалежні PySide6 desktop-додатки, кожен зі своєю системою тем, що розійшлися з часом:

- `shopify-fulfillment-tool/gui/theme_manager.py` — dataclass `ThemeColors` +
  singleton `ThemeManager`, один великий f-string, що будує глобальний
  stylesheet.
- `packing-tool/src/theme.py` — окремі функції `_dark_palette()`/
  `_light_palette()` + два зовнішні файли `styles_dark.qss`/
  `styles_light.qss`.

Обидва вже мають перемикач light/dark через власний `QSettings`, але з
різними акцентними кольорами, різним border-radius, різними відступами.
Користувач попросив: (1) єдиний high-contrast стиль light/dark у дусі Visual
Studio/VS Code для обох застосунків, (2) кращий загальний дизайн і логічніші
таблиці (особливо в Packing Tool), (3) прибрати інформаційні банери-приклади,
показані на скріншотах, (4) кращий resize вікон під різні монітори.

Аудит коду підтвердив конкретні, раніше не озвучені проблеми:

- **75 хардкод-кольорів** (`#RRGGBB` напряму в `setStyleSheet()`) розкидані
  по ~15 файлах `shopify-fulfillment-tool/gui/*.py` — в обхід
  `theme_manager.py`, що прямо порушує правило, вже задокументоване в
  проєктному `CLAUDE.md` ("Never use... hardcoded colors").
- **8+ різних значень** `setSpacing()`/`setContentsMargins()` без жодної
  спільної шкали (0,0,0,0 / 10,10,10,10 / 8,2,8,2 / 5,5,5,5 / 4,4,4,4 тощо).
- **18 викликів** `setFixedWidth/Height/Size` в shopify-tool, частина з яких
  заважає нормальному resize вікна.
- Обидва скріншоти, які надав користувач, — з Shopify Tool: дубльований
  приклад-банер у `gui/column_mapping_widget.py:100` ("ℹ️ Enter the exact
  column names... Example: 'Name' → 'Order_Number'...") і нотатка у
  `gui/settings_window_pyside.py:455-456` ("Templates and custom output
  directories are no longer used...").
- Packing Tool використовує суттєво більше кольорових emoji
  (✅⚡🕐💻👤📋📦🌙☀️🟢🟡🟠🔵🔴), включно зі статус-іконками, вбудованими
  прямо в текст комірок таблиці (`f"{icon} {label}"` у
  `sessions_list_widget.py::STATUS_CONFIG`).

Через brainstorming з мокапами (superpowers visual companion) погоджено
конкретні дизайн-рішення для палітри та для 4 окремих екранів (див. Обсяг
нижче).

Вже існує прецедент для об'єднання спільного коду між цими двома
репозиторіями: `packing-tool/shared/` — канонічне джерело для
`stats_manager.py`, `file_lock.py`, `atomic_write.py`, `session_id.py` тощо
(див. `docs/superpowers/specs/2026-07-25-shared-unification-design.md`),
синхронізоване в shopify-fulfillment-tool через
`shopify-fulfillment-tool/scripts/sync_shared.py` (one-way copy, без
submodule). Той самий механізм використовується тут для теми.

## Обсяг

В межах цього проєкту:

1. **Один канонічний `shared/theme.py`** (+ спільні QSS-білдери), доданий у
   `packing-tool/shared/` і синхронізований в shopify-fulfillment-tool через
   існуючий `sync_shared.py`. Замінює обидві поточні системи тем.
2. **Уніфікована палітра/токени**, затверджена мокапом:
   - Dark: чорний фон (#000000), білі рамки (#FFFFFF) — вже близько до
     поточного стану shopify-tool.
   - Light: білий фон (#FFFFFF), майже чорні рамки (#1A1A1A) — **дзеркально**
     до dark, замість поточного блідо-сірого (#CCCCCC) — найбільша видима
     зміна.
   - Єдиний акцентний колір **`#007ACC`** (класичний VS Code blue) замість
     двох трохи різних відтінків синього, які застосунки використовують
     зараз.
   - Семантичні кольори success/warning/error лишаються близькими до вже
     вживаних (обидва застосунки й так майже узгоджені тут).
   - Border-radius: 4px по всьому додатку (наразі 6-8px в shopify-tool).
   - Моноширинний шрифт для табличних числових/кодових колонок (SKU,
     кількість); системний UI-шрифт — для міток і контролів.
3. **Прибрати 75 хардкод-кольорів** в shopify-fulfillment-tool — маршрутизація
   через токени теми (здебільшого механічно: `#4CAF50`→success,
   `#f44336`→error, `#FF9800`→warning, `#2196F3`→accent). Провести такий
   самий аудит в packing-tool під час імплементації (перевірено поки що
   лише shopify-tool).
4. **Єдина шкала відступів** — 4/8/12/16/24px. Застосовується до екранів,
   які вже переробляються в межах цього проєкту (Packer Mode, Settings
   window, діалоги з хардкод-кольорами); без суцільного переписування
   кожного виклику `setSpacing`/`setContentsMargins` в обох застосунках —
   шкала документується як стандарт для нового коду.
5. **Збереження/відновлення геометрії головного вікна** (`QSettings`),
   обмежене доступним екраном при відновленні (щоб вікно не відкрилось поза
   межами екрана, якщо востаннє воно було на іншому моніторі). Перегляд 18
   викликів `setFixedWidth/Height/Size` в shopify-tool (і відповідний аудит
   в packing-tool) — заміна на size policy + мінімальні розміри там, де це
   реально заважає resize; легітимні фіксовані розміри (напр. кнопки
   розміром з іконку) лишаються.
6. **Мінімізація emoji**: декоративні/кольорові emoji прибираються повністю
   (✅⚡🕐💻👤📋📦🌙☀️). Кольорові статус-індикатори (🟢🟡🟠🔵🔴 в
   packing-tool) замінюються на маленький перевикористовуваний theme-aware
   віджет `StatusDot` замість emoji-гліфа, вбудованого в текст комірки.
   Прості монохромні службові гліфи (✓ ✕ ⚠ ☰ ⚙) — оцінюються індивідуально
   під час імплементації проти нової палітри; лишаються, якщо не
   конфліктують візуально.
7. **Прибрати конкретні інформаційні банери**, вказані користувачем:
   дубльований приклад-банер у `column_mapping_widget.py:100` і нотатка
   "templates no longer used" у `settings_window_pyside.py:455-456`. Під час
   імплементації — пройтись по обох застосунках у пошуку подібного патерну
   (ℹ️ / "Note:" / "Example:") і прибрати такі ж редундантні банери.
8. **Перебудова 4 екранів** (кожен окремо затверджений через мокап,
   опція "A" у всіх чотирьох):

   **Packing Tool → Packer Mode** (`src/packer_mode_widget.py`): зараз права
   колонка (~25% ширини) містить одночасно 4-колонкову summary-таблицю,
   dev-only scan simulator, feed сповіщень, і сам сканер-інпут — причому
   сканер-інпут (найчастіше використовуваний контрол) розташований останнім
   у стеку з п'яти елементів. Пропозиція: сканер-інпут переноситься на верх
   головної (лівої) панелі як головний елемент робочого циклу; права
   колонка стає glance-only (stat-тайли "Packed X/Y", "Items X/Y" + короткі
   списки history/extras, без багатоколонкових таблиць); summary-таблиця
   переїжджає у вкладку на всю ширину поруч з таблицею замовлення; dev
   scan-simulator прибирається з production-макета.

   **Packing Tool → Session Browser** (`src/session_browser/sessions_list_widget.py`):
   зараз — тісний inline filter-row (мітки "Status:"/"From:"/"To:" впереміш
   із контролами), і ДВА окремих рядки кнопок під таблицею (QGroupBox
   "Session Details" з preview-міткою + 2 кнопками, і окремий
   `action_layout` ще з 3 кнопками), плюс статус-колонка конкатенує
   emoji-коло прямо в текст комірки. Пропозиція: один консолідований
   action-bar (контекстна інформація + головна дія зліва, розділювач,
   list-level дії справа); статус-колонка — колірна крапка-віджет
   (`StatusDot`) замість emoji; впорядкований filter-row.

   **Shopify Tool → Main window** (`gui/main_window_pyside.py` +
   `gui/ui_manager.py`): `SessionBrowserWidget` інстанціюється ДВІЧІ — один
   раз на всю ширину як вкладка "Session Browser" (Tab 3), і ще раз
   стиснутий у 40%-ширини бічну панель всередині вкладки "Session Setup"
   (Tab 1) — той самий віджет, одне з двох розміщень занадто вузьке, щоб
   бути корисним. Пропозиція: бічна панель у Tab 1 стає легким списком
   "Recent Sessions" (останні 5 сесій, по одному рядку, з посиланням
   "Open full Session Browser →" на Tab 3) замість повного вбудованого
   браузера; повноцінний Session Browser лишається виключно на Tab 3.

   **Shopify Tool → Settings window** (`gui/settings_window_pyside.py`,
   3800+ рядків — найбільший файл у застосунку): 10 вкладок верхнього рівня
   в одній горизонтальній `QTabWidget`-стрічці (General, Rules, Packing
   Lists, Stock Exports, Mappings, Sets, Weight, Tag Categories, Column
   Config, SKU Labels), причому "Weight" додатково гніздить ще одну
   tab-стрічку всередині себе (Products / Boxes). Пропозиція: заміна на
   згруповану ліву навігацію (список категорій зліва, контент справа) у
   стилі VS Code Settings — ті самі 10 пунктів призначення, згруповані в 4
   категорії (Data / Fulfillment Logic / Output / Organization); вкладене
   гніздо "Weight" стає розгортним пунктом лівої навігації замість
   вкладеної `QTabWidget`.

Поза обсягом:

- Зміни бекенд-логіки/бізнес-правил — це суто GUI/UX шар.
- Повний механічний переспис усіх ~90 викликів `setSpacing`/
  `setContentsMargins` в обох застосунках — торкаємось лише екранів, які і
  так переробляються.
- Реструктуризація інших вкладок Shopify Tool (Information/Tools/Reports) чи
  інших діалогів Packing Tool, крім Session Browser і Packer Mode —
  користувачем не піднімалось; може бути окремим наступним проєктом.
- Автоматизовані UI-тести для PySide6-макетів (снепшоти/pixel-diff) — не
  існують в жодному з застосунків сьогодні, не додаються цим проєктом.

## Архітектура

**Канонічне джерело:** `packing-tool/shared/theme.py`, за тим самим
патерном, що вже встановлений для `stats_manager.py` (див.
`2026-07-25-shared-unification-design.md`). Синхронізація в
shopify-fulfillment-tool — існуючим `scripts/sync_shared.py` без змін до
самого скрипта (він вже копіює всі файли з `packing-tool/shared/`).

**Чому один спільний модуль, а не два узгоджені вручну:** обидва застосунки
вже мають дублювання аналогічного коду для тем (giant f-string в
shopify-tool vs окремі `.qss` файли в packing-tool) — саме це розходження і
є джерелом "minor inconvenient style decisions", які користувач відчув, не
завжди можучи точно вказати де. Об'єднання усуває джерело майбутнього
дрейфу так само, як це вже зроблено для `stats_manager.py`/`file_lock.py`/
`session_id.py`.

**API `shared/theme.py`:**

- `ThemeTokens` — dataclass із кольорами/токенами: `background`, `surface`
  (elevated), `text`, `text_secondary`, `border`, `border_subtle`, `hover`,
  `active_bg`, `active_border`, `accent` (`#007ACC`), `accent_green`,
  `accent_orange`, `accent_red`, `radius` (4), `spacing_xs/sm/md/lg/xl`
  (4/8/12/16/24), `font_family`, `font_family_mono`.
- `LIGHT_THEME`, `DARK_THEME` — готові інстанси `ThemeTokens`.
- `build_stylesheet(tokens: ThemeTokens) -> str` — один спільний QSS-генератор,
  замінює і f-string-білдер shopify-tool, і два окремі `.qss` файли
  packing-tool.
- `build_palette(tokens: ThemeTokens) -> QPalette` — замінює обидві поточні
  `_dark_palette()`/`_light_palette()` (packing-tool) і `_build_palette()`
  (shopify-tool).
- `apply_theme(app: QApplication, theme_name: str) -> None` — застосовує
  stylesheet + палітру. Кожен застосунок і надалі сам зберігає вибір теми у
  власному `QSettings` (org/key лишаються різні для кожного застосунку — це
  per-machine налаштування, не спільні дані).
- `StatusDot(QWidget)` — маленький theme-aware кружечок для
  статус-індикаторів у таблицях, заміняє emoji-кола (споживає
  `accent_green`/`accent_orange`/`accent_red`/`accent` тощо замість
  довільних hex-кольорів з поточного `STATUS_CONFIG`).
- `save_window_geometry(window, settings)` /
  `restore_window_geometry(window, settings)` — спільні хелпери; при
  відновленні перетинають збережену геометрію з
  `QGuiApplication.primaryScreen().availableGeometry()` (або будь-яким
  доступним екраном), щоб вікно не відновилось поза межами поточного
  монітора.

**Інтеграція без ламання існуючого публічного API:**

- `shopify-fulfillment-tool/gui/theme_manager.py` — зберігає публічний API
  (`get_theme_manager()`, `.get_current_theme()`, `.toggle_theme()` тощо, що
  вже викликається у ~30 місцях по всьому `gui/`), але внутрішньо делегує в
  `shared.theme` замість власного f-string-білдера. Мінімізує diff у місцях
  виклику.
- `packing-tool/src/theme.py` — так само зберігає публічний API
  (`apply_theme`, `load_saved_theme`, `toggle_theme`), делегуючи в
  `shared.theme`; файли `styles_dark.qss`/`styles_light.qss`/`styles.qss`
  видаляються — стилі генеруються з `shared.theme.build_stylesheet()`.

## Компоненти

**Нові файли:**
- `packing-tool/shared/theme.py` (канонічний: токени, білдери, `StatusDot`,
  геометрія-хелпери)

**Змінені файли — спільна тема:**
- `shopify-fulfillment-tool/gui/theme_manager.py` — делегує в `shared.theme`
- `packing-tool/src/theme.py` — делегує в `shared.theme`
- `packing-tool/src/styles_dark.qss`, `styles_light.qss`, `styles.qss` —
  видаляються

**Змінені файли — прибрати хардкод-кольори (shopify-tool, ~15 файлів):**
- `gui/settings_window_pyside.py`, `gui/pandas_model.py`,
  `gui/add_product_dialog.py`, `gui/client_sidebar.py`,
  `gui/client_settings_dialog.py`, `gui/tag_categories_dialog.py`,
  `gui/rule_test_dialog.py`, `gui/background_worker.py`,
  `gui/ui_manager.py`, `gui/log_viewer.py`,
  `gui/groups_management_dialog.py`, `gui/report_selection_dialog.py`,
  `gui/barcode_generator_widget.py`, `gui/tag_management_panel.py`,
  `gui/session_browser_widget.py`

**Змінені файли — 4 екрани:**
- `packing-tool/src/packer_mode_widget.py` — перебудова макета
- `packing-tool/src/session_browser/sessions_list_widget.py` —
  консолідований action-bar, `StatusDot`
- `shopify-fulfillment-tool/gui/main_window_pyside.py`,
  `gui/ui_manager.py` — усунення дубльованого Session Browser
- `shopify-fulfillment-tool/gui/settings_window_pyside.py` — перехід з
  `QTabWidget` (10 вкладок) на згруповану ліву навігацію

**Змінені файли — геометрія вікна:**
- `packing-tool/src/main.py`
- `shopify-fulfillment-tool/gui/main_window_pyside.py`

**Змінені файли — інформаційні банери:**
- `shopify-fulfillment-tool/gui/column_mapping_widget.py` (рядок ~100)
- `shopify-fulfillment-tool/gui/settings_window_pyside.py` (рядки 455-456)

## Дані / виклики, що змінюються

- Кожен застосунок і надалі сам вирішує, яка тема активна (light/dark),
  через власний `QSettings` — тут нічого спільного не з'являється, лише
  самі токени й білдери стають спільними.
- `column_mapping_widget.py`: приклад-банер видаляється повністю (не
  скорочується) — сам факт, що приклад дублювався двічі на одному діалозі,
  і був причиною скарги користувача.
- `settings_window_pyside.py:455-456`: нотатка "templates no longer used"
  видаляється повністю.
- `sessions_list_widget.py::STATUS_CONFIG` — поле `"icon"` (emoji)
  прибирається; поле `"color"` (вже існує в конфізі) споживається новим
  `StatusDot` замість конкатенації в текст.

## Порядок виконання

1. Побудувати `packing-tool/shared/theme.py` (токени, білдери
   стилю/палітри, `StatusDot`, геометрія-хелпери) + self-check.
2. Синхронізувати в shopify-fulfillment-tool через `scripts/sync_shared.py`.
3. Переключити `packing-tool/src/theme.py` на делегування в `shared.theme`,
   видалити `.qss`-файли, прогнати self-check/smoke.
4. Переключити `shopify-fulfillment-tool/gui/theme_manager.py` на
   делегування в `shared.theme`, прогнати `ruff check .` + smoke.
5. Прибрати 75 хардкод-кольорів у shopify-tool; аудит + виправлення
   аналогічного у packing-tool.
6. Перебудувати Packer Mode (packing-tool).
7. Перебудувати Session Browser (packing-tool).
8. Усунути дублювання Session Browser у Main window (shopify-tool), додати
   збереження/відновлення геометрії вікна в обох застосунках.
9. Перевести Settings window (shopify-tool) на ліву навігацію.
10. Прибрати вказані інформаційні банери + аудит на подібні патерни в обох
    застосунках.
11. Прибрати/замінити emoji за затвердженою політикою (обидва застосунки).

## Тестування / self-check

- `shared/theme.py` — `if __name__ == "__main__":` self-check: побудувати
  обидві теми, перевірити, що `build_stylesheet()` повертає непорожній
  рядок для кожної, і що всі кольори у `ThemeTokens` — валідні hex
  (`assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value)`).
- `save_window_geometry`/`restore_window_geometry` — короткий assert-тест:
  зберегти geometry поза межами доступного екрана, відновити — перевірити,
  що результат затиснутий у межі `availableGeometry()`.
- packing-tool: `python -m pytest tests/ -v` (існуючий набір) має
  продовжувати проходити без змін.
- shopify-fulfillment-tool: `ruff check .` + `CI=1 python run_dev.py`
  (існуючий headless smoke-тест) — за поточним `CLAUDE.md`.
- Візуальна перевірка вручну (обидва застосунки, light+dark, кілька
  розмірів вікна) — автоматичного UI-тесту для PySide6-макетів не додається
  (поза обсягом, як зазначено вище).

## Відхилений варіант

Тримати дві окремі, але "візуально узгоджені вручну" системи тем (два
файли/два набори QSS, кольори підтримуються в синхроні вручну). Відхилено:
обидва застосунки вже перебувають у цьому стані сьогодні (майже однакові,
але не ідентичні токени/радіуси/відступи) — і саме це розходження призвело
до "minor inconvenient style decisions", які користувач відчув. Спільний
модуль усуває джерело дрейфу так само, як це вже зроблено для
`stats_manager.py`.
