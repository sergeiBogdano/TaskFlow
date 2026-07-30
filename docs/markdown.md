# TaskFlow-SEO — Полная документация проекта

> SEO-трекер для управления задачами, клиентами, дедлайнами и командой.
> Python 3.12 async, FastAPI, SQLAlchemy async, aiosqlite, APScheduler, Jinja2, Chart.js, Bootstrap 5 Dark.

---

## 📁 Структура проекта

```
taskflow-seo/
├── app/
│   ├── __init__.py
│   ├── main.py                          # Точка входа: запуск uvicorn
│   │
│   ├── core/                            # 🧠 Ядро приложения
│   │   ├── __init__.py
│   │   ├── config.py                    # Настройки (WEB_APP_SECRET, БД, таймзона, лог)
│   │   ├── database.py                  # SQLAlchemy async engine, init_db, миграции, сиды
│   │   ├── models.py                    # Все ORM-модели (9 таблиц)
│   │   ├── auth.py                      # PBKDF2 пароли, HMAC-SHA256 сессии, current_user
│   │   ├── permissions.py               # FEATURES словарь, DEFAULT_ROLES, has_feature()
│   │   ├── sse.py                       # Per-user asyncio.Queue для SSE-событий
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── timezone.py              # utc_now, parse_deadline, format_datetime
│   │       └── validators.py            # Валидаторы (url, email)
│   │
│   ├── services/                        # 📦 Бизнес-логика
│   │   ├── __init__.py
│   │   ├── task_service.py              # CRUD задач, фильтрация по user_id/role
│   │   ├── client_service.py            # CRUD клиентов, фильтрация по user_id/role
│   │   ├── user_service.py              # create/update/list/authenticate пользователей
│   │   ├── role_service.py              # CRUD ролей
│   │   ├── notification_service.py      # Генерация/список/чтение уведомлений
│   │   ├── activity_service.py          # Логирование действий + список
│   │   ├── reminder_service.py          # Напоминания по задачам
│   │   └── template_service.py          # Шаблоны чек-листов
│   │
│   ├── scheduler/                       # ⏰ Планировщик задач
│   │   ├── __init__.py
│   │   ├── scheduler.py                 # APScheduler: старт/стоп
│   │   └── jobs.py                      # Джобы: проверка дедлайнов, напоминания, повтор
│   │
│   └── web/                             # 🌐 Веб-слой (FastAPI + Jinja2)
│       ├── __init__.py
│       ├── app.py                       # FastAPI app, lifespan, Jinja2Templates, has_feature filter
│       ├── router.py                    # Основные роуты (~1457 строк) — страницы + API эндпоинты
│       ├── user_routes.py               # Auth, users, roles, comments, SSE (~241 строка)
│       ├── static/
│       │   ├── app.js                   # JS: модалки, чек-листы, комментарии, SSE, поиск
│       │   └── style.css                # Кастомные стили (sidebar, модалки)
│       └── templates/
│           ├── base.html                # Базовый шаблон: sidebar, onboarding, SSE, навигация
│           ├── login.html               # Форма входа (username + password)
│           ├── register.html            # Форма регистрации
│           ├── dashboard.html           # Статистика: графики Chart.js, топ клиентов
│           ├── tasks.html               # Список задач + модалка создания/редактирования
│           ├── kanban.html              # Доска: todo / in_progress / done / overdue
│           ├── calendar.html            # Календарь с дедлайнами, drag-n-drop
│           ├── clients.html             # Список клиентов + пагинация
│           ├── client_detail.html       # Детали клиента: задачи, графики, доступы
│           ├── reports.html             # Отчёты Chart.js: статусы, воронка, топ-10
│           ├── notifications.html       # Уведомления с сортировкой по типу
│           ├── activity.html            # Журнал действий
│           ├── settings.html            # Настройки: часовой пояс, шаблоны
│           ├── trash.html               # Корзина (soft-delete)
│           ├── users.html               # Управление пользователями + per-user права
│           └── roles.html               # Управление ролями и правами
│
├── taskflow.spec                        # PyInstaller spec для сборки exe
├── .env                                 # Переменные окружения
├── requirements.txt                     # Зависимости Python
├── README.md                            # Краткое описание
├── docker-compose.yml                   # Docker Compose
├── Dockerfile                           # Docker образ
└── launcher.py                          # Пускатель для frozen build
```

