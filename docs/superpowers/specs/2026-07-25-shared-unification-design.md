# Уніфікація shared/ між Packing Tool та Shopify Fulfillment Tool

Date: 2026-07-25
Status: Approved (sub-project 1 of 2 — event/notification layer is a separate follow-up spec)

## Контекст

Аудит (ponytail-audit) знайшов, що `packing-tool/shared/` і
`shopify-fulfillment-tool/shared/` — це дві незалежні, розбіжні копії того
самого пакета, хоча `shared/README.md` в обох репо документує контракт
"обидва репозиторії повинні мати цей `shared/` з ідентичним вмістом" і сам
пропонує git submodule як рекомендований варіант — жоден варіант ніколи не
було реалізовано.

Розбіжності:
- `shared/stats_manager.py`: packing-tool — 379 рядків (тільки
  `record_packing`), shopify-fulfillment-tool — 757 рядків (повний набір:
  `record_analysis`, `record_packing`, `record_label_print`,
  `get_global_stats`, `get_client_stats`, `get_all_clients_stats`,
  `get_analysis_history`, `get_packing_history`, `get_label_print_history`,
  `get_label_stats`, `reset_stats`).
- Cross-platform file-lock (msvcrt/fcntl) винесений в окремий модуль
  `packing-tool/shared/file_lock.py`, але в shopify-tool той самий алгоритм
  продубльований inline в `stats_manager.py::_lock_file`.
- `FileLockError` — два різні класи з однаковим ім'ям (в packing-tool —
  підклас `Exception` з `file_lock.py`; в shopify-tool — підклас
  `StatsManagerError`, визначений прямо в `stats_manager.py`).
- Timestamps: packing-tool пише tz-aware через
  `shared.metadata_utils.get_current_timestamp()`; shopify-tool пише naive
  `datetime.now().isoformat()` — в ту саму спільну історію
  (`analysis_history`/`packing_history`) в `Stats/global_stats.json`.
- `_get_default_stats()["version"]`: `"1.3.0"` в packing-tool vs `"1.0"` в
  shopify-tool — залежить, який застосунок перший ініціалізував файл.
- `session_id`, що передається в `record_analysis`/`record_packing`, не
  гарантовано збігається: shopify-tool передає `Path(session_path).name`;
  packing-tool передає або `session_manager.session_id`, або ad hoc fallback
  `f"{current_session_path}_{current_packing_list}"`.
- `base_path` конфігурується двома різними механізмами: packing-tool читає
  `config.ini [Network] FileServerPath`; shopify-tool читає env var
  `FULFILLMENT_SERVER_PATH`. Немає єдиного джерела правди.
- `shared/atomic_write.py` і `shared/metadata_utils.py` існують лише в
  packing-tool і ніколи не використовуються в shopify-tool (0 звернень).

Обидва застосунки пишуть в один і той самий файл на мережевому сервері —
`Stats/global_stats.json` за адресою, що конфігурується окремо в кожному
застосунку. Це єдина точка "спільної роботи в рамках одного файлу" між
двома репозиторіями. Другий спільний канал — файлова система сесій
(`Sessions/<client>/...`): Shopify Tool створює сесію аналізу, Packing Tool
пізніше відкриває ту саму теку для пакування; прямого event/handshake між
застосунками немає (це предмет наступного спек-документа).

Runtime-топологія: Packing Tool і Shopify Tool можуть працювати як на
одному ПК, так і одночасно на різних ПК складу, з'єднаних лише через
мережевий файл-сервер (UNC-шлях). Це виключає рішення, що покладаються на
локальний IPC (сокет/named pipe) як єдиний канал — будь-яка синхронізація
має працювати через файловий сервер.

## Обсяг

У межах цього проєкту:
1. Об'єднати `stats_manager.py` в один канонічний файл (повний набір
   методів з shopify-форку, побудований на інфраструктурі з packing-tool).
2. Прибрати дублювання file-lock, atomic-write, timestamp-логіки.
3. Виправити 4 конкретні конфлікти: `version`-поле, tz-naive vs tz-aware
   timestamps, розбіжність `session_id`, розбіжність джерела `base_path`.
4. Налаштувати односторонню синхронізацію `shared/` без нового git-репо.

Поза обсягом (окремий, наступний спек): live-сповіщення між застосунками
(event/notification layer) поверх уніфікованого `shared/`.

Існуючий production `Stats/global_stats.json` з мішаними записами
(version 1.0/1.3.0, tz-naive/tz-aware) — власник заміняє його новим порожнім
файлом самостійно; міграція старих записів не потрібна (forward-fix only).

## Архітектура

**Канонічне джерело:** `packing-tool/shared/`. Причина: вже містить
правильну, самоперевірену інфраструктуру (`file_lock.py`, `atomic_write.py`,
`metadata_utils.py`), яку не варто переписувати. shopify-tool-форк має
повніший набір методів `StatsManager`, який переноситься в канонічну версію.

**Синхронізація:** без нового git-репо, без submodule. Новий скрипт
`shopify-fulfillment-tool/scripts/sync_shared.py` копіює
`../packing-tool/shared/` → `./shared/` (виключно `.py`/`.md`-файли, без
`__pycache__`), запускається вручну після кожної зміни `shared/` в
packing-tool, друкує список скопійованих файлів.

