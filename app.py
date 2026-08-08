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
# APP SHELL
# ============================================================

st.set_page_config(
    page_title="DT Retail POS",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def theme_overrides(theme):
    if theme == "DARK":
        return r"""
        :root {
            --bg: #0f141c;
            --panel: #171e28;
            --panel-soft: #1d2632;
            --text: #f4f7fb;
            --muted: #aeb8c6;
            --line: #354152;
            --input-bg: #111821;
            --input-border: #465469;
            --placeholder: #8390a2;
            --soft-surface: #202a37;
            --table-head: #202a37;
            --hover: #263241;
            --disabled-bg: #2b3442;
            --disabled-text: #9ba7b6;
            --soft-green: #173528;
            --green-text: #6fe0a6;
            --shadow: 0 8px 28px rgba(0,0,0,.30);
        }

        .stApp, .stApp > div, [data-testid="stAppViewContainer"] { background: var(--bg) !important; color: var(--text) !important; }
        .st-key-top_header, .st-key-pos_left_panel, .st-key-pos_right_panel,
        .st-key-selected_product_card, .st-key-more_strip, .st-key-form_card,
        .st-key-bottom_navigation, .st-key-suggestion_card,
        [class*="st-key-inventory_row_"], [data-testid="stMetric"], [data-testid="stExpander"] {
            background: var(--panel) !important; color: var(--text) !important; border-color: var(--line) !important;
        }
        .dt-clock, .search-hint-card, .empty-cart, .cart-table-head, .suggestion-copy {
            background: var(--panel-soft) !important; color: var(--text) !important; border-color: var(--line) !important;
        }
        .selected-product-image, .upload-preview, .manage-preview, .cart-thumb, .inventory-thumb {
            background: var(--panel-soft) !important; border-color: var(--line) !important;
        }
        [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
        [data-baseweb="select"] > div, [data-baseweb="input"] > div, textarea {
            background: var(--input-bg) !important; color: var(--text) !important; border-color: var(--input-border) !important;
        }
        [data-testid="stTextInput"] input::placeholder, textarea::placeholder { color: var(--placeholder) !important; opacity: 1 !important; }
        [data-testid="stNumberInput"] button, [data-baseweb="select"] svg { color: var(--text) !important; }
        [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"], [role="option"] {
            background: var(--panel) !important; color: var(--text) !important;
        }
        [role="option"]:hover { background: var(--hover) !important; }
        [data-testid="stDataFrame"] { background: var(--panel) !important; color: var(--text) !important; border-color: var(--line) !important; }
        .product-detail span, .more-cell span, .cart-product small, .stCaption, [data-testid="stCaptionContainer"] { color: var(--muted) !important; }
        .st-key-change_due_box { background: var(--soft-green) !important; }
        .change-due { color: var(--green-text) !important; }
        hr, .totals-list hr { border-color: var(--line) !important; }
        """

    return r"""
    :root {
        --bg: #f4f6f8;
        --panel: #ffffff;
        --panel-soft: #fafbfc;
        --text: #121a2a;
        --muted: #657080;
        --line: #dfe3e8;
        --input-bg: #ffffff;
        --input-border: #cfd6de;
        --placeholder: #7c8795;
        --soft-surface: #f7f8fa;
        --table-head: #f5f5f5;
        --hover: #f3f5f7;
        --disabled-bg: #e4e8ed;
        --disabled-text: #697483;
        --soft-green: #edf8f1;
        --green-text: #176f43;
        --shadow: 0 6px 22px rgba(19,30,48,.08);
    }
    """


def load_css(theme, filename="styles.css"):
    css_path = Path(__file__).with_name(filename)
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}\n{theme_overrides(theme)}</style>", unsafe_allow_html=True)


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "page": "POS",
    "cart": [],
    "pos_qty": "1",
    "payment_method": "CASH",
    "tax_override": "PRODUCT DEFAULT",
    "custom_tax_override": 0.0,
    "apply_card_fee": True,
    "last_receipt": None,
    "show_receipt": False,
    "dark_mode": False,
    "reset_pos_qty_pending": False,
    "selected_sku": None,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


load_css("DARK" if st.session_state.dark_mode else "LIGHT")


def goto(page_name):
    st.session_state.page = page_name


def keypad_press(value):
    current = str(st.session_state.get("pos_qty", "1"))

    if value == "C":
        st.session_state.pos_qty = "1"
    elif value == "⌫":
        trimmed = current[:-1]
        st.session_state.pos_qty = trimmed if trimmed else "1"
    else:
        if current == "1":
            st.session_state.pos_qty = value
        else:
            st.session_state.pos_qty = current + value