---

## 🗄️ Модели БД (`app/core/models.py`)

### User

| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer PK | |
| username | String(100) UNIQUE | Логин |
| email | String(200) nullable | Email |
| password_hash | String(200) | PBKDF2-HMAC-SHA256: `salt:hex` |
| role | String(20) default=manager | admin / manager / viewer |
| is_active | Boolean default=True | Блокировка входа |
| onboarding_done | Boolean default=False | Пройден ли тур |
| custom_permissions | JSON nullable | Per-user override прав (null = права роли) |
| created_at | DateTime | |

**Связи:** tasks_created (Task.created_by_id), tasks_assigned (Task.assigned_to_id), comments

### Task

| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer PK | |
| client_id | FK -> clients.id nullable | |
| created_by_id | FK -> users.id nullable | Автор задачи |
| assigned_to_id | FK -> users.id nullable | Исполнитель |
| title | String(200) | Название |
| task_type | String(50) default=custom | article/seo/dev/custom |
| notes | Text nullable | Заметка |
| comment | Text nullable | Комментарий (устаревшее) |
| deadline | DateTime nullable | Крайний срок |
| completion_date | DateTime nullable | Дата выполнения |
| status | String(20) default=todo | todo/in_progress/done/overdue |
| priority | String(10) default=medium | high/medium/low |
| checklist | JSON nullable | Массив {text, done, reminder?} |
| sort_order | Integer default=0 | Порядок в канбане |
| deleted_at | DateTime nullable | Soft-delete |
| recurring_interval | String(20) nullable | daily/weekly/monthly |
| recurring_count | Integer nullable | Сколько раз |
| recurring_remaining | Integer nullable | Осталось раз |
| recurring_parent_id | FK -> tasks.id nullable | Родительская задача (для повторения) |

**Связи:** client, creator, assignee, comments, attachments, reminders

### Client

| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer PK | |
| org_name | String(200) | Название организации |
| domain | String(100) UNIQUE nullable | Домен |
| contract_start | DateTime | Начало договора |
| contract_end | DateTime | Окончание договора |
| status | String(20) default=active | active/ending/expired |
| org_data | Text nullable | JSON с данными |
| accesses | JSON nullable | Массив доступов {title, url, login, password, notes} |
| created_by_id | FK -> users.id nullable | |
| deleted_at | DateTime nullable | Soft-delete |

### TaskComment

| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer PK | |
| task_id | FK -> tasks.id | |
| user_id | FK -> users.id nullable | Автор комментария |
| content | Text | Текст (поддерживает @mentions) |
| created_at | DateTime | |

### Notification

| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer PK | |
| task_id | FK -> tasks.id nullable | |
| client_id | FK -> clients.id nullable | |
| user_id | FK -> users.id nullable | Кому |
| notification_type | String(30) | overdue/deadline/checklist/comment/contract |
| title | String(300) | |
| message | Text nullable | |
| checklist_idx | Integer nullable | Для чек-лист напоминаний |
| read | Boolean default=False | |
| trigger_at | DateTime nullable | |

### Role

| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer PK | |
| name | String(100) UNIQUE | Название роли |
| description | String(500) nullable | |
| permissions | JSON nullable | Словарь {feature: bool} |
| is_system | Boolean default=False | Системные роли нельзя удалить |
| created_at | DateTime | |

### Другие модели

- **FileAttachment** — файлы, прикреплённые к задаче (хранятся в БД как LargeBinary)
- **ActivityLog** — лог действий (entity_type/entity_id, action, summary, user)
- **UserSettings** — настройки пользователя (timezone, calendar_view_mode)
- **Reminder** — напоминания (task_id, client_id, trigger_at, sent)