## Компоненти

**`shared/stats_manager.py`** (переписується):
- Повний набір методів з shopify-форку.
- Лок через `shared.file_lock.locked_file` (видаляється inline
  `_lock_file`).
- Timestamps через `shared.metadata_utils.get_current_timestamp()`
  (видаляються голі `datetime.now().isoformat()`).
- `_atomic_update` переноситься **без змін**: temp-file-then-read-back-
  into-the-locked-handle — навмисний вибір, не помилка. Просте
  temp+`os.replace()` (як в `atomic_write.py`) замінило б файл під локом,
  залишивши лок на відв'язаному inode, а новий файл — незаблокованим;
  вже покрито регресійним тестом
  `tests/test_atomic_write.py::test_stats_manager_atomic_update_is_actually_crash_safe`.
  Корекція попереднього дизайну: секція 2 спершу помилково пропонувала це
  спростити.
- Один `FileLockError`, реекспортований з `shared.file_lock` (друга
  дефініція класу видаляється).
- `_get_default_stats()["version"]` = `"2.0"` (єдине канонічне значення,
  явно відмінне від обох старих; це поле формату `Stats/global_stats.json`,
  не плутати з `shared/__init__.py::__version__` пакета).

**`shared/file_lock.py`, `shared/atomic_write.py`, `shared/metadata_utils.py`**
— без змін.

**`shared/worker_manager.py`** → переїжджає в `packing-tool/src/worker_manager.py`.
Ніколи не використовувався shopify-tool (не в його `shared/__init__.py`,
0 імпортів) — не є "спільним", тримати його в `shared/` вводить в оману.
`shared/__init__.py` більше не експортує `WorkerManager`/`WorkerProfile`;
`src/main.py` імпортує напряму з `src.worker_manager`.

**Новий `shared/session_id.py`** — одна функція
`derive_session_id(session_path) -> str` (`Path(session_path).name`).
Обидва застосунки викликають саме її замість власної ad hoc логіки.

## Дані / виклики, що змінюються

**base_path:** у `packing-tool/src/profile_manager.py` додається перевірка
env var `FULFILLMENT_SERVER_PATH` **першою** (та сама назва й пріоритет, що
вже в shopify-tool), з падінням назад на `config.ini [Network] FileServerPath`,
якщо змінна не задана. Існуючі розгортання на самому `config.ini`
продовжують працювати без змін.

**Виклики:**
- `packing-tool/src/main.py:1626-1629` — дворозгалужена логіка `_session_id`
  замінюється на `shared.session_id.derive_session_id(session_path)`.
- `shopify-fulfillment-tool/gui/actions_handler.py:234-238` —
  `Path(session_path).name` замінюється на той самий
  `shared.session_id.derive_session_id(...)`.
- `packing-tool/src/main.py` — імпорт `WorkerManager` змінюється з
  `shared.worker_manager` на `src.worker_manager`.
- Після запуску `sync_shared.py` — `shopify-fulfillment-tool/shared/`
  повністю замінюється копією з packing-tool (включно з новими для нього
  `file_lock.py`, `atomic_write.py`, `metadata_utils.py`, `session_id.py`).

**Error handling:** без змін по суті — виклики `stats_manager.*` в обох
застосунках вже обгорнуті в `try/except`, що не блокує основний потік при
збої запису; ця поведінка зберігається однаковою в обох, бо тепер це той
самий код.

## Порядок виконання

1. Побудувати канонічний `shared/` в packing-tool (переписаний
   `stats_manager.py`, перенесений `worker_manager.py`, новий
   `session_id.py`), оновити виклики в `packing-tool/src/`.
2. Прогнати self-check-и в packing-tool.
3. Написати й запустити `scripts/sync_shared.py` з
   shopify-fulfillment-tool — це і є перше застосування синхронізації,
   воно повністю замінює `shopify-fulfillment-tool/shared/` канонічною
   версією.
4. Оновити виклики в `shopify-fulfillment-tool/gui/` (session_id,
   base_path fallback), прогнати self-check-и там.

## Тестування / self-check

- `shared/stats_manager.py` — розширюється існуючий
  `if __name__ == "__main__":` self-check: `record_packing` +
  `record_analysis` у тимчасову теку, читання назад, перевірка
  `get_global_stats()`/`get_client_stats()` через assert.
- `shared/session_id.py` — тривіальний one-liner, тесту не потребує.
- `profile_manager.py` (env-var fallback) — короткий assert-блок: env var
  виставлено → повертає її; не виставлено → повертає значення з
  `config.ini`.
- `scripts/sync_shared.py` — після копіювання друкує список скопійованих
  файлів; окремого тесту для самого скрипта не потрібно.

## Відхилений варіант

Виправити 4 конфлікти "на місці", залишивши два незалежні форки
`stats_manager.py`. Відхилено: не усуває корінь проблеми (дублювання коду),
і той самий дрейф повториться щоразу, як хтось торкнеться
`stats_manager.py` лише в одному з репо.
