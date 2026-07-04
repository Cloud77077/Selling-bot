"""initial schema"""
from alembic import op
import sqlalchemy as sa
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('products', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('name', sa.String(200), nullable=False), sa.Column('description', sa.Text()), sa.Column('price', sa.Numeric(12,2), nullable=False), sa.Column('image_path', sa.String(500)), sa.Column('is_active', sa.Boolean(), default=True), sa.Column('created_at', sa.DateTime(timezone=True)))
    op.create_table('users', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('telegram_id', sa.Integer(), unique=True), sa.Column('username', sa.String(100)), sa.Column('full_name', sa.String(200)), sa.Column('created_at', sa.DateTime(timezone=True)))
    op.create_table('admin_users', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('username', sa.String(100), unique=True), sa.Column('password_hash', sa.String(255)), sa.Column('is_active', sa.Boolean(), default=True))
    op.create_table('settings', sa.Column('key', sa.String(100), primary_key=True), sa.Column('value', sa.Text()))
    op.create_table('orders', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('order_number', sa.String(32), unique=True), sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')), sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id')), sa.Column('status', sa.Enum('pending','paid','rejected','expired','fulfilled', name='orderstatus')), sa.Column('payment_method', sa.Enum('upi','binance','manual', name='paymentmethod')), sa.Column('payment_amount', sa.Numeric(12,2), nullable=False), sa.Column('base_amount', sa.Numeric(12,2), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True)), sa.Column('delivered_code', sa.Text()), sa.Column('created_at', sa.DateTime(timezone=True)), sa.Column('confirmed_at', sa.DateTime(timezone=True)))
    op.create_table('deliverable_codes', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id')), sa.Column('code', sa.Text(), nullable=False), sa.Column('is_sold', sa.Boolean(), default=False), sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id')), sa.Column('created_at', sa.DateTime(timezone=True)), sa.Column('sold_at', sa.DateTime(timezone=True)))

def downgrade():
    for t in ['deliverable_codes','orders','settings','admin_users','users','products']:
        op.drop_table(t)
