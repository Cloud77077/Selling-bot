from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from shared.config import get_settings
from shared.database import SessionLocal
from shared.models import PaymentMethod, Product, Setting, Order
from shared.services import create_order, ensure_user, stock_count, confirm_payment, reject_payment, create_manual_sale

router = Router()

def admin_only(msg: Message) -> bool:
    return msg.from_user and msg.from_user.id in get_settings().admin_id_set

def setting(db, key, default=''):
    row = db.get(Setting, key); return row.value if row else default

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
    for aid in get_settings().admin_id_set:
        await cb.bot.send_message(aid, f'Payment claimed for order #{oid}', reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith(('confirm:','reject:')))
async def admin_decision(cb: CallbackQuery):
    if cb.from_user.id not in get_settings().admin_id_set: return await cb.answer('Unauthorized', show_alert=True)
    action, oid = cb.data.split(':')
    with SessionLocal() as db:
        order = confirm_payment(db, int(oid)) if action == 'confirm' else reject_payment(db, int(oid)); db.commit()
    await cb.message.answer(f'{action.title()}ed {order.order_number}\n```\n{order.delivered_code or "Rejected"}\n```', parse_mode='Markdown')

@router.message(Command('manualsale'))
async def manualsale(message: Message):
    if not admin_only(message): return
    pid = int(message.text.split()[1])
    with SessionLocal() as db: order = create_manual_sale(db, pid); db.commit()
    await message.answer(f'Manual sale {order.order_number}\n```\n{order.delivered_code}\n```', parse_mode='Markdown')

@router.message(Command('addproduct'))
async def addproduct(message: Message):
    if not admin_only(message): return
    _, name, price = message.text.split(maxsplit=2)
    with SessionLocal() as db: db.add(Product(name=name, price=price, description='')); db.commit()
    await message.answer('Product added')

@router.message(Command('restock'))
async def restock(message: Message):
    if not admin_only(message): return
    from shared.models import DeliverableCode
    _, pid, *codes = message.text.split()
    with SessionLocal() as db:
        db.add_all([DeliverableCode(product_id=int(pid), code=c) for c in codes]); db.commit()
    await message.answer(f'Added {len(codes)} codes')

@router.message(Command('stats'))
async def stats(message: Message):
    if not admin_only(message): return
    with SessionLocal() as db: products = db.scalars(select(Product)).all()
    await message.answer('\n'.join(f'{p.name}: {stock_count(SessionLocal(), p.id)}' for p in products) or 'No products')

async def main():
    bot = Bot(get_settings().bot_token); dp = Dispatcher(); dp.include_router(router); await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio; asyncio.run(main())
