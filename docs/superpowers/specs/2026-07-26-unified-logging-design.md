# Уніфікація логування (Packing Tool та Shopify Fulfillment Tool)

Date: 2026-07-26
Status: Approved

## Контекст

Обидва застосунки мають повністю незалежні, написані з нуля системи
логування, які ніколи не мали спільного коду:

- **packing-tool** (`src/logger.py`): singleton `AppLogger`, лениво
  ініціалізується при першому виклику `get_logger(__name__)`.
  `TimedRotatingFileHandler` (ротація опівночі, `backupCount` =
  `LogRetentionDays` з `config.ini`, за замовчуванням 30), JSON-формат.
  Пише в `\\...\0UFulfilment\Logs\packing_tool\packing_tool.log` — це
  **один спільний файл**, у який пишуть усі ПК складу одночасно.
- **shopify-fulfillment-tool** (`shopify_tool/logger_config.py`): окрема
  функція `setup_logging()`, інший JSON-формат (додає `client_id`/
  `session_id`), `RotatingFileHandler` (ротація по 10MB, 30 backup-файлів).

Розбіжності й конкретні проблеми, знайдені під час аналізу:

1. **Централізоване логування shopify-tool ніколи не досягає файл-сервера.**
   `shopify_tool/__init__.py:12` викликає `setup_logging()` без аргументів
   під час імпорту пакета — `server_base_path=None`, тобто JSON-логи
   пишуться в локальну `./logs/` (відносно поточної робочої директорії), а
   не на сервер. `ProfileManager.get_logs_path()` (`profile_manager.py:1821`)
   існує, але не викликається **ніде** в кодовій базі — мертвий код.
   Окремо, `gui/main_window_pyside.py::setup_logging` (рядок 260) вішає
   `QtLogHandler` на root-логер лише для відображення в UI ("Execution
   Log") — це працює, тому проблема з файловим логуванням непомітна під
   час звичайного використання.
2. **Ризик пошкодження при одночасному записі кількох ПК в один файл.**
   Жоден з двох `Handler`-ів не використовує файлові локи. `RotatingFileHandler`/
   `TimedRotatingFileHandler` кожного процесу вирішує про ротацію незалежно
   — якщо два ПК одночасно потраплять у момент ротації спільного файлу на
   мережевому диску (SMB), можливі втрачені рядки або `PermissionError` при
   перейменуванні файлу, яким у цей момент користується інший процес. Для
   packing-tool цей ризик реальний вже зараз (файл дійсно спільний і
   дійсно на сервері); для shopify-tool він поки що прихований проблемою
   №1 (файл локальний, тому спільного доступу немає, але й
   централізованого логу теж немає).
3. **Консольний handler — мертвий код у production-збірці.** Обидва
   застосунки збираються через `pyinstaller --onefile --windowed`
   (`packing-tool/main.spec:46` — `console=False`;
   `shopify-fulfillment-tool/.github/workflows/build_release.yml:64` —
   `--windowed`). У такій збірці `sys.stdout`/`sys.stderr` дорівнюють
   `None`. `logging.StreamHandler()` без аргументів фіксує `sys.stderr` у
   момент створення; якщо це `None`, кожен виклик `emit()` мовчки
   провалюється (`Handler.handleError` не пише нічого, якщо
   `sys.stderr` теж `None`) — тобто в реальному production EXE консольний
   handler ніколи нічого нікуди не пише, а лише витрачає час на кожен
   виклик логера.
4. **`extra=` контекстні поля втрачаються в packing-tool.**
   `src/session_lock_manager.py` викликає логер з
   `extra={"client_id": ..., "session_dir": ...}` — Python `logging`
   записує кожен ключ як окремий атрибут `LogRecord` напряму
   (`record.client_id`, `record.session_dir`), а не як єдиний
   `record.extra_data`. `StructuredJSONFormatter.format()`
   (`src/logger.py:80`) перевіряє саме `hasattr(record, 'extra_data')` —
   цей атрибут ніколи не встановлюється настправжніми викликами `extra=`,
   тому `client_id`/`session_dir` мовчки зникають із JSON-логу. У
   shopify-tool є аналогічний, але невикористаний намір —
   `log_with_context()` (`logger_config.py:123`) з тим самим `extra=`
   механізмом; 0 викликів у всій кодовій базі — мертвий код.
5. **Логер сам по собі не узгоджений з `ProfileManager`.**
   `AppLogger._setup_logging()` читає `config.ini [Network] FileServerPath`
   напряму через власний `_load_config()` — незалежно від
   `ProfileManager`, який після
   `docs/superpowers/specs/2026-07-25-shared-unification-design.md` (Task 5)
   вже враховує пріоритет `FULFILLMENT_SERVER_PATH` (env var) і
   `docs/superpowers/specs/2026-07-26-server-connection-settings-design.md`
   (збережений через UI шлях). Якщо користувач змінить шлях через env var
   або через Server Connection UI, `ProfileManager` перейде на новий шлях,
   а логер — ні: дані підуть в один каталог, логи — в інший.
6. **Обсяг викликів логування:** packing-tool — 452 виклики (168 `info`,
   109 `error`, 94 `warning`, 80 `debug`, 1 `exception`);
   shopify-fulfillment-tool — 696 викликів (284 `info`, 150 `warning`,
   137 `error`, 117 `debug`, 8 `exception`). З 109 `error`-викликів у
   packing-tool лише один випадок у всьому застосунку фіксує traceback
   (`logger.exception`/`exc_info=True`) — здебільшого причина збою не
   потрапляє в лог-файл, лише текст повідомлення.

Топологія виконання та сама, що й у попередніх спек-документах: Packing
Tool і Shopify Tool можуть працювати як на одному ПК, так і одночасно на
різних ПК складу, з'єднаних лише через мережевий файл-сервер (UNC-шлях).

## Обсяг

У межах цього проєкту:

1. Новий канонічний модуль `shared/logger.py` з єдиною точкою входу
   `setup_logging(tool_name, base_path, level=logging.INFO,
   retention_days=30)`, що конфігурує root-логер — усі існуючі виклики
   `logging.getLogger(__name__)` / `logging.getLogger("ShopifyToolLogger")`
   в обох застосунках продовжують працювати без змін.
2. **Лог-файл на процес, без локів**: кожен процес пише у власний файл
   `Logs/<tool_name>/<tool_name>_<hostname>_<pid>.log`. Ротація за днем
   (`TimedRotatingFileHandler`, оскільки застосунки можуть працювати кілька
   днів поспіль). Локи не потрібні — у файла завжди рівно один писар.
3. Незалежне **прибирання застарілих файлів** (best-effort, за `mtime`) —
   заміна `backupCount`, який в моделі "файл на процес" більше не має
   довгоживучого власника, що сам себе чистить.
4. Консольний handler підключається, лише якщо `sys.stderr is not None`
   (розробка/`run_dev.py`) — ніколи в упакованому `--windowed` EXE.
5. Виправлення виклику налаштування в shopify-tool: замість
   eager-виклику при імпорті пакета (`shopify_tool/__init__.py:12`,
   `server_base_path=None`) — явний виклик одразу після того, як
   `ProfileManager` резолвить справжній `base_path`.
6. Новий JSON-формат, спільний для обох застосунків: зберігає всі поля з
   обох існуючих форматів (`timestamp`, `level`, `tool`, `module`,
   `function`, `line`, `message`, `exc_info`) і **коректно** захоплює
   довільні `extra=`-поля (виправляє проблему №4 — генерична перевірка
   "яких атрибутів немає у стандартному `LogRecord`", а не хардкод
   неіснуючого `extra_data`).
7. `shared.logger.setup_logging()` викликається з кожного застосунку
   з `ProfileManager.__init__`, одразу після того, як `self.base_path`
   визначено — це ж усуває розбіжність №5 (логер і дані завжди дивляться
   на той самий сервер).
8. Аудит контенту існуючих викликів логування (обидва застосунки, в межах
   цього ж проєкту, за вибором користувача) — не повне ручне
   перечитування ~1150 викликів, а конкретні, автоматизовані перевірки:
   - `logger.error(...)` всередині `except`-блоку без `exc_info=True` /
     `logger.exception(...)` → додати захоплення traceback;
   - викликів "голого" `logging.<рівень>(...)` замість логера модуля
     (1 місце в shopify-tool);
   - видалення мертвого коду: `log_with_context()`
     (`logger_config.py`), `AppLogger`/`get_logger()` (`src/logger.py`),
     `_load_config()` дублювання читання `config.ini` в логері.
9. `packing-tool/src/logger.py` та
   `shopify-fulfillment-tool/shopify_tool/logger_config.py` видаляються
   повністю; 16 викликів `from logger import get_logger` у
   `packing-tool/src/` замінюються на голий stdlib
   `logging.getLogger(__name__)` (сам `setup_logging()` більше не
   потребує lazy-singleton тригера — він викликається явно один раз).

Поза обсягом:

- Повний ручний перегляд формулювань/змісту кожного з ~1150 існуючих
  викликів логування — аудит обмежений конкретними перевірками з пункту 8.
- Будь-які зміни в `QtLogHandler`/`gui/log_viewer.py` (відображення логу в
  UI) — це залишається специфічним для UI кожного застосунку, не спільним.
- `shared/file_lock.py`, `shared/stats_manager.py` — окрема підсистема,
  вже уніфікована попереднім проєктом; ця робота її не торкається.
- Міграція/видалення старих лог-файлів — вони природно застаріють і
  будуть прибрані новим механізмом очищення (forward-fix only, той самий
  підхід, що й заміна `Stats/global_stats.json` в попередньому проєкті).
- UI для зміни рівня логування через Settings — використовується env var
  (за аналогією з `FULFILLMENT_SERVER_PATH`), без нового діалогу.

## Архітектура

**Канонічне джерело:** `packing-tool/shared/logger.py`, синхронізується в
`shopify-fulfillment-tool/shared/` через існуючий
`shopify-fulfillment-tool/scripts/sync_shared.py` — без змін самого
скрипта, він і так копіює всі `.py`-файли з `shared/`.

**Формат файлу:** `Logs/<tool_name>/<tool_name>_<hostname>_<pid>.log`, де
`hostname` = `socket.gethostname()`, `pid` = `os.getpid()`. Ротація —
`TimedRotatingFileHandler(when="midnight", backupCount=retention_days)` →
рotated-файли отримують суфікс дати автоматично
(`..._1234.log.2026-07-25`). Оскільки ім'я файлу унікальне на процес,
конкуруючого писаря немає в принципі — жодних файлових локів не потрібно
(на відміну від `StatsManager`, де один файл дійсно ділять усі процеси).

**Очищення застарілих файлів:** `backupCount` у
`TimedRotatingFileHandler` прибирає лише ротації, створені *цим самим*
handler-ом у межах *цього самого* процесу — файл, залишений процесом, що
вже завершився, ніхто більше не ротує і не видаляє. Тому
`setup_logging()` додатково запускає `_sweep_old_logs(log_dir,
retention_days)`: перебирає всі файли в `log_dir`, видаляє ті, чий
`mtime` старший за `retention_days` діб, ігноруючи `OSError`/
`PermissionError` для окремого файлу (може бути відкритий іншим ще живим
процесом — Windows не дасть його видалити, і це нормально, спробуємо
знову при наступному запуску).

**Резолюція `base_path`/`level` лишається за кожним застосунком** (як і
для `StatsManager`/`server_connection` раніше) — `shared/logger.py`
лише споживає вже готові значення:
- `base_path`: `ProfileManager.base_path` в обох застосунках (уже
  уніфікований ланцюжок env var → UI → config.ini/production-шлях).
- `level`: packing-tool — `config.ini [Logging] LogLevel` (без змін);
  shopify-tool — новий env var `FULFILLMENT_LOG_LEVEL` (той самий
  принцип, що й `FULFILLMENT_SERVER_PATH`), fallback `INFO`.

## Компоненти

**`shared/logger.py`** (новий файл):

- `UnifiedJSONFormatter(logging.Formatter)` — об'єднує обидва існуючі
  формати. Стандартні поля: `timestamp`, `level`, `tool` (переданий у
  `setup_logging`), `module`, `function`, `line`, `message`, `exc_info`
  (якщо є). Додатково: обчислює множину стандартних атрибутів
  порожнього `LogRecord` один раз при імпорті модуля, і будь-який
  атрибут запису, якого немає в цій множині (тобто прийшов через
  `extra={...}`), кладе в `log_data['extra']` — так `client_id`,
  `session_id`, `session_dir`, `worker_id` тощо коректно потрапляють у
  файл незалежно від застосунку, без хардкоду конкретних імен полів
  (виправляє проблему №4 з розділу "Контекст").
- `_sweep_old_logs(log_dir: Path, retention_days: int) -> None` —
  описано вище.
- `setup_logging(tool_name: str, base_path: str, level: int =
  logging.INFO, retention_days: int = 30) -> None`:
  1. `log_dir = Path(base_path) / "Logs" / tool_name`; `mkdir(parents=True,
     exist_ok=True)` в `try/except` — при помилці fallback на
     `Path.home() / f".{tool_name.lower()}" / "logs"` (та сама логіка,
     що вже є в `packing-tool/src/logger.py:182-188`, перенесена без
     змін поведінки).
  2. Ім'я файлу: `f"{tool_name}_{socket.gethostname()}_{os.getpid()}.log"`.
  3. `TimedRotatingFileHandler` (див. "Архітектура") +
     `UnifiedJSONFormatter(tool_name)`.
  4. Консольний `StreamHandler`, **лише якщо** `sys.stderr is not None`
     — людський формат (`asctime | name | levelname | funcName:lineno |
     message`), як зараз у packing-tool.
  5. `root_logger.setLevel(level)`, додати обидва (або один) handler-и.
  6. Викликати `_sweep_old_logs(log_dir, retention_days)`.
  7. Один інформаційний рядок-роздільник у лог, як зараз
     (`"=" * 80`, назва інструменту, рівень, шлях до файлу) — зберігається
     для зручності читання логів вручну.

**Виклики, що видаляються:**
- `packing-tool/src/logger.py` — видаляється повністю (`AppLogger`,
  `StructuredJSONFormatter`, `get_logger()`).
- `shopify-fulfillment-tool/shopify_tool/logger_config.py` — видаляється
  повністю (`JSONFormatter`, `setup_logging()`, `log_with_context()` —
  останній підтверджено мертвий, 0 викликів поза власним визначенням).

## Дані / виклики, що змінюються

- `packing-tool/src/profile_manager.py:95-100` (`self.base_path = ...`,
  `self.logs_dir = self.base_path / "Logs"`) — одразу після цього блоку
  додається виклик `shared.logger.setup_logging("PackingTool",
  str(self.base_path), level=log_level, retention_days=retention_days)`,
  де `log_level`/`retention_days` читаються з `self.config` (`[Logging]
  LogLevel`/`LogRetentionDays`, ті ж fallback-и, що зараз у
  `src/logger.py`). Це відбувається **до** перевірки
  `test_path_reachable` (рядки 114-127) — якщо сервер недоступний,
  `setup_logging()` сам впаде назад на локальний каталог (див.
  "Компоненти"), і `logger.error("File server not accessible...")` на
  рядку 120 вперше в історії цього застосунку потрапить у файл, а не
  тільки на екран/у консоль.
- `packing-tool/src/main.py:35,54` — `from logger import get_logger` /
  `logger = get_logger(__name__)` замінюються на `import logging` /
  `logger = logging.getLogger(__name__)`. Те саме в решті 16 файлів, що
  імпортують `from logger import get_logger`
  (`profile_manager.py`, `packer_logic.py`, `session_lock_manager.py`,
  `session_manager.py`, `session_selector.py`,
  `session_history_manager.py`, `session_registry_manager.py`,
  `restore_session_dialog.py`, `async_state_writer.py`,
  `sku_mapping_dialog.py`, `session_browser/session_browser_widget.py`,
  `session_browser/client_selector_widget.py`,
  `session_browser/orders_tab.py`,
  `session_browser/sessions_list_widget.py`,
  `session_browser/session_details_dialog.py` — 16 файлів разом з
  `main.py`).
  Рядок `logger.info("Initializing ProfileManager...")`
  (`profile_manager.py:69`) виконується до виклику `setup_logging()` у
  цьому ж методі — цей єдиний рядок піде тільки в
  lastResort-handler/консоль при першому запуску процесу; свідомо
  прийнятна втрата (немає бази даних, куди його персистентно писати, до
  моменту, поки `base_path` не визначено).
- `shopify-fulfillment-tool/shopify_tool/__init__.py:9,12` — імпорт і
  виклик `setup_logging()` видаляються (більше нема eager-виклику при
  імпорті пакета).
- `shopify-fulfillment-tool/shopify_tool/profile_manager.py::_get_base_path`
  — одразу після резолюції `self.base_path` додається виклик
  `shared.logger.setup_logging("ShopifyTool", str(self.base_path),
  level=log_level, retention_days=30)`, де `log_level` — з нового env var
  `FULFILLMENT_LOG_LEVEL` (fallback `INFO`).
- `shopify-fulfillment-tool/gui/main_window_pyside.py:271-272` —
  `logging.getLogger().addHandler(self.log_handler)` лишається (це
  окремий UI-handler, не входить у спільний модуль), але рядок
  `logging.getLogger().setLevel(logging.INFO)` видаляється — рівень
  root-логера тепер повністю належить `shared.logger.setup_logging()`,
  і цей виклик інакше міг би тихо перезаписати `DEBUG`, виставлений через
  `FULFILLMENT_LOG_LEVEL`, назад на `INFO`.
- `packing-tool/src/session_lock_manager.py` — виклики з `extra={...}`
  (рядки 101, 111, 124, 151, 163, 194, 201, 216) лишаються без змін коду
  — вони вже писали правильний `extra=`, просто формат раніше його не
  читав; тепер `UnifiedJSONFormatter` підхопить ці поля автоматично.

**Error handling:** без концептуальних змін — `setup_logging()` сам
ловить помилки створення каталогу на сервері (fallback на локальний
каталог, як і зараз); жоден виклик логера в застосунках не обгортається
в try/except (логування не повинно ламати основний потік, як і зараз).

## Порядок виконання

1. `shared/logger.py` у `packing-tool/shared/` (канонічне джерело) +
   self-check.
2. Підключити `packing-tool/src/profile_manager.py` (виклик
   `setup_logging`), видалити `src/logger.py`, замінити 16 імпортів на
   голий `logging.getLogger(__name__)`, прогнати наявні тести.
3. Аудит (пункт 8 "Обсягу") у packing-tool: `exc_info=True`/
   `logger.exception` для `error()`-викликів в `except`-блоках без
   traceback.
4. Запустити `shopify-fulfillment-tool/scripts/sync_shared.py`.
5. Підключити `shopify_tool/profile_manager.py` (виклик
   `setup_logging`), прибрати eager-виклик у `shopify_tool/__init__.py`,
   видалити `logger_config.py`, прибрати
   `logging.getLogger().setLevel(logging.INFO)` в
   `main_window_pyside.py`.
6. Аудит (пункт 8) у shopify-fulfillment-tool: те саме для `error()` +
   голий `logging.<рівень>()` виклик.
7. Наскрізна перевірка на спільному dev-сервері: обидва застосунки
   одночасно, підтвердити окремі файли на процес, відсутність помилок
   ротації/локів.

## Тестування / self-check

- `shared/logger.py` — `if __name__ == "__main__":` self-check у
  тимчасовій теці (`tmp_path`-стиль): виклик `setup_logging()` двічі з
  різними `pid` (замокати `os.getpid`) → два різні файли; запис через
  `extra={"client_id": "X"}` → перевірити, що поле `"client_id"` є в
  JSON-рядку файлу; `_sweep_old_logs` → створити файл зі старим `mtime`
  (через `os.utime`) → перевірити, що видалено, і файл зі свіжим `mtime`
  → перевірити, що лишився.
- Консольний handler: assert, що при
  `sys.stderr = None` (замокати) `setup_logging()` не додає
  `StreamHandler` до root-логера.
- `packing-tool/tests/test_profile_manager.py` — новий тест: після
  `ProfileManager(config_path)` перевірити, що `Logs/PackingTool/`
  містить рівно один файл з очікуваним ім'ям (`PackingTool_<hostname>_<pid>.log`).
- shopify-fulfillment-tool: тестів немає (per `CLAUDE.md`), верифікація —
  `ruff check .` + `CI=1 python run_dev.py` (як і в попередніх проєктах).

## Відхилений варіант

**Один спільний файл на інструмент + файлові локи
(`shared/file_lock.py`) навколо кожного запису.** Відхилено: на відміну
від `StatsManager`, де запис відбувається рідко (раз на сесію), логування
відбувається сотні разів за сеанс роботи — лок над мережевим SMB-шляхом
на кожен виклик логера означав би мережевий round-trip на кожен рядок
логу, з реальним ризиком підвисання UI, якщо виклик логера
трапляється в основному потоці (а він трапляється — логування не
винесене у фоновий потік у жодному з застосунків). Модель "файл на
процес" усуває саму потребу в локах, а не намагається зробити конкуренцію
безпечною.
