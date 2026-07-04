import asyncio
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import desc, func, select
from sqlalchemy.orm import joinedload

from shared.config import get_settings
from shared.database import SessionLocal
from shared.messages import delivery_message, payment_claim_message
from shared.models import DeliverableCode, Order, OrderStatus, PaymentMethod, Product, Setting, User
from shared.services import (
    confirm_payment,
    create_manual_sale,
    create_order,
    ensure_user,
    expired_pending_orders,
    reject_payment,
    stock_count,
)

router = Router()

class AddProductFlow(StatesGroup):
    name = State(); description = State(); price = State(); category = State(); codes = State(); image = State(); confirm = State()

class RestockFlow(StatesGroup):
    codes = State()

def admin_only(msg: Message) -> bool:
    return bool(msg.from_user and msg.from_user.id in get_settings().admin_id_set)

def setting(db, key, default=''):
    row = db.get(Setting, key)
    return row.value if row else default

def parse_codes(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]

def low_stock_threshold(db) -> int:
    val = setting(db, 'low_stock_threshold', str(get_settings().low_stock_threshold))
    return int(val) if str(val).isdigit() else get_settings().low_stock_threshold

async def notify_low_stock(bot: Bot, product_id: int, before: int, after: int, threshold: int):
    if before > threshold and after <= threshold:
        with SessionLocal() as db:
            product = db.get(Product, product_id)
            name = product.name if product else f'Product #{product_id}'
        for aid in get_settings().admin_id_set:
            await bot.send_message(aid, f'⚠️ Low stock: {name} has only {after} left.')

@router.message(Command('start'))
async def start(message: Message):
    kb = InlineKeyboardBuilder(); kb.button(text='Browse products', callback_data='products:0')
    await message.answer('Welcome! Choose an option:', reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith('products:'))
async def products(cb: CallbackQuery):
    page = int(cb.data.split(':')[1]); per = 5
    with SessionLocal() as db:
        items = db.scalars(select(Product).where(Product.is_active.is_(True)).offset(page*per).limit(per)).all()
        kb = InlineKeyboardBuilder()
        for p in items: kb.button(text=f'{p.name} ({stock_count(db,p.id)} in stock)', callback_data=f'product:{p.id}')
        kb.button(text='Next', callback_data=f'products:{page+1}')
    await cb.message.edit_text('Products:', reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith('product:'))
async def detail(cb: CallbackQuery):
    pid = int(cb.data.split(':')[1])
    with SessionLocal() as db:
        p = db.get(Product, pid); text = f'*{p.name}*\n₹{p.price}\nStock: {stock_count(db,p.id)}\n\n{p.description}'
    kb = InlineKeyboardBuilder(); kb.button(text='Pay with UPI', callback_data=f'buy:upi:{pid}'); kb.button(text='Pay with Binance', callback_data=f'buy:binance:{pid}')
    await cb.message.answer(text, parse_mode='Markdown', reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith('buy:'))
