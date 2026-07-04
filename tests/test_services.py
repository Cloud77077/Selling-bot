from decimal import Decimal
import pytest
from sqlalchemy.orm import sessionmaker
from shared.database import Base, engine_from_url
from shared.models import DeliverableCode, OrderStatus, Product, User
from shared.services import create_order, confirm_payment, next_order_number, unique_upi_amount, StockUnavailable

@pytest.fixture
def db():
    engine = engine_from_url('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with Session() as s:
        yield s

def product(db, codes=('A',)):
    p = Product(name='P', price=Decimal('100.00'), description='d')
    db.add(p); db.flush()
    db.add_all([DeliverableCode(product_id=p.id, code=c) for c in codes]); db.flush()
    return p

def test_order_number_generation(db):
    p = product(db); o = create_order(db, p.id, None); db.flush()
    assert o.order_number.startswith('ORD-')
    assert next_order_number(db).endswith('0002')

def test_unique_amount_generation(db):
    p = product(db, ('A','B'))
    first = create_order(db, p.id, None)
    second = create_order(db, p.id, None)
    assert first.payment_amount != second.payment_amount
    assert Decimal(str(first.payment_amount)) > Decimal('100.00')

def test_stock_deduction_atomic_assignment(db):
    p = product(db, ('CODE1',))
    o = create_order(db, p.id, None)
    confirm_payment(db, o.id)
    assert o.status == OrderStatus.fulfilled
    assert o.delivered_code == 'CODE1'
    assert db.query(DeliverableCode).filter_by(is_sold=False).count() == 0

def test_confirm_payment_when_stock_unavailable(db):
    p = product(db, ())
    o = create_order(db, p.id, None)
    with pytest.raises(StockUnavailable):
        confirm_payment(db, o.id)
    assert o.status == OrderStatus.pending
