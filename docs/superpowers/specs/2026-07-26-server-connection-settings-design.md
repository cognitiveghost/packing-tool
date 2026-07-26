# Уніфіковані налаштування підключення до сервера (шлях через UI)

Date: 2026-07-26
Status: Approved

## Контекст

Обидва застосунки (`packing-tool`, `shopify-fulfillment-tool`) підключаються
до одного й того самого мережевого файл-сервера (UNC-шлях), але шлях
змінюється лише вручну і по-різному в кожному застосунку:

- `packing-tool`: `config.ini [Network] FileServerPath`, з можливістю
  перевизначити через env var `FULFILLMENT_SERVER_PATH` (це вже уніфіковано
  попереднім проєктом, див.
  `docs/superpowers/specs/2026-07-25-shared-unification-design.md`).
- `shopify-fulfillment-tool`: `FULFILLMENT_SERVER_PATH`, або, якщо не
  задано, шлях, зашитий у код
  (`shopify_tool/profile_manager.py::_get_base_path`).

У жодному з двох немає UI для зміни шляху — редагування `config.ini` чи
джерела, і перезапуск. Якщо сервер недоступний при старті, обидва
`ProfileManager.__init__` кидають `NetworkError`, а `MainWindow`/`_init_managers`
показує `QMessageBox.critical` і завершує застосунок (`sys.exit(1)` /
`QApplication.quit()`) — без жодної можливості виправити шлях, не виходячи
з програми.

Користувач хоче: (1) шлях до сервера, що конфігурується через UI в обох
застосунках однаковим чином; (2) якщо підключення не вдалось — застосунок
пропонує обрати інший шлях замість негайного виходу; (3) той самий шлях
можна змінити пізніше через Settings.

## Обсяг

У межах цього проєкту:
1. Новий рівень пріоритету джерела шляху — значення, збережене користувачем
   через UI (`QSettings`), між env var (найвищий пріоритет) і існуючим
   fallback (`config.ini` / зашитий шлях).
2. Спільний діалог налаштувань підключення (поле шляху + Browse + Test
   Connection + Save), доступний з Settings-меню (packing-tool) і з
   header-панелі (shopify-fulfillment-tool, там немає menu bar).
3. Recovery-flow при невдалому підключенні на старті: замість негайного
   critical+exit — пропозиція ввести інший шлях, з ретраєм підключення.
4. Винесення дубльованої перевірки доступності шляху
   (`_test_connection`/touch-file) в один спільний `shared/` модуль.

Поза обсягом:
- Live-застосування нового шляху без перезапуску — свідомо відхилено (див.
  "Відхилений варіант"), потрібен перезапуск.
- Зміна поведінки `FULFILLMENT_SERVER_PATH` / `run_dev.py` — не чіпається,
  env var лишається найвищим пріоритетом.
- Зміна формату/розташування `config.ini` — ключ `FileServerPath`
  залишається як fallback останньої черги, як є.
- Спільне сховище налаштувань між двома застосунками — кожен застосунок
  зберігає свій шлях окремо (`QSettings` з різними org/app-іменами); спільний
  лише механізм і UI, не самі дані.

## Архітектура

Порядок визначення ефективного шляху (однаковий в обох застосунках, додається
лише один новий рівень до вже уніфікованого ланцюжка):

1. Env var `FULFILLMENT_SERVER_PATH` — без змін, найвищий пріоритет.
2. **Новий:** значення з `QSettings` (записане через Settings-діалог або
   recovery-prompt).
3. Існуючий fallback — `config.ini [Network] FileServerPath` (packing-tool) /
   зашитий production-шлях (shopify-fulfillment-tool) — без змін.

**Канонічне джерело коду** — `packing-tool/shared/`, за тим самим
контрактом, що й решта `shared/`: зміни вносяться там, і
`shopify-fulfillment-tool/scripts/sync_shared.py` копіює їх у другий
репозиторій. Це дає обом застосункам буквально ідентичну реалізацію
діалогу й логіки перевірки, а не дві паралельні копії.

`QSettings` обрано замість нового файлу конфігурації: `packing-tool` вже
використовує його для `last_client` (`QSettings("PackingTool",
"ClientSelection")`) — той самий механізм, нова org/app-пара
(`"PackingTool"/"Connection"`, `"ShopifyTool"/"Connection"`), без нової
залежності й нового формату файлу.

## Компоненти

Новий файл `shared/server_connection.py`:

- `test_path_reachable(path: str, timeout: int = 5) -> bool` — touch-file
  перевірка, винесена з дубльованих
  `ProfileManager._test_connection()`/`_test_connection()` в обох
  застосунках. Обидва `ProfileManager` викликають саме цю функцію замість
  своєї копії логіки.
- `get_saved_server_path(org: str) -> Optional[str]` /
  `save_server_path(org: str, path: str) -> None` — тонкі обгортки над
  `QSettings(org, "Connection")`, ключ `server_path`.
- `resolve_server_path(org: str, env_var: str, fallback: str) -> str` —
  єдина функція, що реалізує 3-рівневий пріоритет вище; обидва
  `ProfileManager.__init__`/`_get_base_path` викликають її замість власної
  ad hoc перевірки env var.