async def buy(cb: CallbackQuery):
    _, method, pid = cb.data.split(':')
    with SessionLocal() as db:
        user = ensure_user(db, cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        order = create_order(db, int(pid), user, PaymentMethod(method)); db.commit()
        payto = setting(db, 'upi_id' if method == 'upi' else 'binance_qr', 'Ask admin to configure payment settings')
    kb = InlineKeyboardBuilder(); kb.button(text="I've Paid", callback_data=f'paid:{order.id}')
    await cb.message.answer(f'Order {order.order_number}\nPay amount: `{order.payment_amount}`\nPayment info: {payto}', parse_mode='Markdown', reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith('paid:'))
async def paid(cb: CallbackQuery):
    oid = int(cb.data.split(':')[1]); kb = InlineKeyboardBuilder(); kb.button(text='Confirm', callback_data=f'confirm:{oid}'); kb.button(text='Reject', callback_data=f'reject:{oid}')
    await cb.message.answer('Thanks! Waiting for admin confirmation.')
    with SessionLocal() as db:
        order = db.get(Order, oid, options=[joinedload(Order.product), joinedload(Order.user)])
    for aid in get_settings().admin_id_set:
        await cb.bot.send_message(aid, payment_claim_message(order), reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith(('confirm:','reject:')))
async def admin_decision(cb: CallbackQuery):
    if cb.from_user.id not in get_settings().admin_id_set: return await cb.answer('Unauthorized', show_alert=True)
    action, oid = cb.data.split(':')
    before = after = threshold = product_id = buyer_id = None
    with SessionLocal() as db:
        order = db.get(Order, int(oid), options=[joinedload(Order.product), joinedload(Order.user)])
        product_id = order.product_id; buyer_id = order.user.telegram_id if order.user else None
        threshold = low_stock_threshold(db); before = stock_count(db, product_id)
        order = confirm_payment(db, int(oid)) if action == 'confirm' else reject_payment(db, int(oid))
        after = stock_count(db, product_id); msg = delivery_message(order) if action == 'confirm' else f'❌ Order {order.order_number} was rejected. Please contact admin if this is a mistake.'
        db.commit()
    if buyer_id: await cb.bot.send_message(buyer_id, msg, parse_mode='Markdown')
    await cb.message.answer(f'{action.title()}ed {order.order_number}')
    if action == 'confirm': await notify_low_stock(cb.bot, product_id, before, after, threshold)

@router.message(Command('manualsale'))
async def manualsale(message: Message):
    if not admin_only(message): return
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3: return await message.answer('Usage: /manualsale <telegram_id_or_username> <product_id>')
    target, pid_s = parts[1], parts[2]
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == int(target))) if target.isdigit() else db.scalar(select(User).where(User.username == target.lstrip('@')))
        if not user: return await message.answer('Buyer not found. Ask them to /start the bot first.')
        threshold = low_stock_threshold(db); before = stock_count(db, int(pid_s)); order = create_manual_sale(db, int(pid_s), user); after = stock_count(db, int(pid_s)); db.commit()
        msg = delivery_message(order)
    await message.bot.send_message(user.telegram_id, msg, parse_mode='Markdown')
    await message.answer(f'Manual sale {order.order_number} delivered to {user.telegram_id}.')
    await notify_low_stock(message.bot, int(pid_s), before, after, threshold)

@router.message(Command('addproduct'))
async def addproduct(message: Message, state: FSMContext):
    if not admin_only(message): return
    await state.set_state(AddProductFlow.name); await message.answer('Product name?')

@router.message(AddProductFlow.name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip()); await state.set_state(AddProductFlow.description); await message.answer('Description?')
@router.message(AddProductFlow.description)
async def add_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip()); await state.set_state(AddProductFlow.price); await message.answer('Price?')
@router.message(AddProductFlow.price)
async def add_price(message: Message, state: FSMContext):
    try: price = Decimal(message.text.strip())
    except InvalidOperation: return await message.answer('Please send a valid number for price.')
    await state.update_data(price=str(price)); await state.set_state(AddProductFlow.category); await message.answer('Category?')
@router.message(AddProductFlow.category)
async def add_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip()); await state.set_state(AddProductFlow.codes); await message.answer('Paste deliverable codes, one per line.')
@router.message(AddProductFlow.codes)
async def add_codes(message: Message, state: FSMContext):
    codes = parse_codes(message.text or '')
    if not codes: return await message.answer('Send at least one code.')
    await state.update_data(codes=codes); await state.set_state(AddProductFlow.image); await message.answer('Upload an image now, or send /skip.')
@router.message(AddProductFlow.image, Command('skip'))
async def add_skip_image(message: Message, state: FSMContext):
    await state.update_data(image_path=None); await state.set_state(AddProductFlow.confirm); await message.answer('Send /confirm to create product, or /cancel.')
