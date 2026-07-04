from decimal import Decimal
from shared.models import Order


def money(value: Decimal | float | str) -> str:
    return f"{Decimal(str(value)):.2f}"


def delivery_message(order: Order) -> str:
    product_name = order.product.name if order.product else f"Product #{order.product_id}"
    code = order.delivered_code or "No code assigned"
    return (
        f"✅ Payment confirmed for order {order.order_number}!\n\n"
        f"Product: {product_name}\n"
        f"Amount: ₹{money(order.payment_amount)}\n\n"
        f"Your delivery code is:\n````\n{code}\n````\n\n"
        "Thank you for your purchase."
    ).replace('````', '```')


def payment_claim_message(order: Order) -> str:
    product_name = order.product.name if order.product else f"Product #{order.product_id}"
    buyer = order.user.full_name or order.user.username or order.user.telegram_id if order.user else "Unknown buyer"
    return (
        f"💸 Payment claimed for order {order.order_number}\n"
        f"Buyer: {buyer}\n"
        f"Product: {product_name}\n"
        f"Method: {order.payment_method.value}\n"
        f"Amount: ₹{money(order.payment_amount)}"
    )
