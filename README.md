# Book backend (Django + DRF)

Это **новый** backend-проект (не kgloto). Инфра/структура взяты как основа из шаблона `DJANGO_TEMPLATE_ALL_IN_ONE.md`, но названия/контейнеры — свои.

## DEV запуск (Docker)

1) Создай сеть один раз:

```bash
docker network create book_network
```

2) Подними backend:

```bash
cd book_back
cp .env.dev.example .env.dev
docker compose up --build
```

> Важно: используй именно команду **`docker compose`** (Compose v2). Старый `docker-compose` (v1) на новых версиях Docker иногда падает.

Проверка:

```bash
curl http://localhost:8000/api/v1/health/
```

Админка:

```text
http://localhost:8000/admin/
login: admin
pass:  admin
```

Seed данные:

```bash
docker compose exec book-backend python manage.py seed
```

## Smoke-test (чтобы фронт потом подключился без боли)

После `seed` проверь (оба префикса работают всегда: `/api/v1` и `/v1`).
Теперь канонический ресурс — **professionals** (вместо doctors).

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/specialists
curl "http://localhost:8000/api/v1/professionals?page=1&limit=10"
curl http://localhost:8000/api/v1/professionals/1
curl http://localhost:8000/api/v1/professionals/1/calendar

curl http://localhost:8000/v1/health
curl http://localhost:8000/v1/specialists
curl "http://localhost:8000/v1/professionals?page=1&limit=10"
curl http://localhost:8000/v1/professionals/1
curl http://localhost:8000/v1/professionals/1/calendar
```

OTP DEV bypass (DEV окружение):

```bash
curl -X POST http://localhost:8000/api/v1/auth/send-otp \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+996700000000"}'