---

## 🔐 Аутентификация и авторизация (`app/core/auth.py`)

### Схема работы

```
Client → POST /login (username + password)
           ↓
    authenticate() — get_user_by_username() + verify_password()
           ↓
    make_session_token(user_id) → HMAC-SHA256(str(user_id), WEB_APP_SECRET)
           ↓
    Set-Cookie: taskflow_user=id:hex_sig (HttpOnly, Max-Age=30 дней, Path=/, SameSite=lax)

Client → любой запрос с Cookie
           ↓
    current_user(request) → request.cookies → verify_session_token()
           ↓                    ↓
    get_user(user_id)  ←  int(user_id) if HMAC valid
           ↓
    User object (None если inactive/не найден)
```

### Функции

| Функция | Описание |
|---------|----------|
| `hash_password(password)` | PBKDF2-HMAC-SHA256, salt 16 байт, 100k итераций → `salt:hex` |
| `verify_password(password, stored)` | Проверка пароля (constant-time сравнение) |
| `make_session_token(user_id)` | `user_id:HMAC-SHA256(user_id, WEB_APP_SECRET)` |
| `verify_session_token(token)` | Проверка HMAC, возвращает user_id или None |
| `get_current_user(request)` | Полный разбор куки → User объект (с проверкой is_active) |
| `require_user(request)` | То же, но исключение если нет |

### Проверка is_active

- `authenticate()` — блокирует вход если `is_active=False`
- `current_user()` / `_current_user()` — не возвращает пользователя если `is_active=False`
- `_ensure_admin()` в database.py — при старте реактивирует admin если выключен

---

## 🛡️ Права доступа (`app/core/permissions.py`)

### Список фич (FEATURES)

```python
FEATURES = {
    'tasks':          'Задачи — просмотр списка',
    'tasks_create':   'Задачи — создание',
    'tasks_edit':     'Задачи — редактирование любых',
    'tasks_delete':   'Задачи — удаление',
    'tasks_assign':   'Задачи — назначение исполнителя',
    'clients':        'Клиенты — просмотр',
    'clients_create': 'Клиенты — создание',
    'clients_edit':   'Клиенты — редактирование',
    'clients_delete': 'Клиенты — удаление',
    'reports':        'Отчёты',
    'calendar':       'Календарь',
    'kanban':         'Канбан',
    'activity':       'Аудит',
    'trash':          'Корзина',
    'templates':      'Шаблоны — просмотр',
    'templates_create':'Шаблоны — создание',
    'export':         'Экспорт PDF',
    'settings':       'Настройки',
    'users':          'Пользователи (admin)',
}
```

### Системные роли (DEFAULT_ROLES)

| Фича | admin | manager | viewer |
|------|-------|---------|--------|
| tasks | ✅ | ✅ | ✅ |
| tasks_create | ✅ | ✅ | ❌ |
| tasks_edit | ✅ | ✅ | ❌ |
| tasks_delete | ✅ | ✅ | ❌ |
| tasks_assign | ✅ | ✅ | ❌ |
| clients | ✅ | ✅ | ✅ |
| clients_create | ✅ | ✅ | ❌ |
| clients_edit | ✅ | ✅ | ❌ |
| clients_delete | ✅ | ✅ | ❌ |
| reports | ✅ | ✅ | ❌ |
| calendar | ✅ | ✅ | ✅ |
| kanban | ✅ | ✅ | ✅ |
| activity | ✅ | ✅ | ✅ |
| trash | ✅ | ✅ | ❌ |
| templates | ✅ | ✅ | ❌ |
| templates_create | ✅ | ✅ | ❌ |
| export | ✅ | ✅ | ❌ |
| settings | ✅ | ✅ | ❌ |
| users | ✅ | ❌ | ❌ |

### Per-user override

