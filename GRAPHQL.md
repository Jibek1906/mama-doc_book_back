# GraphQL API (MamaDoc Booking)

Этот проект имеет **два параллельных слоя API**:

1) **REST (DRF)** — текущие endpoints, которые использует фронт (Swagger: `/api/docs/`).
2) **GraphQL (Strawberry)** — дополнительный endpoint `/graphql/`.

GraphQL добавлен так, чтобы **не ломать** существующие REST endpoints.

---

## URL

```text
POST https://iwork.operator.kg/graphql/
```

В dev (когда `DEBUG=1`) доступен GraphiQL по этому же URL в браузере.

---

## Формат запроса

GraphQL запрос отправляется JSON-ом:

```http
POST /graphql/
Content-Type: application/json

{"query":"{ health }"}
```

Пример curl:

```bash
curl -k -X POST https://iwork.operator.kg/graphql/ \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ health }"}'
```

---

## Авторизация

### 1) JWT как в REST (для клиента)

Если нужно выполнять действия от имени клиента (например `myBookings`, booking flow),
используется стандартный заголовок:

```http
Authorization: Bearer <access_token>
```

Токен получается тем же способом, что и в REST (OTP verify).

### 2) Service-token для бота (админ-доступ)

Чтобы бот мог выполнять **админские mutations** (CRUD специалистов/врачей/филиалов/услуг/расписания и т.д.),
используется отдельный сервисный токен:

```http
X-BOT-TOKEN: <BOT_GRAPHQL_TOKEN>
```

Токен на сервере задаётся через env:

```env
BOT_GRAPHQL_TOKEN=<long-random-secret>
```

> Важно: админские mutations также разрешены staff-пользователям (`is_staff=True`) при JWT авторизации.

---

## Ошибки (совместимо с REST)

Стандартный GraphQL формат ошибок:

```json
{ "data": null, "errors": [ ... ] }
```

В проекте добавлен совместимый слой как в REST: `extensions.rest`:

```json
{
  "data": null,
  "errors": [
    {
      "message": "Не авторизован",
      "extensions": {
        "error": "not_authenticated",
        "message": "Не авторизован",
        "details": {}
      }
    }
  ],
  "extensions": {
    "rest": {
      "error": "not_authenticated",
      "message": "Не авторизован",
      "details": {}
    }
  }
}
```

То есть клиент/бот может обрабатывать ошибки **так же, как REST**: `error/message/details`.

---

## Основные Query

### health

```graphql
query { health }
```

### specialists

```graphql
query {
  specialists {
    id
    title
    slug
    description
    iconUrl
    isActive
    sortOrder
  }
}
```

### organizations / branches

```graphql
query {
  organizations {
    id
    name
    slug
    paylinkEnabled
    branches { id title address slug paylinkEnabled paylinkAmount }
  }
}
```

### professionals (фильтрация)

```graphql
query {
  professionals(search: "Иван", branchId: 1, specialistId: 2) {
    id
    fullName
    slug
    rating
    experienceYears
    specialties
    branches { id address organization { id name } }
    services { id name price durationMin }
  }
}
```

### calendar / slots

Аналог REST:
`GET /api/v1/professionals/{id}/calendar`.

```graphql
query {
  professionalCalendar(professionalId: 1, days: 7)
}
```

Ответ — JSON массив дней:
`[{date,label,is_available,slots_count,times[]}, ...]`.

Список стартов под конкретную длительность:

```graphql
query {
  professionalAvailableTimes(professionalId: 1, date: "2026-06-10", durationMin: 60)
}
```

---

## Booking flow (Mutations)

### createPaylink

```graphql
mutation {
  createPaylink(branchId: 1) {
    ok
    error
    message
    details
    data { paymentIntentId transactionId amount paylinkUrl }
  }
}
```

### createBooking

```graphql
mutation {
  createBooking(
    professionalId: 1,
    date: "2026-06-10",
    time: "09:30",
    serviceIds: [1],
    branchId: 1,
    paymentIntentId: 123
  ) {
    ok
    error
    message
    details
    data { id confirmationCode date time totalPrice status }
  }
}
```

### cancelBooking

```graphql
mutation { cancelBooking(bookingId: 10) { ok error message details } }
```

---

## Admin/Bot mutations (требуют X-BOT-TOKEN или staff JWT)

### Specialists

Создать:

```graphql
mutation {
  adminCreateSpecialist(title: "Новая специализация") { id title slug isActive }
}
```

Обновить:

```graphql
mutation {
  adminUpdateSpecialist(id: 34, isActive: false) { id title isActive }
}
```

### Professionals

Создать:

```graphql
mutation {
  adminCreateProfessional(fullName: "Иванов Иван", branchIds: [1]) { id fullName slug isActive }
}
```

Обновить:

```graphql
mutation {
  adminUpdateProfessional(id: 1, isActive: false) { id fullName isActive }
}
```

Назначить специализации:

```graphql
mutation {
  adminSetProfessionalSpecialties(
    professionalId: 1,
    specialistIds: [1,2],
    primarySpecialistId: 1
  ) { id fullName specialties }
}
```

Назначить услуги:

```graphql
mutation {
  adminSetProfessionalServices(professionalId: 1, serviceIds: [1,2,3]) {
    id fullName services { id name }
  }
}
```

### Расписание

Заменить недельный график:

```graphql
mutation {
  adminSetProfessionalWeekSchedule(
    professionalId: 1,
    items: [
      { dayOfWeek: 0, isWorking: true, startTime: "09:00", endTime: "18:00" },
      { dayOfWeek: 1, isWorking: true, startTime: "09:00", endTime: "18:00" },
      { dayOfWeek: 2, isWorking: false }
    ]
  ) { ok error message details }
}
```

Добавить исключение:

```graphql
mutation {
  adminAddProfessionalException(professionalId: 1, date: "2026-06-10", isDayOff: true, reason: "Отпуск") {
    id date isDayOff reason
  }
}
```

Удалить исключение:

```graphql
mutation { adminDeleteProfessionalException(exceptionId: 123) { ok message } }
```

---

## Admin: Organizations / Branches / Services (MVP для управления проектом)

### Организации

Создать организацию:

```graphql
mutation {
  adminCreateOrganization(name: "Новая организация") {
    id name slug isActive paylinkEnabled
  }
}
```

Обновить организацию:

```graphql
mutation {
  adminUpdateOrganization(id: 1, paylinkEnabled: false, isActive: true) {
    id name paylinkEnabled isActive
  }
}
```

### Филиалы (Branch)

Создать филиал (включая Paylink настройки + список специализаций филиала):

```graphql
mutation {
  adminCreateBranch(
    organizationId: 1,
    title: "Филиал #1",
    address: "Бишкек, ул. ...",
    paylinkEnabled: true,
    paylinkAmount: 500,
    specialistIds: [1, 2]
  ) {
    id title address slug isActive paylinkEnabled paylinkAmount
    specialists { id title }
  }
}
```

Обновить филиал:

```graphql
mutation {
  adminUpdateBranch(
    id: 1,
    paylinkEnabled: false,
    paylinkAmount: 0,
    specialistIds: [1]
  ) {
    id title paylinkEnabled paylinkAmount specialists { id title }
  }
}
```

Недельный график филиала:

```graphql
mutation {
  adminSetBranchWeekSchedule(
    branchId: 1,
    items: [
      { dayOfWeek: 0, isWorking: true, startTime: "09:00", endTime: "18:00", breakStart: "12:00", breakEnd: "13:00" },
      { dayOfWeek: 1, isWorking: true, startTime: "09:00", endTime: "18:00" },
      { dayOfWeek: 2, isWorking: false }
    ]
  ) { ok error message details }
}
```

### Услуги (Service)

Создать услугу и привязать к профессионалам:

```graphql
mutation {
  adminCreateService(
    name: "Консультация",
    price: 1000,
    durationMin: 60,
    professionalIds: [1,2]
  ) {
    id name price durationMin isActive
  }
}
```

Обновить услугу:

```graphql
mutation {
  adminUpdateService(id: 1, price: 1200, isActive: true) {
    id name price isActive
  }
}
```

---

## Admin: bookings для бота (создание/отмена/перенос без JWT клиента)

Эти операции нужны боту, чтобы работать с записью **от имени клиента**, без прохождения OTP.

### Создать запись для клиента

```graphql
mutation {
  adminCreateBookingForClient(
    clientPhone: "+996700123456",
    clientFullName: "Иван Иванов",
    professionalId: 1,
    date: "2026-06-10",
    time: "09:30",
    serviceIds: [1],
    branchId: 1,
    # если в филиале включена бронь/депозит, но нужно создать запись без оплаты
    skipPaymentRequirement: true
  ) {
    ok
    error
    message
    details
    data { id confirmationCode date time totalPrice status organizationId branchId }
  }
}
```

### Отменить запись (любую) по id

```graphql
mutation {
  adminCancelBooking(bookingId: 123, reason: "Клиент попросил отменить") {
    ok error message details
  }
}
```

### Перенести запись

```graphql
mutation {
  adminRescheduleBooking(bookingId: 123, date: "2026-06-12", time: "11:00", skipPaymentRequirement: true) {
    ok error message details
  }
}
```

Можно также менять professional/branch/services:

```graphql
mutation {
  adminRescheduleBooking(
    bookingId: 123,
    professionalId: 2,
    branchId: 3,
    serviceIds: [5,6],
    date: "2026-06-12",
    time: "11:00"
  ) { ok error message details }
}
```

### Поиск записей

```graphql
query {
  adminBookings(clientPhone: "+996700123456", date: "2026-06-10", limit: 20) {
    id
    status
    bookingDate
    bookingTime
    clientPhone
    professionalName
    branchId
    organizationId
  }
}
```

---

## Где смотреть реализацию

- Схема: `book_back/app/api/graphql_schema.py`
- JWT auth для GraphQL: `book_back/app/api/graphql_auth.py`
- Service-token для бота: `book_back/app/api/graphql_bot_auth.py`
- REST-like ошибки: `book_back/app/api/graphql_extensions.py`
- Django view: `book_back/app/api/graphql_view.py`
