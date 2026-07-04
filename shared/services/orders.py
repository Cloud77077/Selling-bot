from datetime import timedelta
from decimal import Decimal
from random import randint
from sqlalchemy import extract, func, select, update
from sqlalchemy.orm import Session
from shared.config import get_settings
from shared.models import DeliverableCode, Order, OrderStatus, PaymentMethod, Product, Setting, User, now_utc

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
        user.username = username or user.username
        user.full_name = full_name or user.full_name
        return user
    user = User(telegram_id=telegram_id, username=username, full_name=full_name)
    db.add(user); db.flush()
    return user

def find_user(db: Session, telegram_id_or_username: str) -> User | None:
    value = telegram_id_or_username.lstrip('@')
    if value.isdigit():
        return db.scalar(select(User).where(User.telegram_id == int(value)))
    return db.scalar(select(User).where(User.username == value))

def create_order(db: Session, product_id: int, user: User | None, payment_method: PaymentMethod = PaymentMethod.upi, expiry_minutes: int | None = None) -> Order:
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise ValueError('Product unavailable')
    expiry_minutes = expiry_minutes if expiry_minutes is not None else get_settings().order_expiry_minutes
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

def expire_pending_orders(db: Session) -> int:
    result = db.execute(update(Order).where(Order.status == OrderStatus.pending, Order.expires_at < now_utc()).values(status=OrderStatus.expired))
    return result.rowcount or 0

def create_manual_sale(db: Session, product_id: int, note_user: User | None = None) -> Order:
    product = db.get(Product, product_id)
    if not product:
        raise ValueError('Product unavailable')
    order = Order(order_number=next_order_number(db), user_id=note_user.id if note_user else None, product_id=product_id,
                  status=OrderStatus.pending, payment_method=PaymentMethod.manual, base_amount=product.price, payment_amount=product.price)
    db.add(order); db.flush()
    return confirm_payment(db, order.id)

def low_stock_alert_due(db: Session, product_id: int, threshold: int | None = None) -> tuple[bool, int]:
    threshold = threshold if threshold is not None else get_settings().low_stock_threshold
    remaining = stock_count(db, product_id)
    key = f'low_stock_alerted_{product_id}'
    setting = db.get(Setting, key)
    if remaining > threshold:
        if setting:
            db.delete(setting)
        return False, remaining
    if setting:
        return False, remaining
    db.merge(Setting(key=key, value=str(remaining)))
    return True, remaining
