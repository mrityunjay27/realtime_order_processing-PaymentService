# Payment Service

Handles payment processing for the Realtime Order Processing System. This service processes payment requests from the Order Service, simulates a payment gateway (80% success / 20% failure), and publishes success or failure events back to complete the order lifecycle.

## What It Does

- **Processes payments** when `payments.requested` events arrive
- **Simulates a payment gateway** with 80% success rate (for testing both paths)
- **Publishes events** to Kafka via the transactional outbox pattern
- **Exposes read-only API** for viewing payment records
- **Integrates with the saga pattern** to trigger compensation on failure

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Payment Service (:8002)                      │
├─────────────────────────────────────────────────────────────┤
│  Web API (DRF)  │  Kafka Consumer  │  Outbox Publisher      │
│       │         │        │         │        │                │
│       ▼         │        ▼         │        ▼                │
│  PaymentService │  EventHandlers  │  OutboxService         │
│       │         │        │         │        │                │
│       ▼         │        ▼         │        ▼                │
│  OutboxEvent ───────────────────────────────────────────────│
│  EventHistory │  ProcessedEvents (idempotency)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Kafka (payments.requested, payments.succeeded, payments.failed)
```

## How to Start

### Prerequisites
- Python 3.12+
- PostgreSQL (via Docker)
- Kafka infrastructure (via Docker)

### 1. Start Dependencies

```bash
# Start Kafka infrastructure (from project root)
cd infra && docker compose up -d

# Start PostgreSQL for this service
cd payment_service && docker compose up -d
```

### 2. Setup Environment

```bash
cd payment_service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run Migrations

```bash
python manage.py migrate
```

### 4. Start the Service

**Option A: All processes via honcho (recommended)**
```bash
honcho start
```
This starts three processes: web (API), consumer (Kafka), publisher (outbox).

**Option B: Individual processes**
```bash
# Terminal 1: Web API
python manage.py runserver 0.0.0.0:8002

# Terminal 2: Kafka Consumer
python manage.py consume_events

# Terminal 3: Outbox Publisher
python manage.py publish_outbox
```

**Option C: VS Code Launch Configs**
Use the provided launch configurations for debugging.

## Dependencies on Other Services

| Dependency | Type | Purpose |
|------------|------|---------|
| **Order Service** | Kafka producer | Sends `payments.requested` events to process payments |
| **Order Service** | Kafka consumer | Receives `payments.succeeded` and `payments.failed` events |
| **Kafka** | Message broker | Asynchronous communication |
| **PostgreSQL** | Database | Persistent storage for payments, events |
| **Grafana/Loki** | Observability | Log aggregation and monitoring |

### Event Flow

1. **Consumes** `payments.requested` → Processes payment (simulated gateway)
2. **Publishes** `payments.succeeded` → Order Service (80% success rate)
3. **Publishes** `payments.failed` → Order Service (20% failure rate)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/payments/` | List all payments |
| `GET` | `/api/payments/{id}/` | Get payment details |

**Note:** Payments are read-only via API. They are only created by the Kafka consumer when processing payment requests.

### List Payments Example

```bash
curl http://127.0.0.1:8002/api/payments/
```

## What Happens When It Reacts

### On `payments.requested` (process payment)
- Creates a `Payment` record with status `PENDING`
- **80% success rate**: 
  - Generates a transaction reference (UUID)
  - Updates status to `SUCCESS`
  - Publishes `payments.succeeded` with transaction details
- **20% failure rate**:
  - Updates status to `FAILED`
  - Publishes `payments.failed` with reason `PAYMENT_DECLINED`
- **Database error**: Raises `RetryableEventException` → routes to retry topic

### Payment Gateway Simulation
The payment gateway is simulated using `random.random() < 0.8`:
- 80% of payments succeed (simulates normal operation)
- 20% of payments fail (triggers compensation saga in Order Service)

This allows testing both the happy path and the compensation path without external dependencies.

## Models

| Model | Purpose |
|-------|---------|
| `Payment` | Payment record (order_id, amount, status, transaction_reference) |
| `ProcessedEvent` | Idempotency tracking |
| `OutboxEvent` | Transactional outbox for Kafka publishing |
| `EventHistory` | Audit ledger for event lifecycle |

### Payment Statuses

| Status | Description |
|--------|-------------|
| `PENDING` | Payment created, processing in progress |
| `SUCCESS` | Payment completed successfully |
| `FAILED` | Payment declined or failed |

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgres://...` | PostgreSQL connection |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `SERVICE_NAME` | `payment-service` | Service identifier in logs |

## Directory Structure

```
payment_service/
├── config/                     # Django settings, URLs, WSGI
├── core/logging/               # JSON logging infrastructure
│   ├── config.py               # Logging configuration
│   ├── context.py              # contextvars for correlation IDs
│   ├── filters.py              # ContextFilter, HealthCheckFilter
│   ├── formatter.py            # JsonFormatter
│   └── middleware.py           # CorrelationMiddleware
├── payments/
│   ├── api/                    # DRF views, serializers, URLs
│   ├── events/
│   │   ├── audit/              # EventHistory ledger
│   │   ├── event_envelope.py   # Message contract
│   │   ├── payment_events.py   # Topic constants
│   │   ├── idempotency.py      # ProcessedEvent check/mark
│   │   ├── kafka_consumer.py   # Event handlers
│   │   ├── kafka_publisher.py  # Direct publisher (legacy)
│   │   ├── exceptions.py       # Retryable/NonRetryable
│   │   ├── retry_policy.py     # MAX_RETRIES = 3
│   │   ├── retry_publisher.py  # *.retry producer
│   │   ├── dlq_publisher.py    # *.dlq producer
│   │   ├── failure_handler.py  # Retry/DLQ routing
│   │   └── outbox_service.py   # Outbox CRUD
│   ├── management/commands/
│   │   ├── consume_events.py   # Start Kafka consumer
│   │   └── publish_outbox.py   # Outbox publisher
│   ├── models/                 # Payment, etc.
│   └── services/
│       └── payment_service.py  # Business logic
├── logs/                       # Structured JSON logs
├── Procfile                    # Process definitions
├── docker-compose.yml          # PostgreSQL container
├── Dockerfile                  # Container image
└── requirements.txt            # Python dependencies
```

## Testing

```bash
python manage.py test
```

Tests cover:
- Payment processing logic
- Success/failure paths
- Event publishing
- Idempotency checks
- Error handling

## Monitoring

Logs are written to `logs/application.log` in JSON format and aggregated by Grafana Alloy → Loki → Grafana.

Filter logs by correlation ID:
```
{service="payment-service"} |= "<correlation-id>"
```