import asyncio
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from shared.config import get_settings
from shared.database import SessionLocal
from shared.models import DeliverableCode, Order, OrderStatus, PaymentMethod, Product, Setting, User
from shared.services import (StockUnavailable, confirm_payment, create_manual_sale, create_order,
                             ensure_user, expire_pending_orders, find_user, low_stock_alert_due,
                             reject_payment, stock_count)

router = Router()

class AddProductFlow(StatesGroup):
    name = State(); description = State(); price = State(); category = State(); codes = State(); image = State(); confirm = State()

class RestockFlow(StatesGroup):
    codes = State()

def admin_only(msg: Message) -> bool:
    return bool(msg.from_user and msg.from_user.id in get_settings().admin_id_set)

def setting(db, key, default=''):
    row = db.get(Setting, key)
    env_default = getattr(get_settings(), key, default) if hasattr(get_settings(), key) else default
    return row.value if row and row.value else env_default

def delivery_message(order: Order) -> str:
    return (f'✅ Payment confirmed!\n'
            f'Order: {order.order_number}\n'
            f'Product: {order.product.name}\n\n'
            f'Your delivery code:\n```\n{order.delivered_code}\n```')

async def notify_low_stock(bot: Bot, product_id: int):
    with SessionLocal() as db:
        threshold = int(setting(db, 'low_stock_threshold', get_settings().low_stock_threshold))
        due, remaining = low_stock_alert_due(db, product_id, threshold)
        product = db.get(Product, product_id)
        db.commit()
    if due and product:
        for aid in get_settings().admin_id_set:
            await bot.send_message(aid, f'⚠️ Low stock: {product.name} has only {remaining} left.')

async def send_delivery(bot: Bot, order: Order):
    if order.user and order.user.telegram_id:
        await bot.send_message(order.user.telegram_id, delivery_message(order), parse_mode='Markdown')

@router.message(Command('start'))
async def start(message: Message):
    with SessionLocal() as db:
        if message.from_user:
            ensure_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name); db.commit()
    kb = InlineKeyboardBuilder(); kb.button(text='Browse products', callback_data='products:0')
    await message.answer('Welcome! Choose an option:', reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith('products:'))
async def products(cb: CallbackQuery):
    page = int(cb.data.split(':')[1]); per = 5
    with SessionLocal() as db:
        items = db.scalars(select(Product).where(Product.is_active.is_(True)).offset(page*per).limit(per)).all()
        kb = InlineKeyboardBuilder()
        for p in items:
            kb.button(text=f'{p.name} ({stock_count(db,p.id)} in stock)', callback_data=f'product:{p.id}')
        if page: kb.button(text='Previous', callback_data=f'products:{page-1}')
        if len(items) == per: kb.button(text='Next', callback_data=f'products:{page+1}')
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
        expiry = int(setting(db, 'order_expiry_minutes', get_settings().order_expiry_minutes))
        order = create_order(db, int(pid), user, PaymentMethod(method), expiry_minutes=expiry)
        payto = setting(db, 'upi_id' if method == 'upi' else 'binance_pay_qr_path', 'Ask admin to configure payment settings')
        db.commit()
    kb = InlineKeyboardBuilder(); kb.button(text="I've Paid", callback_data=f'paid:{order.id}')
    await cb.message.answer(f'Order {order.order_number}\nPay amount: `{order.payment_amount}`\nPayment info: {payto}', parse_mode='Markdown', reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith('paid:'))
async def paid(cb: CallbackQuery):
    oid = int(cb.data.split(':')[1]); kb = InlineKeyboardBuilder(); kb.button(text='Confirm', callback_data=f'confirm:{oid}'); kb.button(text='Reject', callback_data=f'reject:{oid}')
    await cb.message.answer('Thanks! Waiting for admin confirmation.')
    for aid in get_settings().admin_id_set:
        await cb.bot.send_message(aid, f'Payment claimed for order #{oid}', reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith(('confirm:','reject:')))
async def admin_decision(cb: CallbackQuery):
    if cb.from_user.id not in get_settings().admin_id_set: return await cb.answer('Unauthorized', show_alert=True)
    action, oid = cb.data.split(':')
    with SessionLocal() as db:
        order = confirm_payment(db, int(oid)) if action == 'confirm' else reject_payment(db, int(oid))
        product_id = order.product_id; user_id = order.user.telegram_id if order.user else None; msg = delivery_message(order) if action == 'confirm' else f'❌ Order {order.order_number} was rejected.'
        db.commit()
    if user_id: await cb.bot.send_message(user_id, msg, parse_mode='Markdown')
    if action == 'confirm': await notify_low_stock(cb.bot, product_id)
    await cb.message.answer(f'{action.title()}ed order #{oid}')

@router.message(Command('addproduct'))
async def addproduct(message: Message, state: FSMContext):
    if not admin_only(message): return
    await state.clear(); await state.set_state(AddProductFlow.name); await message.answer('Product name?')

@router.message(AddProductFlow.name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text); await state.set_state(AddProductFlow.description); await message.answer('Description?')

@router.message(AddProductFlow.description)
async def add_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text); await state.set_state(AddProductFlow.price); await message.answer('Price?')

@router.message(AddProductFlow.price)
async def add_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text); await state.set_state(AddProductFlow.category); await message.answer('Category?')