def money(value):
    return f"${float(value):,.2f}"


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


def render_bottom_navigation():
    pages = [
        ("POS", "POS"),
        ("Inventory", "Inventory"),
        ("Add Item", "Add Item"),
        ("Manage", "Manage Item"),
        ("History", "Sales History"),
        ("Settings", "More"),
    ]

    with st.container(key="bottom_navigation", border=True):
        cols = st.columns(6, gap="small")
        for idx, (label, page_name) in enumerate(pages):
            if cols[idx].button(
                label,
                key=f"footer_nav_{page_name}",
                use_container_width=True,
                type="primary" if st.session_state.page == page_name else "secondary",
            ):
                goto(page_name)
                st.rerun()


# ============================================================
# HEADER — no hamburger; date/time + theme switch on right
# ============================================================

with st.container(key="top_header"):
    title_col, clock_col, theme_col = st.columns([6.8, 2.4, 1.4], vertical_alignment="center")

    with title_col:
        st.markdown('<div class="dt-brand">DT Retail POS</div>', unsafe_allow_html=True)

    with clock_col:
        st.markdown(
            f'<div class="dt-clock">◷&nbsp;&nbsp;{datetime.now().strftime("%b %d, %Y&nbsp;&nbsp;&nbsp;%I:%M %p")}</div>',
            unsafe_allow_html=True,
        )

    with theme_col:
        st.markdown('<div class="theme-toggle-label">Dark</div>', unsafe_allow_html=True)
        st.toggle(
            "Dark mode",
            key="dark_mode",
            label_visibility="collapsed",
            help="Switch between light and dark mode",
        )


settings = get_settings()
low_tax = settings.get("LOW_TAX", 0.0)
high_tax = settings.get("HIGH_TAX", 0.0)
card_fee = settings.get("CARD_FEE", 0.0)
summary = get_dashboard_summary()


# ============================================================
# POS PAGE
# ============================================================