У каждого пользователя есть поле `custom_permissions` (JSON).
Если заполнено — права из этого поля имеют приоритет над правами роли.

```
has_feature(user, feature):
  1. Если user.role == 'admin' → True
  2. Если user.custom_permissions[feature] существует → вернуть его значение
  3. Иначе → DEFAULT_ROLES[user.role][feature] (или False)
```

### Jinja2 фильтр

В шаблонах: `{% if user|has_feature('tasks') %} ... {% endif %}`

---

## 🚀 Маршруты (HTTP API)

### Страницы (HTML)

| Метод | Путь | Шаблон | Описание |
|-------|------|--------|----------|
| GET | `/` | dashboard.html | Дашборд со статистикой |
| GET | `/login` | login.html | Форма входа |
| POST | `/login` | — | Аутентификация |
| GET | `/register` | register.html | Форма регистрации |
| POST | `/register` | — | Создать пользователя (role=manager) |
| GET | `/logout` | — | Удалить куку |
| GET | `/tasks` | tasks.html | Список задач |
| POST | `/tasks/create` | — | Создать задачу (FormData) |
| POST | `/tasks/{id}/edit` | — | Редактировать задачу (FormData) |
| POST | `/tasks/{id}/done` | — | Отметить выполненной |
| GET | `/kanban` | kanban.html | Канбан-доска |
| GET | `/calendar` | calendar.html | Календарь |
| GET | `/clients` | clients.html | Список клиентов (с пагинацией) |
| GET | `/clients/{id}` | client_detail.html | Детали клиента |
| GET | `/reports` | reports.html | Отчёты |
| GET | `/notifications` | notifications.html | Уведомления |
| GET | `/activity` | activity.html | Аудит |
| GET | `/settings` | settings.html | Настройки |
| GET | `/trash` | trash.html | Корзина |
| GET | `/users` | users.html | Управление пользователями (admin) |
| GET | `/roles` | roles.html | Управление ролями (admin) |
| GET | `/tasks/{id}/print` | — | PDF-версия задачи для печати |
| GET | `/clients/{id}/print` | — | PDF-версия клиента для печати |

### API задач

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/tasks` | Список задач (JSON) |
| GET | `/api/tasks/all` | Все задачи с доп. полями (для модалки) |
| POST | `/api/tasks/{id}/move` | Переместить на канбане (drag-n-drop) |
| POST | `/api/tasks/batch` | Batch-операции (статус, удаление) |
| POST | `/api/tasks/{id}/start` | Начать задачу → in_progress |
| POST | `/api/tasks/{id}/delete` | Soft-delete |
| POST | `/api/tasks/{id}/restore` | Восстановить из корзины |
| POST | `/api/tasks/{id}/hard-delete` | Полное удаление |
| POST | `/api/tasks/{id}/upload` | Загрузить файлы |
| POST | `/api/tasks/{id}/generate-next` | Создать следующую повторяющуюся |
| GET | `/api/tasks/{id}/comments` | Комментарии задачи |
| POST | `/api/tasks/{id}/comments` | Добавить комментарий (FormData: content) |
| GET | `/api/tasks/calendar` | Задачи для календаря (start/end) |
| PATCH | `/api/tasks/update` | Обновить поля задачи (JSON) |

### API клиентов

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/clients` | Список клиентов (JSON) |
| POST | `/api/clients/create` | Создать клиента (FormData) |
| POST | `/api/clients/{id}/edit` | Редактировать клиента (FormData) |
| POST | `/api/clients/{id}/delete` | Soft-delete |
| POST | `/api/clients/{id}/restore` | Восстановить |
| POST | `/api/clients/{id}/hard-delete` | Полное удаление |