@router.message(AddProductFlow.category)
async def add_cat(message: Message, state: FSMContext):
    await state.update_data(category=message.text); await state.set_state(AddProductFlow.codes); await message.answer('Paste deliverable codes, one per line.')

@router.message(AddProductFlow.codes)
async def add_codes(message: Message, state: FSMContext):
    await state.update_data(codes=[c.strip() for c in message.text.splitlines() if c.strip()]); await state.set_state(AddProductFlow.image); await message.answer('Upload an image now, or type /skip.')

@router.message(AddProductFlow.image, Command('skip'))
async def add_skip_image(message: Message, state: FSMContext):
    await state.update_data(image_path=None); await state.set_state(AddProductFlow.confirm); await message.answer('Type CONFIRM to create product.')

@router.message(AddProductFlow.image, F.photo)
async def add_image(message: Message, state: FSMContext):
    os.makedirs(get_settings().upload_dir, exist_ok=True)
    rel = f'{get_settings().upload_dir}/bot_{message.photo[-1].file_unique_id}.jpg'
    await message.bot.download(message.photo[-1], destination=rel)
    await state.update_data(image_path='/' + rel); await state.set_state(AddProductFlow.confirm); await message.answer('Type CONFIRM to create product.')

@router.message(AddProductFlow.confirm)
async def add_confirm(message: Message, state: FSMContext):
    if message.text != 'CONFIRM': return await message.answer('Cancelled. Run /addproduct again to restart.')
    data = await state.get_data()
    desc = f"Category: {data['category']}\n\n{data['description']}"
    with SessionLocal() as db:
        p = Product(name=data['name'], description=desc, price=data['price'], image_path=data.get('image_path'))
        db.add(p); db.flush(); db.add_all([DeliverableCode(product_id=p.id, code=c) for c in data['codes']]); db.commit()
    await state.clear(); await message.answer('Product created and stocked.')

@router.message(Command('restock'))
async def restock(message: Message, state: FSMContext):
    if not admin_only(message): return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit(): return await message.answer('Usage: /restock <product_id>')
    await state.update_data(restock_product_id=int(parts[1])); await state.set_state(RestockFlow.codes); await message.answer('Paste additional codes, one per line.')

@router.message(RestockFlow.codes)
async def restock_codes(message: Message, state: FSMContext):
    data = await state.get_data(); pid = data['restock_product_id']; codes = [c.strip() for c in message.text.splitlines() if c.strip()]
    with SessionLocal() as db:
        db.add_all([DeliverableCode(product_id=pid, code=c) for c in codes]); db.commit()
    await state.clear(); await message.answer(f'Added {len(codes)} codes to product {pid}.')

@router.message(Command('manualsale'))
async def manualsale(message: Message):
    if not admin_only(message): return
    parts = message.text.split()
    if len(parts) != 3: return await message.answer('Usage: /manualsale <telegram_id_or_username> <product_id>')
    with SessionLocal() as db:
        user = find_user(db, parts[1])
        if not user: return await message.answer('Buyer must /start the bot once before manual sale can be delivered.')
        order = create_manual_sale(db, int(parts[2]), user); user_tid = user.telegram_id; product_id = order.product_id; msg = delivery_message(order); db.commit()
    await message.bot.send_message(user_tid, msg, parse_mode='Markdown')
    await notify_low_stock(message.bot, product_id)
    await message.answer(f'Manual sale recorded as {order.order_number}.')

@router.message(Command('stats'))
async def stats(message: Message):
    if not admin_only(message): return
    with SessionLocal() as db:
        total = db.scalar(select(func.count(Order.id))) or 0
        revenue = db.scalar(select(func.coalesce(func.sum(Order.payment_amount), 0)).where(Order.status == OrderStatus.fulfilled)) or 0
        today = db.scalar(select(func.count(Order.id)).where(func.date(Order.created_at) == func.current_date())) or 0
        top = db.execute(select(Product.name, func.count(Order.id)).join(Order, Order.product_id == Product.id).where(Order.status == OrderStatus.fulfilled).group_by(Product.id).order_by(func.count(Order.id).desc()).limit(5)).all()
        low = [(p.name, stock_count(db, p.id)) for p in db.scalars(select(Product).where(Product.is_active.is_(True))).all() if stock_count(db, p.id) <= int(setting(db, 'low_stock_threshold', get_settings().low_stock_threshold))]
    text = f'📊 Stats\nTotal orders: {total}\nTotal revenue: ₹{revenue}\nOrders today: {today}\nTop products:\n' + ('\n'.join(f'- {n}: {c}' for n,c in top) or '- none') + '\nLow/out stock:\n' + ('\n'.join(f'- {n}: {c}' for n,c in low) or '- none')
    await message.answer(text)

async def expiry_loop(bot: Bot):
    while True:
        expired_user_ids = []
        with SessionLocal() as db:
            orders = db.scalars(select(Order).where(Order.status == OrderStatus.pending, Order.expires_at < func.now())).all()
            expired_user_ids = [(o.user.telegram_id, o.order_number) for o in orders if o.user]
            expire_pending_orders(db); db.commit()
        for tid, number in expired_user_ids:
            await bot.send_message(tid, f'⌛ Order {number} expired. Please start again when you are ready.')
        await asyncio.sleep(180)

async def main():
    bot = Bot(get_settings().bot_token); dp = Dispatcher(storage=MemoryStorage()); dp.include_router(router)
    asyncio.create_task(expiry_loop(bot))
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