if st.session_state.page == "POS":
    left, right = st.columns([1, 1.05], gap="medium")

    # --------------------------------------------------------
    # LEFT PANEL
    # --------------------------------------------------------
    with left:
        with st.container(key="pos_left_panel", border=True):
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
                match_skus = [row["sku"] for row in matches]
                if st.session_state.selected_sku not in match_skus:
                    st.session_state.selected_sku = matches[0]["sku"]

                st.markdown('<div class="suggestion-title">Inventory suggestions</div>', unsafe_allow_html=True)

                for idx, row in enumerate(matches[:5]):
                    with st.container(key=f"suggestion_card_{idx}"):
                        s1, s2, s3 = st.columns([5.2, 1.1, 1.2], vertical_alignment="center", gap="small")
                        s1.markdown(
                            f"""
                            <div class="suggestion-copy">
                                <b>{row['product']}</b>
                                <span>{row['sku']} · {row['category']} · {money(row['price'])} · Stock {int(row['quantity'])}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        if s2.button("View", key=f"suggest_view_{row['sku']}", use_container_width=True):
                            st.session_state.selected_sku = row["sku"]
                            st.rerun()

                        if s3.button(
                            "+ Add",
                            key=f"suggest_add_{row['sku']}",
                            use_container_width=True,
                            disabled=int(row["quantity"]) <= 0,
                        ):
                            ok, message = add_product_to_cart(row, 1)
                            if ok:
                                st.session_state.selected_sku = row["sku"]
                                st.toast(message)
                                st.rerun()
                            else:
                                st.error(message)

                selected_product = next(
                    (row for row in matches if row["sku"] == st.session_state.selected_sku),
                    matches[0],
                )

                with st.container(key="selected_product_card", border=True):
                    img_col, details_col, qty_col = st.columns([1.25, 1.95, 1.45], vertical_alignment="center")

                    with img_col:
                        st.markdown(
                            image_markup(
                                selected_product.get("image_data"),
                                selected_product["product"],
                                "selected-product-image",
                                "detail",
                            ),
                            unsafe_allow_html=True,
                        )

                    with details_col:
                        st.markdown(
                            f"""
                            <div class="product-info">
                                <div class="product-name">{selected_product['product']}</div>
                                <div class="product-detail"><span>SKU</span><b>{selected_product['sku']}</b></div>
                                <div class="product-detail"><span>Barcode</span><b>{selected_product['barcode'] or '—'}</b></div>
                                <div class="product-detail"><span>Price</span><b class="product-price">{money(selected_product['price'])}</b></div>
                                <div class="product-detail"><span>Stock</span><b class="stock-value">{int(selected_product['quantity'])}</b></div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    with qty_col:
                        st.markdown('<div class="quantity-label">Quantity</div>', unsafe_allow_html=True)

                        if st.session_state.get("reset_pos_qty_pending", False):
                            st.session_state.pos_qty = "1"
                            st.session_state.reset_pos_qty_pending = False

                        st.text_input(
                            "Quantity",
                            key="pos_qty",
                            label_visibility="collapsed",
                        )

                        requested_qty = int(st.session_state.pos_qty) if str(st.session_state.pos_qty).isdigit() else 1
                        requested_qty = max(requested_qty, 1)

                        if st.button(
                            "🛒  Add to Cart",
                            key="add_to_cart",
                            use_container_width=True,
                            type="primary",
                            disabled=int(selected_product["quantity"]) <= 0,
                        ):
                            ok, message = add_product_to_cart(selected_product, requested_qty)
                            if ok:
                                st.session_state.reset_pos_qty_pending = True
                                st.toast(message)
                                st.rerun()
                            else:
                                st.error(message)

            elif search_text.strip():
                st.markdown(
                    """
                    <div class="search-hint-card no-match-card">
                        <div class="scan-icon">⌕</div>
                        <div><b>No inventory match.</b><br><span>Try another spelling, SKU, barcode, or add the product from Add Item.</span></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                    <div class="search-hint-card">
                        <div class="scan-icon">▥</div>
                        <div><b>Scan a barcode</b> or type a SKU / product name to begin.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Keypad
            keypad = [
                ["7", "8", "9"],
                ["4", "5", "6"],
                ["1", "2", "3"],
                ["C", "0", "⌫"],
            ]

            for row_index, row in enumerate(keypad):
                cols = st.columns(3, gap="small")
                for col_index, label in enumerate(row):
                    cols[col_index].button(
                        label,
                        key=f"keypad_{row_index}_{col_index}_{label}",
                        use_container_width=True,
                        on_click=keypad_press,
                        args=(label,),
                    )

            # Manual price item
            with st.expander("Manual Price Item"):
                manual_name = st.text_input("Description", placeholder="Miscellaneous Item", key="manual_name")
                manual_price = st.number_input("Manual Price", min_value=0.01, step=0.01, format="%.2f", key="manual_price")
                manual_quantity = st.number_input("Quantity", min_value=1, step=1, key="manual_quantity")
                manual_fee = st.number_input("Item Fee", min_value=0.0, step=0.01, format="%.2f", key="manual_fee")
                manual_tax = st.selectbox("Tax", ["NONE", "LOW", "HIGH", "CUSTOM"], key="manual_tax")

                manual_custom_tax = 0.0
                if manual_tax == "CUSTOM":
                    manual_custom_tax = st.number_input("Custom Tax %", min_value=0.0, step=0.1, key="manual_custom_tax")

                if st.button("Add Manual Item", use_container_width=True, key="add_manual_item"):
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

            # Quick tax
            st.markdown('<h3 class="quick-tax-heading">Quick Tax</h3>', unsafe_allow_html=True)
            tax_cols = st.columns(4, gap="small")
            tax_choices = [
                ("No Tax", "NO TAX", "tax_no"),
                ("Low Tax", "LOW TAX", "tax_low"),
                ("High Tax", "HIGH TAX", "tax_high"),
                ("Custom Tax", "CUSTOM TAX", "tax_custom"),
            ]

            for idx, (label, value, button_key) in enumerate(tax_choices):
                active = st.session_state.tax_override == value
                if tax_cols[idx].button(
                    label,
                    key=button_key,
                    use_container_width=True,
                    type="primary" if active else "secondary",
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
                    key="pos_custom_tax",
                )

            if st.button("Use Product Tax", key="use_product_tax"):
                st.session_state.tax_override = "PRODUCT DEFAULT"
                st.rerun()

            with st.container(key="more_strip", border=True):
                m1, m2, m3, m4 = st.columns([1.45, 1, 1, 1])
                m1.markdown("<div class='more-title'>⚙&nbsp;&nbsp;Settings</div>", unsafe_allow_html=True)
                m2.markdown(f"<div class='more-cell'><span>Low Tax</span><b>{low_tax:.2f}%</b></div>", unsafe_allow_html=True)
                m3.markdown(f"<div class='more-cell'><span>High Tax</span><b>{high_tax:.2f}%</b></div>", unsafe_allow_html=True)
                m4.markdown(f"<div class='more-cell'><span>Card Fee</span><b>{card_fee:.2f}%</b></div>", unsafe_allow_html=True)

    # --------------------------------------------------------
    # RIGHT PANEL
    # --------------------------------------------------------
    with right:
        with st.container(key="pos_right_panel", border=True):
            st.markdown('<h2 class="section-title">Cart</h2>', unsafe_allow_html=True)

            if st.session_state.cart:
                st.markdown(
                    """
                    <div class="cart-table-head">
                        <span>Item</span><span>Qty</span><span>Price</span><span>Line Total</span><span></span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                for index, item in enumerate(st.session_state.cart):
                    with st.container(key=f"cart_item_{index}"):
                        c_img, c_name, c_minus, c_qty, c_plus, c_price, c_total, c_delete = st.columns(
                            [0.8, 2.8, 0.55, 0.6, 0.55, 1.0, 1.05, 0.55],
                            vertical_alignment="center",
                            gap="small",
                        )

                        c_img.markdown(
                            image_markup(item.get("image_data"), item["product"], "cart-thumb", "thumb"),
                            unsafe_allow_html=True,
                        )
                        c_name.markdown(
                            f'<div class="cart-product"><b>{item["product"]}</b><small>SKU: {item["sku"]}</small></div>',
                            unsafe_allow_html=True,
                        )

                        if c_minus.button("−", key=f"minus_{index}", use_container_width=True):
                            item["quantity"] -= 1
                            if item["quantity"] <= 0:
                                st.session_state.cart.pop(index)
                            st.rerun()

                        c_qty.markdown(f'<div class="cart-qty">{item["quantity"]}</div>', unsafe_allow_html=True)

                        if c_plus.button("+", key=f"plus_{index}", use_container_width=True):
                            if item.get("manual") or item["quantity"] < item["stock"]:
                                item["quantity"] += 1
                                st.rerun()
                            else:
                                st.warning("No more stock available.")

                        c_price.markdown(f'<div class="cart-money">{money(item["price"])}</div>', unsafe_allow_html=True)
                        line_base = float(item["price"]) * int(item["quantity"])
                        c_total.markdown(f'<div class="cart-money">{money(line_base)}</div>', unsafe_allow_html=True)

                        if c_delete.button("✕", key=f"remove_{index}", use_container_width=True):
                            st.session_state.cart.pop(index)
                            st.rerun()
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

            with st.container(key="totals_box", border=True):
                st.markdown(
                    f"""
                    <div class="totals-list">
                        <div><span>Subtotal</span><b>{money(totals['subtotal'])}</b></div>
                        <div><span>Product Fees</span><b>{money(totals['fees'])}</b></div>
                        <div><span>Tax</span><b>{money(totals['tax'])}</b></div>
                        <div><span>Card Fee</span><b>{money(totals['card_fee'])}</b></div>
                        <hr>
                        <div class="grand-total"><span>Total</span><b>{money(totals['total'])}</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown('<h3 class="payment-heading">Payment</h3>', unsafe_allow_html=True)
            pay1, pay2 = st.columns(2, gap="medium")

            if pay1.button("▣  Cash", key="cash_button", use_container_width=True):
                st.session_state.payment_method = "CASH"
                st.rerun()

            if pay2.button("▤  Card", key="card_button", use_container_width=True):
                st.session_state.payment_method = "CARD"
                st.rerun()

            cash_received = 0.0
            change_due = 0.0

            if st.session_state.payment_method == "CASH":
                cash_received = st.number_input(
                    "Cash Received",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key="cash_received",
                )
                change_due = cash_received - totals["total"]

                with st.container(key="change_due_box", border=True):
                    st.markdown(
                        f'<div class="change-due"><span>Change Due</span><b>{money(max(change_due, 0))}</b></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.checkbox(
                    f"Apply Card Fee ({card_fee:.2f}%)",
                    key="apply_card_fee",
                )
                totals = calculate_cart_totals(
                    st.session_state.cart,
                    st.session_state.payment_method,
                    st.session_state.tax_override,
                    st.session_state.custom_tax_override,
                    st.session_state.apply_card_fee,
                    settings,
                )
                with st.container(key="change_due_box", border=True):
                    st.markdown(
                        f'<div class="change-due"><span>Card Total</span><b>{money(totals["total"])}</b></div>',
                        unsafe_allow_html=True,
                    )

            action1, action2 = st.columns(2, gap="medium")

            if action1.button(
                "✓  Complete Sale",
                key="complete_sale_button",
                use_container_width=True,
                disabled=not st.session_state.cart,
            ):
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
                    stock_ok, problem_product = validate_cart_stock(st.session_state.cart)
                    if not stock_ok:
                        st.error(f"Not enough stock for {problem_product}. Refresh the cart.")
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
                            "change_due": max(change_due, 0.0),
                        }
                        st.session_state.cart = []
                        st.session_state.show_receipt = False
                        st.toast(f"Sale complete · {receipt_id}")
                        st.rerun()

            if action2.button(
                "▣  Print Receipt",
                key="print_receipt_button",
                use_container_width=True,
                disabled=st.session_state.last_receipt is None,
            ):
                st.session_state.show_receipt = not st.session_state.show_receipt

            if st.session_state.show_receipt and st.session_state.last_receipt:
                with st.expander("Receipt Preview", expanded=True):
                    components.html(
                        build_receipt_html(st.session_state.last_receipt),
                        height=540,
                        scrolling=True,
                    )


# ============================================================
# INVENTORY PAGE
# ============================================================

elif st.session_state.page == "Inventory":
    st.markdown('<h1 class="page-title">Inventory</h1>', unsafe_allow_html=True)
    st.caption("Search inventory and send any in-stock item directly to the POS cart.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Products", summary["products"])
    m2.metric("Units in Stock", summary["units"])
    m3.metric("Inventory Value", money(summary["inventory_value"]))
    m4.metric("Sales Revenue", money(summary["revenue"]))

    inventory_search = st.text_input(
        "Search Inventory",
        placeholder="Search product, SKU, barcode, or category",
        key="inventory_search",
    )

    inventory = search_products(inventory_search, limit=30) if inventory_search.strip() else list_inventory()

    if not inventory:
        st.info("No inventory matches found.")

    for item in inventory:
        with st.container(key=f"inventory_row_{item['sku']}", border=True):
            i1, i2, i3, i4, i5, i6 = st.columns(
                [0.8, 2.5, 1.0, 1.0, 1.1, 1.2],
                vertical_alignment="center",
                gap="small",
            )
            i1.markdown(image_markup(item.get("image_data"), item["product"], "inventory-thumb", "thumb"), unsafe_allow_html=True)
            i2.markdown(
                f'<div class="inventory-name"><b>{item["product"]}</b><span>SKU: {item["sku"]} · {item["barcode"] or "No barcode"}</span></div>',
                unsafe_allow_html=True,
            )
            i3.metric("Stock", int(item["quantity"]))
            i4.metric("Price", money(item["price"]))
            i5.metric("Value", money(float(item["quantity"]) * float(item["price"])))

            if i6.button(
                "+ Add to POS",
                key=f"inventory_add_{item['sku']}",
                use_container_width=True,
                disabled=int(item["quantity"]) <= 0,
            ):
                ok, message = add_product_to_cart(item, 1)
                if ok:
                    st.session_state.selected_sku = item["sku"]
                    goto("POS")
                    st.toast(message)
                    st.rerun()
                else:
                    st.error(message)


# ============================================================
# ADD ITEM PAGE — includes product picture upload
# ============================================================

elif st.session_state.page == "Add Item":
    st.markdown('<h1 class="page-title">Add Item</h1>', unsafe_allow_html=True)
    st.caption("Create a product, assign SKU/barcode, pricing, tax, stock, and an optional product picture.")

    with st.container(key="form_card", border=True):
        left_form, right_form = st.columns([1.45, 1])

        with left_form:
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

        with right_form:
            st.markdown("### Product Picture")
            uploaded_image = st.file_uploader(
                "Upload product picture",
                type=["png", "jpg", "jpeg"],
                help="PNG/JPG. The image is compressed before saving in Databricks.",
            )

            preview_data = None
            if uploaded_image:
                preview_data = prepare_image_data(uploaded_image)
                st.markdown(image_markup(preview_data, product or "Product", "upload-preview", "detail"), unsafe_allow_html=True)
            else:
                st.markdown(image_markup(None, "Product", "upload-preview", "detail"), unsafe_allow_html=True)

        if st.button("Add Product", key="add_product_submit", type="primary", use_container_width=True):
            sku = sku.strip().upper()
            product = product.strip()
            category = category.strip()
            barcode = barcode.strip()

            if not sku or not product or not category:
                st.error("SKU, product name, and category are required.")
            else:
                ok, message = add_inventory_item(
                    sku,
                    barcode,
                    product,
                    category,
                    quantity,
                    price,
                    item_fee,
                    tax_type,
                    custom_tax_rate,
                    preview_data,
                )
                if ok:
                    st.success("Product added successfully. It is now available in POS search and Inventory.")
                else:
                    st.error(message)


# ============================================================
# MANAGE ITEM PAGE
# ============================================================

elif st.session_state.page == "Manage Item":
    st.markdown('<h1 class="page-title">Manage Item</h1>', unsafe_allow_html=True)

    inventory = list_inventory()
    if not inventory:
        st.info("No inventory items found.")
    else:
        options = {f'{row["sku"]} — {row["product"]}': row for row in inventory}
        selected_label = st.selectbox("Select Item", list(options.keys()))
        item = options[selected_label]

        with st.container(key="form_card", border=True):
            image_col, edit_col = st.columns([1, 2])

            with image_col:
                st.markdown("### Product Picture")
                st.markdown(image_markup(item.get("image_data"), item["product"], "manage-preview", "detail"), unsafe_allow_html=True)
                new_image_file = st.file_uploader(
                    "Change product picture",
                    type=["png", "jpg", "jpeg"],
                    key=f"manage_image_{item['sku']}",
                )
                remove_image = st.checkbox("Remove current picture", key=f"remove_image_{item['sku']}")

            with edit_col:
                new_barcode = st.text_input("Barcode", value=item["barcode"] or "")
                new_quantity = st.number_input("Stock Quantity", min_value=0, value=int(item["quantity"]), step=1)
                new_price = st.number_input("Price", min_value=0.01, value=float(item["price"]), step=0.01, format="%.2f")
                new_fee = st.number_input("Item Fee", min_value=0.0, value=float(item["item_fee"] or 0), step=0.01, format="%.2f")

                tax_options = ["NONE", "LOW", "HIGH", "CUSTOM"]
                current_tax = item["tax_type"] if item["tax_type"] in tax_options else "NONE"
                new_tax_type = st.selectbox("Tax Type", tax_options, index=tax_options.index(current_tax))

                new_custom_tax = float(item["custom_tax_rate"] or 0)
                if new_tax_type == "CUSTOM":
                    new_custom_tax = st.number_input("Custom Tax %", min_value=0.0, value=new_custom_tax, step=0.1, format="%.2f")

            if st.button("Save Changes", key="save_item_changes", type="primary", use_container_width=True):
                if new_image_file:
                    new_image_data = prepare_image_data(new_image_file)
                    keep_existing_image = False
                elif remove_image:
                    new_image_data = None
                    keep_existing_image = False
                else:
                    new_image_data = None
                    keep_existing_image = True

                update_inventory_item(
                    item["sku"],
                    new_barcode.strip(),
                    new_quantity,
                    new_price,
                    new_fee,
                    new_tax_type,
                    new_custom_tax,
                    new_image_data,
                    keep_existing_image,
                )
                st.success("Item updated successfully.")
                st.rerun()

            st.divider()
            confirm_delete = st.checkbox(f'I confirm I want to delete {item["product"]}')
            if st.button("Delete Item", key="delete_item_button", use_container_width=True):
                if not confirm_delete:
                    st.warning("Confirm deletion first.")
                else:
                    delete_inventory_item(item["sku"])
                    st.success("Item deleted.")
                    st.rerun()


# ============================================================
# SALES HISTORY PAGE
# ============================================================

elif st.session_state.page == "Sales History":
    st.markdown('<h1 class="page-title">Sales History</h1>', unsafe_allow_html=True)
    sales = list_sales()
    if sales:
        st.dataframe(sales, use_container_width=True, hide_index=True)
    else:
        st.info("No sales have been recorded yet.")


# ============================================================
# MORE PAGE — replaces Settings and contains settings + add history
# ============================================================

elif st.session_state.page == "More":
    st.markdown('<h1 class="page-title">Settings</h1>', unsafe_allow_html=True)
    st.caption("POS configuration and recently added inventory.")

    with st.container(key="form_card", border=True):
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
        st.info(
            "Recently-added history is ready in the project, but your inventory table needs the one-time added_at upgrade. "
            "Run pos_inventory_history_upgrade.sql once in Databricks SQL."
        )
    elif not recent:
        st.info("No recently added products yet.")
    else:
        st.dataframe(recent, use_container_width=True, hide_index=True)


# ============================================================
# BOTTOM NAVIGATION — replaces the hamburger menu
# ============================================================

render_bottom_navigation()