- `ConnectionSettingsDialog(QDialog)` — `QLineEdit` (попередньо заповнене
  поточним ефективним шляхом) + кнопка "Browse…"
  (`QFileDialog.getExistingDirectory`, для локальних/mapped-drive шляхів) +
  кнопка "Test Connection" (викликає `test_path_reachable`, показує
  ✅/❌ інлайн) + Save/Cancel. Якщо активний env var — над полем неактивне
  попередження "Overridden by FULFILLMENT_SERVER_PATH environment variable",
  поле лишається редагованим (значення однаково збережеться в QSettings),
  але користувачу одразу видно, чому зміна не подіє негайно. Save записує
  через `save_server_path` і показує `QMessageBox.information` "Restart the
  application for the new path to take effect."
- `prompt_for_recovery_path(parent, attempted_path: str, org: str) -> bool` —
  той самий набір полів (шлях + Browse + Test), плюс кнопки Retry/Exit.
  Повертає `True`, якщо користувач зберіг новий шлях і натиснув Retry
  (виклик-стороні варто повторити побудову `ProfileManager`), `False` —
  якщо Exit (виклик-сторона завершує застосунок як і зараз).

## Дані / виклики, що змінюються

- `packing-tool/src/profile_manager.py::__init__` (рядки ~79-91) — виклик
  `os.environ.get(...) or self.config.get(...)` замінюється на
  `resolve_server_path("PackingTool", "FULFILLMENT_SERVER_PATH", config_fallback)`.
  `_test_connection` (рядки 149-172) видаляється, замінюється викликом
  `test_path_reachable(str(self.base_path), self.connection_timeout)`.
- `shopify-fulfillment-tool/shopify_tool/profile_manager.py::_get_base_path`
  (рядки 121-141) — та сама заміна на `resolve_server_path("ShopifyTool",
  "FULFILLMENT_SERVER_PATH", prod_path)`. `_test_connection` (рядки 151+)
  так само замінюється на спільну функцію.
- `packing-tool/src/main.py::MainWindow.__init__` (рядки 174-190) — блок
  `try: ProfileManager(config_path) except NetworkError` обгортається в
  цикл: при `NetworkError` викликається
  `prompt_for_recovery_path(self, str(e), "PackingTool")`; якщо `True` —
  повторити спробу створення `ProfileManager`, якщо `False` — `sys.exit(1)`
  як і зараз.
- `packing-tool/src/main.py::_init_menu_bar` (рядок ~391, Settings-меню) —
  нова `QAction("Server Connection...", self)` →
  `ConnectionSettingsDialog(...).exec()`.
- `shopify-fulfillment-tool/gui/main_window_pyside.py::_init_managers`
  (рядки 127-154) — той самий цикл-з-recovery навколо `ProfileManager()`,
  замість негайного `QApplication.quit()`.
- `shopify-fulfillment-tool/gui/ui_manager.py` (header widget, біля
  `sidebar_toggle_btn`, рядок ~161) — нова кнопка (шестерня/іконка) →
  той самий `ConnectionSettingsDialog`. Menu bar в цьому застосунку немає,
  тому діалог викликається з header-панелі, а не з меню.
- Після зміни `packing-tool/shared/` — обов'язково перезапустити
  `shopify-fulfillment-tool/scripts/sync_shared.py`, інакше
  `shopify-fulfillment-tool/shared/server_connection.py` не з'явиться.

**Error handling:** без змін по суті для шляху, що працює. Для шляху, що не
працює — поведінка стає *м'якшою*: замість `sys.exit`/`QApplication.quit()`
одразу, спочатку пропозиція виправити шлях; остаточний вихід — той самий
код, що й зараз, просто на крок пізніше.

## Порядок виконання

1. `shared/server_connection.py` в `packing-tool/shared/` (канонічне
   джерело) + self-check.
2. Підключити `packing-tool/src/profile_manager.py` і
   `packing-tool/src/main.py` (recovery-цикл + пункт меню), прогнати
   self-check і наявні тести (`tests/test_profile_manager.py`).
3. Запустити `shopify-fulfillment-tool/scripts/sync_shared.py`.
4. Підключити `shopify_tool/profile_manager.py` і
   `gui/main_window_pyside.py` (recovery-цикл) + нову кнопку в
   `gui/ui_manager.py`.
5. Прогнати наявні тести в `shopify-fulfillment-tool`
   (`tests/test_profile_manager.py`).

## Тестування / self-check

- `shared/server_connection.py::test_path_reachable` — assert-блок:
  існуюча тимчасова тека → `True`; неіснуючий/недоступний шлях (наприклад,
  файл замість теки) → `False`.
- `resolve_server_path` — assert-блок на три випадки: env var виставлено →
  повертає його незалежно від QSettings/fallback; env var не виставлено, є
  збережене значення в QSettings → повертає його; нічого не задано →
  повертає fallback. Для ізоляції від реального `QSettings` користувача —
  `QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, <temp dir>)`
  у самому self-check-блоці.
- `ConnectionSettingsDialog`/`prompt_for_recovery_path` — UI, без
  автоматичного тесту; перевіряється вручну (`run` skill) в обох
  застосунках: успішне підключення, невдале підключення → recovery-prompt
  → новий шлях → успіх.

## Відхилений варіант

**Застосування нового шляху одразу, без перезапуску.** Означало б безпечне
пересоздання `ProfileManager` і всього, що з нього побудовано
(`SessionLockManager`, `WorkerManager`, `StatsManager`,
`SessionHistoryManager`, `SessionRegistryManager` в packing-tool;
аналогічний набір у shopify-tool), плюс перевірку, що жодна сесія не
активна в момент зміни. Відхилено за прямим вибором користувача: простіше
й безпечніше — зберегти шлях і попросити перезапустити, як і зараз
задокументовано в `config.ini`/`config.ini.example`.