curl -X POST http://localhost:8000/api/v1/auth/verify-otp \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+996700000000","code":"123456"}'
```

Ответ даст `access_token`. Его дальше можно использовать для `/bookings/*`.

Пример создания записи:

```bash
TOKEN="<PASTE_ACCESS_TOKEN_HERE>"

curl -X POST http://localhost:8000/api/v1/bookings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"doctor_id":1,"date":"2026-05-20","time":"09:30","service_ids":[1]}'
```

Пример списка моих записей:

```bash
curl http://localhost:8000/api/v1/bookings/my \
  -H "Authorization: Bearer $TOKEN"
```

---

## Формат ошибок (важно для фронта)

**Все ошибки** приходят в одном формате:

```json
{
  "error": "snake_case_code",
  "message": "Сообщение на русском",
  "details": {}
}
```

### Основные error-коды (которые фронт должен обрабатывать)

**Общие (DRF/сервер):**
- `validation_error` (400) — невалидные входные данные (подробности в `details`)
- `not_authenticated` (401) — нет/неверный Bearer токен
- `forbidden` (403) — нет доступа
- `not_found` (404) — ресурс не найден
- `server_error` (500) — внутренняя ошибка

**OTP:**
- `invalid_phone` (400) — неверный формат телефона
- `invalid_code` (400) — неверный/просроченный код, `details.attempts_left`
- `too_many_requests` (429) — лимиты OTP, `details.retry_after`

**Bookings:**
- `slot_unavailable` (409) — слот занят/недоступен
- `patient_not_found` (400) — клиент не найден (редко, если токен не связан)
- `services_not_found` (400) — часть service_ids не принадлежит врачу/не найдена
- `date_in_past` (400) — дата записи в прошлом
- `cannot_cancel` (400) — нельзя отменить позже чем за 2 часа
- `cannot_review` (400) — отзыв можно оставить только после завершённого приёма (`booking.status=completed`)

---

## Поиск специалистов + фильтрация по специализациям

`GET /api/v1/professionals` поддерживает:

- `search` — поиск по ФИО и специализациям
- `specialist_id` — фильтр по одной специализации
- `specialist_ids` — фильтр по нескольким специализациям (CSV, например `1,7,10`)
- также можно передать повторяющийся параметр: `?specialist_id=1&specialist_id=7`

Примеры:

```bash
curl "http://localhost:8000/api/v1/professionals?search=Сурапбеков"
curl "http://localhost:8000/api/v1/professionals?specialist_id=7"
curl "http://localhost:8000/api/v1/professionals?specialist_ids=1,7"
curl "http://localhost:8000/api/v1/professionals?search=гинеколог&specialist_ids=1,7"
```

### Elasticsearch (опционально)

Поиск умеет работать через Elasticsearch с fallback на PostgreSQL (`icontains`), если ES недоступен.

ENV:

```env
ES_ENABLED=true
ES_URL=http://elasticsearch:9200
ES_DOCTORS_INDEX=mamadoc_doctors
ES_TIMEOUT_SECONDS=2
```

Индексация врачей:

```bash
docker compose exec book-backend python manage.py sync_doctors_es --recreate
```

---

## PROD-like запуск (Nginx -> Front + Back, как в примере)

Это режим, чтобы всё открывалось по **IP сервера**:

- Front: `http://<SERVER_IP>/`
- Swagger: `http://<SERVER_IP>/api/docs/` или `http://<SERVER_IP>/docs/`
- Admin: `http://<SERVER_IP>/admin/`
- API health: `http://<SERVER_IP>/api/v1/health/` и `http://<SERVER_IP>/v1/health/`

### Запуск

```bash
docker network create book_network  # один раз

cd book_back
cp .env.prod.example .env.prod

# обязательно добавь IP/домены в DJANGO_ALLOWED_HOSTS внутри .env.prod

docker compose -f docker-compose.prod.yml up -d --build
```

### SSL (Let’s Encrypt + Certbot внутри nginx)

Этот проект умеет сам выпускать сертификат Let’s Encrypt при старте nginx-контейнера.

**Требования:**
- DNS A-запись `iwork.operator.kg -> 185.194.218.133`
- Открыты порты 80 и 443

**В `.env.prod`:**
```env
DOMAIN=iwork.operator.kg
GET_CERTS=True
CERTBOT_EMAIL=jibek.cabirova@mail.ru
```

**После запуска** проверяй:
- https://iwork.operator.kg/ (front)
- https://iwork.operator.kg/api/docs/ (swagger)
- https://iwork.operator.kg/admin/ (admin)

### Как перезапускать контейнеры (prod)

Команды выполнять из `book_back/`:

```bash
# Посмотреть что запущено
docker compose -f docker-compose.prod.yml ps

# Перезапустить только backend
docker compose -f docker-compose.prod.yml restart backend

# Перезапустить только frontend
docker compose -f docker-compose.prod.yml restart frontend

# Перезапустить nginx (например после правок конфига)
docker compose -f docker-compose.prod.yml restart nginx

# Пересобрать и поднять всё заново
docker compose -f docker-compose.prod.yml up -d --build
```

Контейнеры:
- `book_frontend` — Next.js фронт
- `book_backend` — Django/DRF API
- `book_nginx` — reverse proxy + certbot
- `book_postgres` — база

---

## Таблица ошибок по endpoint (факт из OpenAPI /api/schema.json)

Все ошибки всегда в формате:

```json
{ "error": "...", "message": "...", "details": {} }
```

| method | path | status | error codes (examples) |
|---|---|---:|---|
| `POST` | `/api/v1/auth/send-otp/` | `400` | invalid_phone, validation_error |
| `POST` | `/api/v1/auth/send-otp/` | `429` | too_many_requests |
| `POST` | `/api/v1/auth/send-otp/` | `500` | server_error |
| `POST` | `/api/v1/auth/verify-otp/` | `400` | invalid_code, invalid_phone, validation_error |
| `POST` | `/api/v1/auth/verify-otp/` | `429` | too_many_requests |
| `POST` | `/api/v1/auth/verify-otp/` | `500` | server_error |
| `POST` | `/api/v1/bookings/` | `400` | date_in_past, patient_not_found, services_not_found, validation_error |
| `POST` | `/api/v1/bookings/` | `401` | not_authenticated |
| `POST` | `/api/v1/bookings/` | `403` | forbidden |
| `POST` | `/api/v1/bookings/` | `404` | not_found |
| `POST` | `/api/v1/bookings/` | `409` | slot_unavailable |
| `POST` | `/api/v1/bookings/` | `500` | server_error |
| `GET` | `/api/v1/bookings/my/` | `401` | not_authenticated |
| `GET` | `/api/v1/bookings/my/` | `403` | forbidden |
| `GET` | `/api/v1/bookings/my/` | `500` | server_error |
| `DELETE` | `/api/v1/bookings/{booking_id}/` | `400` | cannot_cancel, patient_not_found, validation_error |
| `DELETE` | `/api/v1/bookings/{booking_id}/` | `401` | not_authenticated |
| `DELETE` | `/api/v1/bookings/{booking_id}/` | `403` | forbidden |
| `DELETE` | `/api/v1/bookings/{booking_id}/` | `404` | not_found |
| `DELETE` | `/api/v1/bookings/{booking_id}/` | `500` | server_error |
| `GET` | `/api/v1/doctors/` | `400` | validation_error |
| `GET` | `/api/v1/doctors/` | `500` | server_error |
| `GET` | `/api/v1/doctors/{doctor_id}/` | `404` | not_found |
| `GET` | `/api/v1/doctors/{doctor_id}/` | `500` | server_error |
| `GET` | `/api/v1/doctors/{doctor_id}/calendar/` | `404` | not_found |
| `GET` | `/api/v1/doctors/{doctor_id}/calendar/` | `500` | server_error |
| `GET` | `/api/v1/doctors/{doctor_id}/reviews/` | `400` | validation_error |
| `GET` | `/api/v1/doctors/{doctor_id}/reviews/` | `404` | not_found |
| `GET` | `/api/v1/doctors/{doctor_id}/reviews/` | `500` | server_error |
| `POST` | `/api/v1/doctors/{doctor_id}/reviews/` | `400` | patient_not_found, validation_error |
| `POST` | `/api/v1/doctors/{doctor_id}/reviews/` | `401` | not_authenticated |
| `POST` | `/api/v1/doctors/{doctor_id}/reviews/` | `403` | forbidden |
| `POST` | `/api/v1/doctors/{doctor_id}/reviews/` | `404` | not_found |
| `POST` | `/api/v1/doctors/{doctor_id}/reviews/` | `500` | server_error |
| `GET` | `/api/v1/meta/phone-countries/` | `500` | server_error |
| `GET` | `/api/v1/specialists/` | `500` | server_error |

### Остановка

```bash
cd book_back
docker compose -f docker-compose.prod.yml down
```
