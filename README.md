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

После `seed` проверь:

```bash
curl http://localhost:8000/api/v1/health/
curl http://localhost:8000/api/v1/specialists/
curl "http://localhost:8000/api/v1/doctors/?page=1&limit=10"
curl http://localhost:8000/api/v1/doctors/1/
curl http://localhost:8000/api/v1/doctors/1/calendar/
```

OTP DEV bypass:

```bash
curl -X POST http://localhost:8000/api/v1/auth/phone/verify-code/ \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+996700000000","code":"123456"}'
```

Ответ даст `access_token`. Его дальше можно использовать для `/bookings/*`.

---

## PROD-like запуск (Nginx -> Front + Back, как в примере)

Это режим, чтобы всё открывалось по **IP сервера**:

- Front: `http://<SERVER_IP>/`
- Swagger: `http://<SERVER_IP>/api/docs/`
- Admin: `http://<SERVER_IP>/admin/`
- API health: `http://<SERVER_IP>/api/v1/health/`

### Запуск

```bash
docker network create book_network  # один раз

cd book_back
cp .env.prod.example .env.prod

# обязательно добавь IP/домены в DJANGO_ALLOWED_HOSTS внутри .env.prod

docker compose -f docker-compose.prod.yml up -d --build
```

### Остановка

```bash
cd book_back
docker compose -f docker-compose.prod.yml down
```

