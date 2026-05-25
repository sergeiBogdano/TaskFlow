# TaskFlow-SEO

Личная система управления задачами, контентом и напоминаниями для SEO/веб-специалиста.

## Быстрый старт

### Локальный запуск

```bash
cp .env.example .env
# Отредактируйте .env — укажите BOT_TOKEN

pip install -r requirements.txt
python app/main.py
```

### Запуск через Docker

```bash
cp .env.example .env
# Отредактируйте .env — укажите BOT_TOKEN

docker-compose up -d
```

## Команды Telegram-бота

- `/start` — приветствие
- `/help` — справка
- `/add [текст] [#теги] [~дедлайн]` — быстрая задача
- `/list [фильтр]` — просмотр задач
- `/done [id]` — отметить выполненной
- `/snooze [id] [время]` — отложить
- `/note [id] [текст]` — добавить заметку
- `/new_client` — новый проект
- `/articles [домен]` — пакет статей
- `/settings` — настройки

## Структура проекта

```
app/
├── main.py              # Точка входа
├── core/                # Ядро: конфиг, БД, модели, утилиты
├── services/            # Бизнес-логика
├── bot/                 # Telegram-бот
├── scheduler/           # Планировщик напоминаний
├── web/                 # Веб-интерфейс (v2.0)
templates/               # JSON-шаблоны проектов
data/                    # SQLite БД
logs/                    # Логи
```
