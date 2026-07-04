import os, shutil
from fastapi import Depends, FastAPI, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from shared.config import get_settings
from shared.database import get_db
from shared.models import AdminUser, DeliverableCode, Order, Product, Setting
from shared.services import confirm_payment, reject_payment, stock_count

app = FastAPI(title='Selling Bot Admin')
app.add_middleware(SessionMiddleware, secret_key=get_settings().secret_key)
app.mount('/static', StaticFiles(directory='admin_panel/static'), name='static')
templates = Jinja2Templates(directory='admin_panel/templates')
pwd = CryptContext(schemes=['bcrypt'], deprecated='auto')

def current_admin(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get('admin_id')
    user = db.get(AdminUser, uid) if uid else None
    if not user: raise HTTPException(303, headers={'Location': '/login'})
    return user

@app.get('/login')
def login_page(request: Request): return templates.TemplateResponse('login.html', {'request': request})

@app.post('/login')
def login(request: Request, username: str = Form(), password: str = Form(), db: Session = Depends(get_db)):
    user = db.scalar(select(AdminUser).where(AdminUser.username == username, AdminUser.is_active.is_(True)))
    if not user or not pwd.verify(password, user.password_hash): return templates.TemplateResponse('login.html', {'request': request, 'error':'Invalid login'})
    request.session['admin_id'] = user.id; return RedirectResponse('/', 303)

@app.get('/logout')
def logout(request: Request): request.session.clear(); return RedirectResponse('/login',303)

@app.get('/')
def dashboard(request: Request, db: Session = Depends(get_db), admin=Depends(current_admin)):
    return templates.TemplateResponse('dashboard.html', {'request':request, 'products': db.scalars(select(Product)).all(), 'orders': db.scalars(select(Order).order_by(Order.id.desc()).limit(10)).all(), 'stock_count': stock_count})

@app.get('/products')
def products(request: Request, db: Session = Depends(get_db), admin=Depends(current_admin)):
    return templates.TemplateResponse('products/list.html', {'request':request, 'products': db.scalars(select(Product)).all(), 'stock_count': stock_count, 'db': db})

@app.post('/products')
def save_product(name: str = Form(), price: float = Form(), description: str = Form(''), image: UploadFile | None = File(None), db: Session = Depends(get_db), admin=Depends(current_admin)):
    path = None
    if image and image.filename:
        os.makedirs(get_settings().upload_dir, exist_ok=True); path = f'/static/uploads/{image.filename}'
        with open(os.path.join(get_settings().upload_dir, image.filename), 'wb') as f: shutil.copyfileobj(image.file, f)
    db.add(Product(name=name, price=price, description=description, image_path=path)); db.commit(); return RedirectResponse('/products',303)

@app.post('/products/{pid}/delete')
def delete_product(pid:int, db: Session = Depends(get_db), admin=Depends(current_admin)):
    p=db.get(Product,pid); p.is_active=False; db.commit(); return RedirectResponse('/products',303)

@app.post('/products/{pid}/stock')
def add_stock(pid:int, codes: str = Form(), db: Session = Depends(get_db), admin=Depends(current_admin)):
    db.add_all([DeliverableCode(product_id=pid, code=c.strip()) for c in codes.splitlines() if c.strip()]); db.commit(); return RedirectResponse('/products',303)

@app.get('/orders')
def orders(request: Request, db: Session = Depends(get_db), admin=Depends(current_admin)):
    return templates.TemplateResponse('orders.html', {'request':request, 'orders': db.scalars(select(Order).order_by(Order.id.desc())).all()})

@app.post('/orders/{oid}/{action}')
def order_action(oid:int, action:str, db: Session = Depends(get_db), admin=Depends(current_admin)):
    confirm_payment(db, oid) if action == 'confirm' else reject_payment(db, oid); db.commit(); return RedirectResponse('/orders',303)

@app.get('/settings')
def settings_page(request: Request, db: Session = Depends(get_db), admin=Depends(current_admin)):
    rows = {s.key:s.value for s in db.scalars(select(Setting)).all()}
    return templates.TemplateResponse('settings.html', {'request':request, 'settings': rows})

@app.post('/settings')
def settings_save(upi_id: str = Form(''), binance_qr: str = Form(''), low_stock_threshold: str = Form('5'), expiry_timeout: str = Form('30'), db: Session = Depends(get_db), admin=Depends(current_admin)):
    for k,v in dict(upi_id=upi_id, binance_qr=binance_qr, low_stock_threshold=low_stock_threshold, expiry_timeout=expiry_timeout).items(): db.merge(Setting(key=k,value=v))
    db.commit(); return RedirectResponse('/settings',303)
