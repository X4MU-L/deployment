---
name: python-fastapi-repository-port
description: Use when introducing or refactoring a persistence boundary in a Python FastAPI/SQLAlchemy app: repository interfaces, domain records, SQL adapters, query methods, transaction behavior, and repository tests.
---

# Python Repository Port

## Purpose

Add a clean persistence boundary so services depend on a domain-specific interface instead of SQLAlchemy details.

Use this when:

- A service needs database reads/writes.
- SQL queries are leaking into endpoints or services.
- You need fake repositories for deterministic service tests.
- You are adding a model and want a stable access pattern.

## First Questions

- Which service or workflow consumes this repository?
- What exact operations does the service need?
- What should the repository return: dataclass record, Pydantic DTO, ORM model, or primitive?
- Who owns commits: repository method, unit of work, or request transaction middleware?
- Does the repository need soft-delete filtering, ownership filtering, or ordering?
- Which queries need indexes or uniqueness constraints?

## Interface Shape

Prefer business-oriented methods over generic CRUD:

```python
class InvoiceRepository(ABC):
    @abstractmethod
    def create_pending(self, customer_id: str, amount_cents: int) -> InvoiceRecord:
        raise NotImplementedError

    @abstractmethod
    def get_open_by_customer(self, customer_id: str) -> list[InvoiceRecord]:
        raise NotImplementedError
```

Good method names encode intent:

- `get_active_by_id`
- `list_by_owner`
- `mark_disconnected`
- `reserve_name`
- `append_event`
- `find_conflict`

## Record Shape

Use an immutable-ish record/dataclass to decouple services from ORM state:

```python
@dataclass(frozen=True)
class InvoiceRecord:
    invoice_id: str
    customer_id: str
    amount_cents: int
    status: str
```

Include fields the service needs. Do not mirror every database column automatically.

## SQLAlchemy Adapter

Typical structure:

```python
class SQLInvoiceRepository(InvoiceRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_pending(self, customer_id: str, amount_cents: int) -> InvoiceRecord:
        row = Invoice(...)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return self._to_record(row)

    @staticmethod
    def _to_record(row: Invoice) -> InvoiceRecord:
        return InvoiceRecord(...)
```

Follow the local project’s transaction convention. If no convention exists, keep mutating repository methods small and commit there.

## Query Guidelines

- Use `select(Model).where(...)` with SQLAlchemy 2 style.
- Filter soft-deleted rows by default unless the method says otherwise.
- Apply ownership filters in repository methods when they are persistence-level invariants.
- Use deterministic ordering for list methods.
- Return `None` for not found; let the service decide whether that is an error.
- Catch database integrity errors only when you can translate them into a meaningful domain conflict.

## Factory and DI

Expose a small factory when the project uses function-based DI:

```python
def resolve(session: Session) -> InvoiceRepository:
    return SQLInvoiceRepository(session)
```

Then wire it in the central dependency module:

```python
def get_invoice_repository(session: DbSession) -> InvoiceRepository:
    return invoice_repository.resolve(session)
```

## Tests

Use service fakes for business logic and SQL integration tests for repository behavior.

Repository tests should cover:

- Insert and fetch.
- Not found.
- Ownership/status filtering.
- Ordering.
- Constraint behavior.
- Soft delete or state transitions.

Keep fake repositories simple dictionaries of records. They should implement the interface methods the service uses, not SQL details.
