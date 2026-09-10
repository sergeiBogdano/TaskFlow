# TaskFlow — DevOps Infrastructure

> Практический DevOps-проект: Linux-инфраструктура, контейнеризация, reverse proxy, CI/CD и контроль доступа.

## О проекте

**TaskFlow** — внутреннее веб-приложение для управления задачами и рабочими процессами. Проект разворачивается на собственном Debian-сервере и используется как полноценный практический DevOps-полигон.

Цель проекта — не просто запустить приложение, а построить вокруг него воспроизводимую инфраструктуру: от Git и тестов до Docker, Nginx, PostgreSQL, автоматического deployment и security boundaries.

## Архитектура

```text
                    ┌──────────────────────┐
                    │        GitHub        │
                    │   Source + Actions   │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
                 ▼                           ▼
          ┌────────────┐              ┌────────────┐
          │    CI      │              │     CD     │
          │   pytest   │              │ deployment │
          └────────────┘              └─────┬──────┘
                                            │
                                            ▼
                                    ┌──────────────┐
                                    │   Edge VPS   │
                                    │    Nginx     │
                                    └──────┬───────┘
                                           │
                                      SSH tunnel
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────┐
│                     Debian Server                        │
│                                                          │
│  systemd ──► Docker Compose                              │
│                    │                                     │
│             ┌──────┴──────┐                              │
│             ▼             ▼                              │
│          Nginx         FastAPI                           │
│             │             │                              │
│             ▼             ▼                              │
│          React       PostgreSQL                          │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Поток deployment

```text
Developer
   │
   ▼
Git push → GitHub
   │
   ▼
CI: install → test → coverage
   │
   ├── fail → deployment не запускается
   │
   └── success
          │
          ▼
        CD
          │
          ▼
     Deployment host
          │
          ▼
   git fetch / reset
          │
          ▼
 Docker Compose build
          │
          ▼
 Docker Compose up -d
          │
          ▼
 Container check
```

## Технологии

| Слой | Технологии |
|---|---|
| OS | Debian GNU/Linux 13 |
| VCS | Git / GitHub |
| CI/CD | GitHub Actions |
| Containers | Docker / Docker Compose |
| Frontend | React / Vite |
| Backend | FastAPI / Python |
| Database | PostgreSQL 16 |
| Web server | Nginx |
| Service management | systemd |
| Transport | SSH reverse tunnel |
| Testing | pytest / coverage |

## Приложение

TaskFlow состоит из трёх основных runtime-компонентов:

```text
React frontend
      │
      ▼
Nginx
 ┌────┴─────┐
 ▼          ▼
Frontend   FastAPI
              │
              ▼
          PostgreSQL
```

Docker Compose изолирует сервисы и связывает их через внутреннюю Docker-сеть.

## Linux и модель доступа

Инфраструктура построена вокруг отдельных ролей пользователей:

- `debian` — административная работа и управление приложением;
- `sergei` — административная работа;
- `developer` — работа с кодом без административного доступа;
- `deploy` — ограниченная роль для автоматического deployment.

Для deployment используется принцип **least privilege**. `deploy` не является обычным администратором и не входит в Docker-группу. Для него разрешён только необходимый deployment entrypoint через точечное правило `sudo`.

Основная рабочая директория:

```text
/opt/company/
├── repositories/
├── environments/
├── logs/
├── backups/
├── scripts/
└── monitoring/
```

Структура заранее разделяет код, окружения, логи, резервные копии, automation и monitoring.

## CI

При изменениях в `main` и `develop` запускается GitHub Actions:

1. checkout;
2. Python 3.13;
3. установка зависимостей;
4. подготовка тестового окружения;
5. `pytest`;
6. coverage.

CI использует отдельную тестовую SQLite-базу и тестовые секреты. Production database в CI не используется.

## CD

Deployment запускается только после успешного CI для `main`.

На сервере deployment выполняет контролируемый сценарий:

```text
fetch origin
   ↓
checkout main
   ↓
check local changes
   ↓
.......
   ↓
check containers
```

Если рабочее дерево содержит неожиданные локальные изменения, deployment останавливается.


## Что уже сделано

- Debian host подготовлен для работы с приложением.
- Созданы пользователи, группы и модель доступа.
- Организована структура `/opt/company`.
- Репозиторий подключён к GitHub.
- TaskFlow контейнеризирован.
- Настроены React + FastAPI + PostgreSQL.
- Настроен Nginx routing.
- Создан edge VPS.
- Настроены постоянные SSH reverse tunnels через systemd.
- Настроены GitHub Actions CI/CD.
- Deployment вынесен в отдельный root-owned script.
- Проверены ограничения пользователя `deploy`.
- Проверена работоспособность полного production flow.

## Следующие этапы

```text
Current
  │
  ├── Backup
  ├── Restore testing
  ├── Monitoring
  ├── Centralized logging
  ├── Alerting
  ├── Rollback
  ├── HTTPS / domain
  └── Production hardening
```

Архитектура не считается завершённой: новые компоненты должны добавляться так, чтобы их можно было заменить или удалить без потери понимания системы.

## Ценность проекта

Проект демонстрирует практические навыки:

- Linux administration;
- users / groups / permissions / sudo;
- Git и GitHub;
- Docker и Compose;
- Nginx;
- PostgreSQL;
- SSH и systemd;
- CI/CD;
- deployment automation;
- security boundaries;
- эксплуатацию собственной инфраструктуры.

> Проект развивается постепенно: сначала базовая эксплуатация и deployment, затем backup, monitoring, recovery и дальнейшее hardening.