### API пользователей и ролей

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/users/me` | Текущий пользователь (id, username, role, onboarding_done, custom_permissions) |
| GET | `/api/users` | Список всех пользователей (admin) |
| POST | `/api/users/create` | Создать пользователя (FormData, admin) |
| POST | `/api/users/{id}/update` | Обновить пользователя (FormData, admin) |
| GET | `/api/roles` | Список ролей (admin) |
| POST | `/api/roles/create` | Создать роль (FormData, admin) |
| POST | `/api/roles/{id}/update` | Обновить роль (FormData: name, description, permissions JSON) |
| POST | `/api/roles/{id}/delete` | Удалить роль (admin, системные нельзя) |
| POST | `/api/onboarding/done` | Отметить онбординг пройденным |

### Прочие API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/sse` | Server-Sent Events (live-уведомления) |
| GET | `/api/search?q=...` | Глобальный поиск задач и клиентов |
| GET | `/api/reports/data?months=N` | Данные для отчётов (Chart.js) |
| GET | `/api/notifications` | Список уведомлений |
| GET | `/api/notifications/unread-count` | Кол-во непрочитанных |
| POST | `/api/notifications/{id}/read` | Отметить прочитанным |
| POST | `/api/notifications/read-all` | Всё прочитано |
| POST | `/api/notifications/{id}/dismiss` | Удалить уведомление |
| POST | `/api/notifications/dismiss-all-read` | Удалить все прочитанные |
| GET | `/api/activity` | Лог действий |
| GET | `/api/settings` | Настройки (JSON) |
| POST | `/api/settings/update` | Обновить настройки |
| GET | `/api/task-templates` | Шаблоны задач (JSON) |
| POST | `/api/task-templates/save` | Сохранить шаблон |
| GET | `/api/files/{id}/download` | Скачать файл |
| POST | `/api/checklist/{id}/update` | Обновить пункт чек-листа |
| GET | `/api/tasks/export?client_id=X` | Экспорт задач в CSV |

---

## 🔄 Server-Sent Events (SSE) — `app/core/sse.py`

```
Client → GET /api/sse (с Cookie)
           ↓
    register_queue(user_id) → asyncio.Queue
           ↓
    StreamingResponse(event_stream())
           ↓
    каждые 30с: keepalive (timeout → ': keepalive\n\n')
           ↓
    события:
      event: notification_new\n
      data: {"id":1,"title":"...","type":"comment","message":"..."}\n\n
      ---
      event: comment_new\n
      data: {"task_id":1,"author":"admin","content":"..."}\n\n

При отключении: unregister_queue() → удаляем очередь
```

Используется в `base.html`:
```javascript
const es = new EventSource('/api/sse');
es.addEventListener('notification_new', function(e) { ... });
es.addEventListener('comment_new', function(e) { showToast('Новый комментарий'); });
```

---

## ⏰ Планировщик (`app/scheduler/`)

### Джобы (выполняются каждую минуту)

1. **Проверка дедлайнов** — задачи с `deadline < now` и `status != done` → создаёт уведомления `overdue`
2. **Напоминания чек-листов** — пункты с `reminder` и без `done` → уведомления `checklist`
3. **Повторяющиеся задачи** — `recurring_remaining > 0` → создаёт копию задачи
4. **Заканчивающиеся договоры** — `contract_end` в ближайшие 30 дней → уведомления `contract`

Использует APScheduler с интервалом 60 секунд.

---

## 🗄️ База данных

- **Движок:** SQLite + aiosqlite (async)
- **URL:** `sqlite+aiosqlite:///%APPDATA%/TaskFlow/data/taskflow.db`
- **Миграции:** ALTER TABLE в `_migrate()` — добавляет колонки, игнорируя ошибки если колонка уже есть
- **init_db:**
  1. `Base.metadata.create_all` — создаёт таблицы если нет
  2. `_migrate()` — добавляет новые колонки
  3. `_ensure_admin()` — создаёт admin:admin если пользователей нет; реактивирует admin если выключен
  4. `_ensure_roles()` — создаёт 3 системные роли (admin, manager, viewer) если их нет

---

## 📊 Графики и визуализация

