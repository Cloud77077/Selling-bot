from datetime import timedelta
from decimal import Decimal
from random import randint
from sqlalchemy import extract, func, select, update
from sqlalchemy.orm import Session
from shared.config import get_settings
from shared.models import DeliverableCode, Order, OrderStatus, PaymentMethod, Product, User, now_utc

class StockUnavailable(Exception):
    pass

def next_order_number(db: Session, when=None) -> str:
    when = when or now_utc()
    count = db.scalar(select(func.count(Order.id)).where(extract('year', Order.created_at) == when.year)) or 0
    return f'ORD-{when.year}-{count + 1:04d}'

def unique_upi_amount(db: Session, base_amount: Decimal | float) -> Decimal:
    base = Decimal(str(base_amount)).quantize(Decimal('0.01'))
    for _ in range(100):
        candidate = base + (Decimal(randint(1, 99)) / Decimal('100'))
        exists = db.scalar(select(Order.id).where(Order.status == OrderStatus.pending, Order.payment_amount == candidate).limit(1))
        if not exists:
            return candidate
    raise RuntimeError('Could not allocate unique UPI amount')

def stock_count(db: Session, product_id: int) -> int:
    return db.scalar(select(func.count(DeliverableCode.id)).where(DeliverableCode.product_id == product_id, DeliverableCode.is_sold.is_(False))) or 0

def ensure_user(db: Session, telegram_id: int, username=None, full_name=None) -> User:
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user:
        return user
    user = User(telegram_id=telegram_id, username=username, full_name=full_name)
    db.add(user); db.flush()
    return user

def create_order(db: Session, product_id: int, user: User | None, payment_method: PaymentMethod = PaymentMethod.upi, expiry_minutes: int | None = None) -> Order:
    expiry_minutes = expiry_minutes or get_settings().order_expiry_minutes
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise ValueError('Product unavailable')
    amount = unique_upi_amount(db, product.price) if payment_method == PaymentMethod.upi else Decimal(str(product.price))
    order = Order(order_number=next_order_number(db), user_id=user.id if user else None, product_id=product.id,
                  payment_method=payment_method, base_amount=product.price, payment_amount=amount,
                  expires_at=now_utc() + timedelta(minutes=expiry_minutes))
    db.add(order); db.flush()
    return order

def assign_stock_atomically(db: Session, order: Order) -> str:
    code = db.scalar(select(DeliverableCode).where(DeliverableCode.product_id == order.product_id, DeliverableCode.is_sold.is_(False)).order_by(DeliverableCode.id).with_for_update(skip_locked=True).limit(1))
    if not code:
        raise StockUnavailable('No stock available')
    code.is_sold = True; code.order_id = order.id; code.sold_at = now_utc()
    order.delivered_code = code.code
    return code.code

def confirm_payment(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if not order or order.status != OrderStatus.pending:
        raise ValueError('Order is not pending')
    assign_stock_atomically(db, order)
    order.status = OrderStatus.fulfilled; order.confirmed_at = now_utc()
    db.flush()
    return order

def reject_payment(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if not order or order.status != OrderStatus.pending:
        raise ValueError('Order is not pending')
    order.status = OrderStatus.rejected
    db.flush(); return order

def expired_pending_orders(db: Session) -> list[Order]:
    orders = db.scalars(select(Order).where(Order.status == OrderStatus.pending, Order.expires_at < now_utc())).all()
    for order in orders:
        order.status = OrderStatus.expired
    db.flush()
    return orders

def expire_pending_orders(db: Session) -> int:
    return len(expired_pending_orders(db))

def create_manual_sale(db: Session, product_id: int, note_user: User | None = None) -> Order:
    product = db.get(Product, product_id)
    if not product:
        raise ValueError('Product unavailable')
    order = Order(order_number=next_order_number(db), user_id=note_user.id if note_user else None, product_id=product_id,
                  status=OrderStatus.pending, payment_method=PaymentMethod.manual, base_amount=product.price, payment_amount=product.price)
    db.add(order); db.flush()
    return confirm_payment(db, order.id)
