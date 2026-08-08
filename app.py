import html
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from image_utils import image_markup, prepare_image_data
from pos_service import (
    add_inventory_item,
    calculate_cart_totals,
    complete_sale,
    delete_inventory_item,
    get_dashboard_summary,
    get_settings,
    list_inventory,
    list_recent_additions,
    list_sales,
    search_products,
    update_inventory_item,
    update_settings,
    validate_cart_stock,
)
from receipt import build_receipt_html


# ============================================================
# PAGE / THEME
# ============================================================

st.set_page_config(
    page_title="DT Retail POS",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DEFAULT_STATE = {
    "page": "POS",
    "cart": [],
    "pos_qty": "1",
    "selected_sku": None,
    "payment_method": "CASH",
    "tax_override": "PRODUCT DEFAULT",
    "custom_tax_override": 0.0,
    "apply_card_fee": True,
    "last_receipt": None,
    "show_receipt": False,
    "dark_mode": True,
    "reset_pos_qty_pending": False,
    "manage_sku": None,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value

# This release intentionally opens in Dark Mode the first time it loads.
# After that, the user's toggle choice is respected for the current session.
if "theme_default_v2_initialized" not in st.session_state:
    st.session_state.dark_mode = True
    st.session_state.theme_default_v2_initialized = True


def theme_vars():
    if st.session_state.dark_mode:
        return """
        :root {
          --bg:#0d131c; --panel:#151e2a; --panel-2:#1b2635; --input:#0f1722;
          --text:#f7f9fc; --muted:#9eacbd; --line:#334154; --line-soft:#263448;
          --navy:#17346e; --navy-hi:#2451a4; --green:#159957; --green-hi:#25b96e;
          --blue:#2568d8; --blue-hi:#3b82f6; --red:#d44c4c;
          --success-bg:#143a29; --success-text:#65e4a1;
          --shadow:0 12px 32px rgba(0,0,0,.28);
          --soft-shadow:0 4px 14px rgba(0,0,0,.20);
        }
        """

    return """
    :root {
      --bg:#f2f4f7; --panel:#ffffff; --panel-2:#f8fafc; --input:#ffffff;
      --text:#111827; --muted:#667085; --line:#d8dee7; --line-soft:#e8ecf1;
      --navy:#13284e; --navy-hi:#1e3f79; --green:#18965a; --green-hi:#23b66c;
      --blue:#2868d7; --blue-hi:#3b82f6; --red:#d94747;
      --success-bg:#eaf8f0; --success-text:#137446;
      --shadow:0 12px 30px rgba(15,23,42,.08);
      --soft-shadow:0 4px 14px rgba(15,23,42,.06);
    }
    """


def load_css():
    css = Path(__file__).with_name("styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{theme_vars()}\n{css}</style>", unsafe_allow_html=True)


load_css()


# ============================================================
# HELPERS
# ============================================================


def money(value):
    return f"${float(value):,.2f}"


def esc(value):
    return html.escape(str(value or ""))


def goto(page_name):
    st.session_state.page = page_name


def keypad_press(value):
    current = str(st.session_state.get("pos_qty", "1"))
    if value == "C":
        st.session_state.pos_qty = "1"
    elif value == "⌫":
        st.session_state.pos_qty = current[:-1] or "1"
    else:
        st.session_state.pos_qty = value if current == "1" else current + value


def add_product_to_cart(product, quantity=1):
    quantity = max(int(quantity), 1)
    stock = int(product.get("quantity") or 0)

    if stock <= 0:
        return False, "This item is out of stock."

    existing = next(
        (
            item
            for item in st.session_state.cart
            if item.get("sku") == product["sku"] and not item.get("manual")
        ),
        None,
    )

    if existing:
        if existing["quantity"] + quantity > stock:
            return False, "Cart quantity exceeds available stock."
        existing["quantity"] += quantity
    else:
        if quantity > stock:
            return False, "Not enough stock."
        st.session_state.cart.append(
            {
                "sku": product["sku"],
                "product": product["product"],
                "price": float(product["price"]),
                "quantity": quantity,
                "stock": stock,
                "item_fee": float(product.get("item_fee") or 0),
                "tax_type": product.get("tax_type") or "NONE",
                "custom_tax_rate": float(product.get("custom_tax_rate") or 0),
                "image_data": product.get("image_data"),
                "manual": False,
            }
        )
    return True, f'{product["product"]} added to cart.'


def render_header():
    with st.container(key="app_header"):
        title_col, time_col, theme_col = st.columns([6.6, 2.45, 1.2], vertical_alignment="center")
        title_col.markdown('<div class="brand">DT Retail POS</div>', unsafe_allow_html=True)
        time_col.markdown(
            f'<div class="clock">◷&nbsp;&nbsp;{datetime.now().strftime("%b %d, %Y&nbsp;&nbsp;%I:%M %p")}</div>',
            unsafe_allow_html=True,
        )
        with theme_col:
            st.toggle("Dark mode", key="dark_mode", help="Switch light / dark mode")


def render_bottom_nav():
    pages = [
        ("POS", "POS"),
        ("Inventory", "Inventory"),
        ("Add Item", "Add Item"),
        ("Manage", "Manage Item"),
        ("History", "Sales History"),
        ("Settings", "Settings"),
    ]
    with st.container(key="bottom_nav"):
        cols = st.columns(6, gap="small")
        for col, (label, page) in zip(cols, pages):
            if col.button(
                label,
                key=f"nav_{page}",
                use_container_width=True,
                type="primary" if st.session_state.page == page else "secondary",
            ):
                goto(page)
                st.rerun()


def render_settings_strip(low_tax, high_tax, card_fee):
    with st.container(key="settings_strip"):
        s1, s2, s3, s4 = st.columns([1.35, 1, 1, 1], vertical_alignment="center")
        s1.markdown('<div class="settings-label">⚙&nbsp;&nbsp;Settings</div>', unsafe_allow_html=True)
        s2.markdown(f'<div class="setting-cell"><span>Low Tax</span><b>{low_tax:.2f}%</b></div>', unsafe_allow_html=True)
        s3.markdown(f'<div class="setting-cell"><span>High Tax</span><b>{high_tax:.2f}%</b></div>', unsafe_allow_html=True)
        s4.markdown(f'<div class="setting-cell"><span>Card Fee</span><b>{card_fee:.2f}%</b></div>', unsafe_allow_html=True)


def render_cart_item(index, item):
    with st.container(key=f"cart_row_{index}"):
        img, name, minus, qty, plus, price, total, remove = st.columns(
            [0.78, 2.65, 0.52, 0.52, 0.52, 0.92, 1.05, 0.52],
            vertical_alignment="center",
            gap="small",
        )
        img.markdown(image_markup(item.get("image_data"), item["product"], "cart-thumb", "thumb"), unsafe_allow_html=True)
        name.markdown(
            f'<div class="cart-name"><b>{esc(item["product"])}</b><small>SKU: {esc(item["sku"])}</small></div>',
            unsafe_allow_html=True,
        )
        if minus.button("−", key=f"cart_minus_{index}", use_container_width=True):
            item["quantity"] -= 1
            if item["quantity"] <= 0:
                st.session_state.cart.pop(index)
            st.rerun()
        qty.markdown(f'<div class="cart-qty">{int(item["quantity"])}</div>', unsafe_allow_html=True)
        if plus.button("+", key=f"cart_plus_{index}", use_container_width=True):
            if item.get("manual") or item["quantity"] < item["stock"]:
                item["quantity"] += 1
                st.rerun()
            else:
                st.toast("No more stock available.")
        price.markdown(f'<div class="cart-money">{money(item["price"])}</div>', unsafe_allow_html=True)
        total.markdown(f'<div class="cart-money">{money(float(item["price"]) * int(item["quantity"]))}</div>', unsafe_allow_html=True)
        if remove.button("✕", key=f"cart_remove_{index}", use_container_width=True):
            st.session_state.cart.pop(index)
            st.rerun()


# ============================================================
# HEADER + DATA
# ============================================================

render_header()
settings = get_settings()
low_tax = settings.get("LOW_TAX", 0.0)
high_tax = settings.get("HIGH_TAX", 0.0)
card_fee = settings.get("CARD_FEE", 0.0)
summary = get_dashboard_summary()


# ============================================================
# POS PAGE
# ============================================================

if st.session_state.page == "POS":
    left, right = st.columns([1, 1.08], gap="medium")

    with left:
        with st.container(key="pos_left"):
            st.markdown('<h2 class="section-title">Search / Scan Item</h2>', unsafe_allow_html=True)

            search_text = st.text_input(
                "Search / Scan Item",
                placeholder="Barcode / SKU / Product Name",
                label_visibility="collapsed",
                key="pos_search",
            )

            matches = search_products(search_text)
            selected_product = None

            if matches:
                skus = [row["sku"] for row in matches]
                if st.session_state.selected_sku not in skus:
                    st.session_state.selected_sku = matches[0]["sku"]

                st.markdown('<div class="suggestions-title">Inventory suggestions</div>', unsafe_allow_html=True)
                for idx, row in enumerate(matches[:4]):
                    with st.container(key=f"suggestion_{idx}"):
                        c1, c2, c3 = st.columns([5.2, 1.1, 1.25], vertical_alignment="center", gap="small")
                        c1.markdown(
                            f'<div class="suggestion-copy"><b>{esc(row["product"])}</b>'
                            f'<span>{esc(row["sku"])} · {esc(row["category"])} · {money(row["price"])} · Stock {int(row["quantity"])}</span></div>',
                            unsafe_allow_html=True,
                        )
                        if c2.button("View", key=f"view_{row['sku']}", use_container_width=True):
                            st.session_state.selected_sku = row["sku"]
                            st.rerun()
                        if c3.button("+ Add", key=f"quick_add_{row['sku']}", use_container_width=True, disabled=int(row["quantity"]) <= 0):
                            ok, msg = add_product_to_cart(row, 1)
                            if ok:
                                st.toast(msg)
                            else:
                                st.error(msg)
                            if ok:
                                st.session_state.selected_sku = row["sku"]
                                st.rerun()

                selected_product = next(
                    (row for row in matches if row["sku"] == st.session_state.selected_sku),
                    matches[0],
                )

                with st.container(key="product_card"):
                    img_col, detail_col, qty_col = st.columns([1.2, 2.0, 1.45], vertical_alignment="center", gap="medium")
                    img_col.markdown(
                        image_markup(selected_product.get("image_data"), selected_product["product"], "selected-product-image", "detail"),
                        unsafe_allow_html=True,
                    )
                    detail_col.markdown(
                        f"""
                        <div class="product-copy">
                          <div class="product-name">{esc(selected_product['product'])}</div>
                          <div class="product-line"><span>SKU</span><b>{esc(selected_product['sku'])}</b></div>
                          <div class="product-line"><span>Barcode</span><b>{esc(selected_product['barcode'] or '—')}</b></div>
                          <div class="product-line"><span>Price</span><b class="product-price">{money(selected_product['price'])}</b></div>
                          <div class="product-line"><span>Stock</span><b class="stock">{int(selected_product['quantity'])}</b></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    with qty_col:
                        st.markdown('<div class="quantity-label">Quantity</div>', unsafe_allow_html=True)
                        if st.session_state.reset_pos_qty_pending:
                            st.session_state.pos_qty = "1"
                            st.session_state.reset_pos_qty_pending = False
                        st.text_input("Quantity", key="pos_qty", label_visibility="collapsed")
                        requested_qty = int(st.session_state.pos_qty) if str(st.session_state.pos_qty).isdigit() else 1
                        if st.button(
                            "🛒  Add to Cart",
                            key="add_to_cart",
                            use_container_width=True,
                            type="primary",
                            disabled=int(selected_product["quantity"]) <= 0,
                        ):
                            ok, msg = add_product_to_cart(selected_product, max(requested_qty, 1))
                            if ok:
                                st.session_state.reset_pos_qty_pending = True
                                st.toast(msg)
                                st.rerun()
                            else:
                                st.error(msg)
            elif search_text.strip():
                st.markdown(
                    '<div class="search-state"><b>No matching inventory item.</b><span>Try a product name, SKU, barcode, or category.</span></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="search-state"><div class="scan-glyph">▥</div><b>Scan a barcode or type a SKU / product name.</b></div>',
                    unsafe_allow_html=True,
                )

            keypad = [["7", "8", "9"], ["4", "5", "6"], ["1", "2", "3"], ["C", "0", "⌫"]]
            for r, row in enumerate(keypad):
                cols = st.columns(3, gap="small")
                for c, label in enumerate(row):
                    cols[c].button(
                        label,
                        key=f"keypad_{r}_{c}",
                        use_container_width=True,
                        on_click=keypad_press,
                        args=(label,),
                    )

            with st.expander("Manual Price Item"):
                manual_name = st.text_input("Description", placeholder="Miscellaneous Item", key="manual_name")
                manual_price = st.number_input("Manual Price", min_value=0.01, step=0.01, format="%.2f", key="manual_price")
                manual_quantity = st.number_input("Quantity", min_value=1, step=1, key="manual_quantity")
                manual_fee = st.number_input("Item Fee", min_value=0.0, step=0.01, format="%.2f", key="manual_fee")
                manual_tax = st.selectbox("Tax", ["NONE", "LOW", "HIGH", "CUSTOM"], key="manual_tax")
                manual_custom_tax = 0.0
                if manual_tax == "CUSTOM":
                    manual_custom_tax = st.number_input("Custom Tax %", min_value=0.0, step=0.1, key="manual_custom_tax")
                if st.button("Add Manual Item", key="add_manual", use_container_width=True):
                    if not manual_name.strip():
                        st.error("Enter a description.")
                    else:
                        st.session_state.cart.append(
                            {
                                "sku": f"MANUAL-{uuid.uuid4().hex[:6].upper()}",
                                "product": manual_name.strip(),
                                "price": float(manual_price),
                                "quantity": int(manual_quantity),
                                "stock": None,
                                "item_fee": float(manual_fee),
                                "tax_type": manual_tax,
                                "custom_tax_rate": float(manual_custom_tax),
                                "image_data": None,
                                "manual": True,
                            }
                        )
                        st.rerun()

            st.markdown('<h3 class="subheading">Quick Tax</h3>', unsafe_allow_html=True)
            tax_cols = st.columns(4, gap="small")
            tax_choices = [
                ("No Tax", "NO TAX"),
                ("Low Tax", "LOW TAX"),
                ("High Tax", "HIGH TAX"),
                ("Custom Tax", "CUSTOM TAX"),
            ]
            for col, (label, value) in zip(tax_cols, tax_choices):
                if col.button(
                    label,
                    key=f"tax_{value}",
                    use_container_width=True,
                    type="primary" if st.session_state.tax_override == value else "secondary",
                ):
                    st.session_state.tax_override = value
                    st.rerun()

            if st.session_state.tax_override == "CUSTOM TAX":
                st.session_state.custom_tax_override = st.number_input(
                    "Custom Tax %",
                    min_value=0.0,
                    value=float(st.session_state.custom_tax_override),
                    step=0.1,
                    format="%.2f",
                    key="custom_tax_override_input",
                )

            if st.button("Use Product Tax", key="use_product_tax"):
                st.session_state.tax_override = "PRODUCT DEFAULT"
                st.rerun()


    with right:
        with st.container(key="pos_right"):
            st.markdown('<h2 class="section-title">Cart</h2>', unsafe_allow_html=True)

            if st.session_state.cart:
                st.markdown(
                    '<div class="cart-head"><span>Item</span><span>Qty</span><span>Price</span><span>Line Total</span><span></span></div>',
                    unsafe_allow_html=True,
                )
                for index, item in enumerate(st.session_state.cart):
                    render_cart_item(index, item)
            else:
                st.markdown('<div class="empty-cart">Your cart is empty.</div>', unsafe_allow_html=True)

            totals = calculate_cart_totals(
                st.session_state.cart,
                st.session_state.payment_method,
                st.session_state.tax_override,
                st.session_state.custom_tax_override,
                st.session_state.apply_card_fee,
                settings,
            )

            st.markdown(
                f"""
                <div class="totals">
                  <div><span>Subtotal</span><b>{money(totals['subtotal'])}</b></div>
                  <div><span>Product Fees</span><b>{money(totals['fees'])}</b></div>
                  <div><span>Tax</span><b>{money(totals['tax'])}</b></div>
                  <div><span>Card Fee</span><b>{money(totals['card_fee'])}</b></div>
                  <hr>
                  <div class="grand"><span>Total</span><b>{money(totals['total'])}</b></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown('<h3 class="subheading">Payment</h3>', unsafe_allow_html=True)
            pay1, pay2 = st.columns(2, gap="medium")
            if pay1.button("▣  Cash", key="cash_btn", use_container_width=True, type="primary" if st.session_state.payment_method == "CASH" else "secondary"):
                st.session_state.payment_method = "CASH"
                st.rerun()
            if pay2.button("▤  Card", key="card_btn", use_container_width=True, type="primary" if st.session_state.payment_method == "CARD" else "secondary"):
                st.session_state.payment_method = "CARD"
                st.rerun()

            cash_received = 0.0
            change_due = 0.0

            if st.session_state.payment_method == "CASH":
                cash_received = st.number_input("Cash Received", min_value=0.0, step=1.0, format="%.2f", key="cash_received")
                change_due = max(cash_received - totals["total"], 0.0)
                st.markdown(
                    f'<div class="change-card"><span>Change Due</span><b>{money(change_due)}</b></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.checkbox(f"Apply Card Fee ({card_fee:.2f}%)", key="apply_card_fee")
                totals = calculate_cart_totals(
                    st.session_state.cart,
                    st.session_state.payment_method,
                    st.session_state.tax_override,
                    st.session_state.custom_tax_override,
                    st.session_state.apply_card_fee,
                    settings,
                )
                st.markdown(
                    f'<div class="change-card"><span>Card Total</span><b>{money(totals["total"])}</b></div>',
                    unsafe_allow_html=True,
                )

            a1, a2 = st.columns(2, gap="medium")
            if a1.button("✓  Complete Sale", key="complete_sale", use_container_width=True, type="primary", disabled=not st.session_state.cart):
                totals = calculate_cart_totals(
                    st.session_state.cart,
                    st.session_state.payment_method,
                    st.session_state.tax_override,
                    st.session_state.custom_tax_override,
                    st.session_state.apply_card_fee,
                    settings,
                )
                if st.session_state.payment_method == "CASH" and cash_received < totals["total"]:
                    st.error("Cash received is less than the total.")
                else:
                    stock_ok, problem = validate_cart_stock(st.session_state.cart)
                    if not stock_ok:
                        st.error(f"Not enough stock for {problem}.")
                    else:
                        receipt_id = "DT-" + datetime.now().strftime("%Y%m%d-") + uuid.uuid4().hex[:6].upper()
                        complete_sale(st.session_state.cart, receipt_id)
                        st.session_state.last_receipt = {
                            "receipt_id": receipt_id,
                            "date": datetime.now().strftime("%m/%d/%Y %I:%M %p"),
                            "items": [dict(item) for item in st.session_state.cart],
                            "totals": totals,
                            "payment_method": st.session_state.payment_method,
                            "cash_received": cash_received,
                            "change_due": change_due,
                        }
                        st.session_state.cart = []
                        st.session_state.show_receipt = False
                        st.toast(f"Sale complete · {receipt_id}")
                        st.rerun()

            if a2.button("▣  Print Receipt", key="print_receipt", use_container_width=True, disabled=st.session_state.last_receipt is None):
                st.session_state.show_receipt = not st.session_state.show_receipt

            if st.session_state.show_receipt and st.session_state.last_receipt:
                with st.expander("Receipt Preview", expanded=True):
                    components.html(build_receipt_html(st.session_state.last_receipt), height=540, scrolling=True)


# ============================================================
# INVENTORY
# ============================================================

elif st.session_state.page == "Inventory":
    st.markdown('<h1 class="page-title">Inventory</h1>', unsafe_allow_html=True)
    st.caption("Search inventory and add any in-stock item directly to the POS cart.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Products", summary["products"])
    m2.metric("Units in Stock", summary["units"])
    m3.metric("Inventory Value", money(summary["inventory_value"]))
    m4.metric("Sales Revenue", money(summary["revenue"]))

    inventory_search = st.text_input("Search Inventory", placeholder="Search product, SKU, barcode, or category", key="inventory_search")
    inventory = search_products(inventory_search, limit=30) if inventory_search.strip() else list_inventory()

    if not inventory:
        st.info("No inventory matches found.")

    for item in inventory:
        with st.container(key=f"inventory_{item['sku']}"):
            i1, i2, i3, i4, i5, i6 = st.columns([0.8, 2.5, 1, 1, 1.15, 1.35], vertical_alignment="center", gap="small")
            i1.markdown(image_markup(item.get("image_data"), item["product"], "inventory-thumb", "thumb"), unsafe_allow_html=True)
            i2.markdown(
                f'<div class="inventory-name"><b>{esc(item["product"])}</b><span>SKU: {esc(item["sku"])} · {esc(item["barcode"] or "No barcode")}</span></div>',
                unsafe_allow_html=True,
            )
            i3.metric("Stock", int(item["quantity"]))
            i4.metric("Price", money(item["price"]))
            i5.metric("Value", money(float(item["quantity"]) * float(item["price"])))
            stock_qty = int(item["quantity"])
            action_label = "Restock" if stock_qty <= 0 else "+ Add to POS"
            if i6.button(
                action_label,
                key=f"inv_action_{item['sku']}",
                use_container_width=True,
                type="primary" if stock_qty > 0 else "secondary",
            ):
                if stock_qty <= 0:
                    st.session_state.manage_sku = item["sku"]
                    goto("Manage Item")
                    st.rerun()
                else:
                    ok, msg = add_product_to_cart(item, 1)
                    if ok:
                        st.session_state.selected_sku = item["sku"]
                        goto("POS")
                        st.toast(msg)
                        st.rerun()
                    else:
                        st.error(msg)


# ============================================================
# ADD ITEM
# ============================================================

elif st.session_state.page == "Add Item":
    st.markdown('<h1 class="page-title">Add Item</h1>', unsafe_allow_html=True)
    st.caption("Create an inventory product with SKU, barcode, tax, fee, stock, and an optional picture.")

    with st.container(key="form_card"):
        form, photo = st.columns([1.5, 1], gap="large")
        with form:
            sku = st.text_input("SKU", placeholder="DT-1005")
            barcode = st.text_input("Barcode", placeholder="100000000005")
            product = st.text_input("Product Name", placeholder="Coca-Cola")
            category = st.text_input("Category", placeholder="Beverages")
            quantity = st.number_input("Quantity", min_value=0, step=1)
            price = st.number_input("Price", min_value=0.01, step=0.01, format="%.2f")
            item_fee = st.number_input("Item Fee", min_value=0.0, step=0.01, format="%.2f")
            tax_type = st.selectbox("Tax Type", ["NONE", "LOW", "HIGH", "CUSTOM"])
            custom_tax_rate = 0.0
            if tax_type == "CUSTOM":
                custom_tax_rate = st.number_input("Custom Tax %", min_value=0.0, step=0.1, format="%.2f")
        with photo:
            st.markdown("### Product Picture")
            uploaded = st.file_uploader("Upload product picture", type=["png", "jpg", "jpeg"])
            preview = prepare_image_data(uploaded) if uploaded else None
            st.markdown(image_markup(preview, product or "Product", "upload-preview", "detail"), unsafe_allow_html=True)

        if st.button("Add Product", key="add_product", type="primary", use_container_width=True):
            sku = sku.strip().upper()
            product = product.strip()
            category = category.strip()
            barcode = barcode.strip()
            if not sku or not product or not category:
                st.error("SKU, product name, and category are required.")
            else:
                ok, msg = add_inventory_item(sku, barcode, product, category, quantity, price, item_fee, tax_type, custom_tax_rate, preview)
                if ok:
                    st.success("Product added successfully.")
                else:
                    st.error(msg)


# ============================================================
# MANAGE ITEM
# ============================================================

elif st.session_state.page == "Manage Item":
    st.markdown('<h1 class="page-title">Manage Item</h1>', unsafe_allow_html=True)
    inventory = list_inventory()
    if not inventory:
        st.info("No inventory items found.")
    else:
        options = {f'{row["sku"]} — {row["product"]}': row for row in inventory}
        option_labels = list(options.keys())
        requested_sku = st.session_state.get("manage_sku")
        requested_index = 0
        if requested_sku:
            for idx, label in enumerate(option_labels):
                if options[label]["sku"] == requested_sku:
                    requested_index = idx
                    break
        selected_label = st.selectbox("Select Item", option_labels, index=requested_index, key="manage_item_selector")
        item = options[selected_label]
        st.session_state.manage_sku = item["sku"]

        with st.container(key="form_card"):
            photo, edit = st.columns([1, 2], gap="large")
            with photo:
                st.markdown("### Product Picture")
                st.markdown(image_markup(item.get("image_data"), item["product"], "manage-preview", "detail"), unsafe_allow_html=True)
                new_image_file = st.file_uploader("Change product picture", type=["png", "jpg", "jpeg"], key=f"img_{item['sku']}")
                remove_image = st.checkbox("Remove current picture", key=f"rm_img_{item['sku']}")
            with edit:
                new_barcode = st.text_input("Barcode", value=item["barcode"] or "", key=f"manage_barcode_{item['sku']}")
                new_quantity = st.number_input("Stock Quantity", min_value=0, value=int(item["quantity"]), step=1, key=f"manage_quantity_{item['sku']}", help="Restock is allowed even when current stock is 0.")
                new_price = st.number_input("Price", min_value=0.01, value=float(item["price"]), step=0.01, format="%.2f", key=f"manage_price_{item['sku']}")
                new_fee = st.number_input("Item Fee", min_value=0.0, value=float(item["item_fee"] or 0), step=0.01, format="%.2f", key=f"manage_fee_{item['sku']}")
                tax_options = ["NONE", "LOW", "HIGH", "CUSTOM"]
                current_tax = item["tax_type"] if item["tax_type"] in tax_options else "NONE"
                new_tax_type = st.selectbox("Tax Type", tax_options, index=tax_options.index(current_tax), key=f"manage_tax_type_{item['sku']}")
                new_custom_tax = float(item["custom_tax_rate"] or 0)
                if new_tax_type == "CUSTOM":
                    new_custom_tax = st.number_input("Custom Tax %", min_value=0.0, value=new_custom_tax, step=0.1, format="%.2f", key=f"manage_custom_tax_{item['sku']}")

            if st.button("Save Changes", key="save_changes", type="primary", use_container_width=True):
                if new_image_file:
                    new_image_data = prepare_image_data(new_image_file)
                    keep_existing = False
                elif remove_image:
                    new_image_data = None
                    keep_existing = False
                else:
                    new_image_data = None
                    keep_existing = True
                update_inventory_item(item["sku"], new_barcode.strip(), new_quantity, new_price, new_fee, new_tax_type, new_custom_tax, new_image_data, keep_existing)
                st.success("Item updated successfully.")
                st.rerun()

            st.divider()
            confirm = st.checkbox(f'I confirm I want to delete {item["product"]}')
            if st.button("Delete Item", key="delete_item", use_container_width=True):
                if confirm:
                    delete_inventory_item(item["sku"])
                    st.success("Item deleted.")
                    st.rerun()
                else:
                    st.warning("Confirm deletion first.")


# ============================================================
# HISTORY
# ============================================================

elif st.session_state.page == "Sales History":
    st.markdown('<h1 class="page-title">Sales History</h1>', unsafe_allow_html=True)
    sales = list_sales()
    if sales:
        st.dataframe(sales, use_container_width=True, hide_index=True)
    else:
        st.info("No sales have been recorded yet.")


# ============================================================
# SETTINGS
# ============================================================

elif st.session_state.page == "Settings":
    st.markdown('<h1 class="page-title">Settings</h1>', unsafe_allow_html=True)
    st.caption("Configure taxes and card fees, and review recently added inventory.")

    with st.container(key="form_card"):
        st.markdown("### POS Settings")
        c1, c2, c3 = st.columns(3)
        new_low_tax = c1.number_input("Low Tax %", min_value=0.0, value=float(low_tax), step=0.1, format="%.2f")
        new_high_tax = c2.number_input("High Tax %", min_value=0.0, value=float(high_tax), step=0.1, format="%.2f")
        new_card_fee = c3.number_input("Card Fee %", min_value=0.0, value=float(card_fee), step=0.1, format="%.2f")
        if st.button("Save Settings", key="save_settings", type="primary", use_container_width=True):
            update_settings(new_low_tax, new_high_tax, new_card_fee)
            st.success("Settings saved.")
            st.rerun()

    st.markdown("### Recently Added Inventory")
    recent = list_recent_additions(25)
    if recent is None:
        st.info("Run pos_inventory_history_upgrade.sql once to enable added-date history.")
    elif recent:
        st.dataframe(recent, use_container_width=True, hide_index=True)
    else:
        st.info("No recently added products yet.")


render_bottom_nav()