- **Chart.js** (CDN) — используются на дашборде, отчётах, странице клиента
- **Типы графиков:** bar, doughnut, line
- **Дашборд:** статусы (doughnut), активность за 14 дней (line), топ-10 клиентов (bar)
- **Отчёты:** статус распределение, воронка выполнения (месяцы), топ-10 клиентов по задачам
- **Клиент детально:** статусы задач клиента + количество за месяц

---

## 🔧 Переменные окружения (`.env`)

```env
WEB_APP_SECRET=taskflow_secret_2026    # Секрет для HMAC-токенов
DEFAULT_TIMEZONE=Europe/Moscow          # Часовой пояс по умолчанию
LOG_LEVEL=INFO                          # Уровень логирования
```

---

## 📦 Сборка (PyInstaller)

Файл `taskflow.spec` собирает приложение в один exe:

```powershell
pyinstaller taskflow.spec
```

Выход: `dist/TaskFlow-SEO.exe` (включает все шаблоны, статику и зависимости).

`launcher.py` — пускатель, который:
1. Определяет путь к БД (`%APPDATA%/TaskFlow/data/taskflow.db`)
2. Распаковывает шаблоны/статику из `_internal/resources/`
3. Запускает uvicorn
4. Открывает браузер на `http://127.0.0.1:8080`

---

## 🐳 Docker

```yaml
services:
  web:
    build: .
    ports: "8080:8080"
    environment:
      - WEB_APP_SECRET=taskflow_secret_2026
      - DEFAULT_TIMEZONE=Europe/Moscow
    volumes:
      - taskflow_data:/app/data
```

---

## 👥 Роли пользователей (система прав)

### Создание и управление

- **Admin** (создаётся автоматически при первом запуске) — логин `admin`, пароль `admin`
- **Обычная регистрация** (`/register`) — создаёт пользователя с ролью `manager`
- **Через админку** (`/users`) — admin создаёт пользователей с любой ролью + per-user права
- **Роли** (`/roles`) — admin создаёт/редактирует/удаляет кастомные роли с любым набором прав

### Изоляция данных

```
list_tasks(user):     admin → все, иначе → (created_by_id=id OR assigned_to_id=id)
list_clients(user):   admin → все, иначе → (created_by_id=id)
```

### Защита admin

- Admin (id=1) нельзя отключить через UI — `api_update_user` возвращает ошибку
- `_ensure_admin()` при старте реактивирует admin если `is_active=False`
- Admin всегда имеет все права (bypass проверок)

---

## 💬 Комментарии и @mentions

- Комментарии привязываются к задаче (`TaskComment`)
- При добавлении комментария парсятся `@username` упоминания
- Для каждого упоминания (кроме автора) создаётся `Notification` и отправляется SSE-событие
- Также SSE-событие отправляется создателю задачи и исполнителю

---

## 🧪 Тестирование

```powershell
# pytest (если установлен)
pytest

# Ручное тестирование через curl/PowerShell
$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-WebRequest -Uri "http://127.0.0.1:8080/login" -Method POST `
  -Body @{username='admin';password='admin'} -WebSession $s
Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/tasks" -WebSession $s
```

---

## 🚀 Быстрый старт

```powershell
# 1. Активировать venv
.\venv\Scripts\Activate.ps1

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Запустить
$env:WEB_APP_SECRET="taskflow_secret_2026"
$env:PYTHONPATH="C:\Dashboard\TG\taskflow-seo"
python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8080

# 4. Открыть браузер
start http://127.0.0.1:8080
# Логин: admin / пароль: admin
```

---

## ❗ Известные проблемы

1. **Dashboard 500 в PowerShell тестах** — через браузер работает. Проблема с передачей cookie через `:`
2. **`POST /api/users/create` только FormData** — не принимает JSON
3. **SSE не тестируется в автотестах** — только в браузере
4. **Миграции игнорируют ошибки** — если колонка уже существует, просто pass
5. **NotificationService не фильтрует по user_id** — все уведомления видны всем (запланировано)
6. **ActivityLog не фильтрует по user** — все действия видны всем
