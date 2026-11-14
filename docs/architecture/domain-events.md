# Domain Events

> Status: planned

## Why

Decoupling modules. `OrderService.place()` should not know about the email service, analytics or inventory. It publishes `OrderPlaced`, and subscribers react independently.

Benefits:

- **Single responsibility**: a service does one thing
- **Open/closed**: new reactions are added by registering a new handler, without editing `OrderService`
- **Test-friendly**: `OrderService` is tested with `FakeEventBus.published`, without bringing up email/analytics

## Minimal bus

```python
# src/fastapi_ecommerce_api/core/events/base.py
@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: UUID = field(default_factory=uuid4)


# src/fastapi_ecommerce_api/core/events/bus.py
type Handler[E] = Callable[[E], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe[E: DomainEvent](self, event_type: type[E], handler: Handler[E]) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(type(event), [])
        # sequentially, logging errors: one failing handler does not break the others
        for h in handlers:
            try:
                await h(event)
            except Exception:
                log.exception(
                    "event.handler.failed",
                    event_type=type(event).__name__,
                    handler=h.__name__,
                )
```

## Events in modules

```python
# src/fastapi_ecommerce_api/modules/orders/events.py
@dataclass(frozen=True, kw_only=True)
class OrderPlaced(DomainEvent):
    order_id: UUID
    user_id: UUID
    total: Decimal
    items: tuple[OrderItemSnapshot, ...]


@dataclass(frozen=True, kw_only=True)
class OrderCancelled(DomainEvent):
    order_id: UUID
    reason: str
```

Events are **immutable** (`frozen=True`). They carry the **minimum data** subscribers need, not an ID plus a lazy load (a handler should not go to the DB for event details).

## Subscriber registration

At application startup (lifespan):

```python
# src/fastapi_ecommerce_api/main.py
async def register_event_handlers(bus: EventBus, deps: AppDeps) -> None:
    bus.subscribe(OrderPlaced, send_order_confirmation_email(deps.email))
    bus.subscribe(OrderPlaced, decrement_inventory(deps.inventory))
    bus.subscribe(OrderPlaced, track_analytics(deps.analytics))
    bus.subscribe(OrderCancelled, refund_payment(deps.payment))
```

Subscribers are usually closures that inject dependencies:

```python
def send_order_confirmation_email(email: EmailService) -> Handler[OrderPlaced]:
    async def handler(event: OrderPlaced) -> None:
        await email.send_confirmation(event.order_id)

    return handler
```

## Publishing: after commit

**Critical**: publish **after** the UoW commit succeeds, not inside the transaction. Otherwise a rollback leaves handlers with a phantom event.

```python
async def place_order(self, ...) -> Order:
    async with self._uow:
        order = await self._uow.orders.create(...)
        await self._uow.commit()
    # commit succeeded, now publish
    await self._events.publish(OrderPlaced(
        order_id=order.id,
        user_id=order.user_id,
        total=order.total,
        items=tuple(...),
    ))
    return order
```

## Evolution in production

When it becomes necessary, the migration path is:

1. **Outbox pattern**: the event is written to an `outbox` table in the same transaction; a separate worker reads it and sends it out. This guarantees at-least-once delivery
2. **External broker** (RabbitMQ, NATS, Kafka): replace the in-process `EventBus` with an adapter that has the same interface. Services and handlers do not change
3. **Event sourcing**: a separate architectural step, usually not needed; do not go there without a strong reason

For a small project, in-process is enough. The main point is that **the service already publishes events**, so moving to a broker does not require rewriting domain logic.

## Anti-patterns

- **Event as a command**: `SendEmailRequested` is not an event, it is a command. An event is a **fact about the past** (`OrderPlaced`), not a request for an action
- **Event with excess data**: an event should be self-contained, but not a dump of the whole model. Only what subscribers actually need
- **A handler's reaction changes state that triggers the same event**: infinite recursion. Domain events must not form a cycle