@router.message(AddProductFlow.image, F.photo)
async def add_image(message: Message, state: FSMContext):
    import os
    os.makedirs(get_settings().upload_dir, exist_ok=True)
    filename = f'tg_{message.photo[-1].file_unique_id}.jpg'; path = os.path.join(get_settings().upload_dir, filename)
    await message.bot.download(message.photo[-1], destination=path)
    await state.update_data(image_path=f'/static/uploads/{filename}'); await state.set_state(AddProductFlow.confirm); await message.answer('Image saved. Send /confirm to create product, or /cancel.')
@router.message(AddProductFlow.confirm, Command('confirm'))
async def add_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    desc = f"Category: {data['category']}\n\n{data['description']}" if data.get('category') else data['description']
    with SessionLocal() as db:
        p = Product(name=data['name'], price=Decimal(data['price']), description=desc, image_path=data.get('image_path'))
        db.add(p); db.flush(); db.add_all([DeliverableCode(product_id=p.id, code=c) for c in data['codes']]); db.commit()
    await state.clear(); await message.answer(f"Product added with {len(data['codes'])} codes.")
@router.message(Command('cancel'))
async def cancel(message: Message, state: FSMContext):
    await state.clear(); await message.answer('Cancelled.')

@router.message(Command('restock'))
async def restock(message: Message, state: FSMContext):
    if not admin_only(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit(): return await message.answer('Usage: /restock <product_id>')
    await state.update_data(restock_pid=int(parts[1])); await state.set_state(RestockFlow.codes); await message.answer('Paste additional codes, one per line.')
@router.message(RestockFlow.codes)
async def restock_codes(message: Message, state: FSMContext):
    data = await state.get_data(); codes = parse_codes(message.text or '')
    with SessionLocal() as db:
        if not db.get(Product, data['restock_pid']): return await message.answer('Product not found.')
        db.add_all([DeliverableCode(product_id=data['restock_pid'], code=c) for c in codes]); db.commit()
    await state.clear(); await message.answer(f'Added {len(codes)} codes.')

@router.message(Command('stats'))
async def stats(message: Message):
    if not admin_only(message): return
    with SessionLocal() as db:
        total_orders = db.scalar(select(func.count(Order.id))) or 0
        revenue = db.scalar(select(func.coalesce(func.sum(Order.payment_amount), 0)).where(Order.status == OrderStatus.fulfilled)) or 0
        today = db.scalar(select(func.count(Order.id)).where(func.date(Order.created_at) == func.current_date())) or 0
        top = db.execute(select(Product.name, func.count(Order.id).label('sold')).join(Order, Order.product_id == Product.id).where(Order.status == OrderStatus.fulfilled).group_by(Product.name).order_by(desc('sold')).limit(5)).all()
        threshold = low_stock_threshold(db); products = db.scalars(select(Product).where(Product.is_active.is_(True))).all()
        low = [(p.name, stock_count(db,p.id)) for p in products if stock_count(db,p.id) <= threshold]
    lines = [f'📊 Stats', f'Total orders: {total_orders}', f'Total revenue: ₹{revenue}', f'Orders today: {today}', 'Top products:']
    lines += [f'- {name}: {sold}' for name, sold in top] or ['- None yet']
    lines += ['Low/out of stock:'] + ([f'- {name}: {count}' for name, count in low] or ['- None'])
    await message.answer('\n'.join(lines))

async def expiry_worker(bot: Bot):
    while True:
        await asyncio.sleep(180)
        with SessionLocal() as db:
            orders = expired_pending_orders(db); db.commit()
            notices = [(o.user.telegram_id, o.order_number) for o in orders if o.user]
        for telegram_id, num in notices:
            await bot.send_message(telegram_id, f'⌛ Order {num} expired. Please start again if you still want to buy.')

async def main():
    bot = Bot(get_settings().bot_token); dp = Dispatcher(); dp.include_router(router)
    asyncio.create_task(expiry_worker(bot)); await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
