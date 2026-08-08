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
# PAGE / SESSION
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
    "selected_sku": None,
    "payment_method": "CASH",
    "apply_card_fee": True,
    "last_receipt": None,
    "show_receipt": False,
    "dark_mode": True,
    "manage_sku": None,
    # Quick-add terminal state
    "quick_value": "0",
    # Separate Streamlit widget buffer. Never bind the visible input
    # directly to quick_value; quick_value is the POS/business value.
    "quick_input_widget": "0",
    "quick_input_sync_pending": False,
    "quick_qty": 1,
    "quick_tax": "NONE",
    "quick_mode": "PRICE",           # PRICE | CUSTOM_TAX
    "quick_pending_price": 0.0,
    "quick_pending_qty": 1,
    "quick_message": "Enter a price, then tap a tax to add instantly.",
    "editing_cart_index": None,
    "cash_received": 0.0,
    "reset_cash_pending": False,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Always open a new session in dark mode. The user can switch modes from More.
if "theme_initialized_v4" not in st.session_state:
    st.session_state.dark_mode = True
    st.session_state.theme_initialized_v4 = True

# Streamlit widget keys can only be changed safely before their widget
# is instantiated. Button actions set this flag; the next rerun applies
# the value here, before the Quick Entry input is rendered.
if st.session_state.get("quick_input_sync_pending"):
    st.session_state.quick_input_widget = str(
        st.session_state.get("quick_value", "0") or "0"
    )
    st.session_state.quick_input_sync_pending = False

if st.session_state.get("reset_cash_pending"):
    st.session_state.cash_received = 0.0
    st.session_state.reset_cash_pending = False


# ============================================================
# THEME / CSS
# ============================================================


def theme_vars():
    if st.session_state.dark_mode:
        return """
        :root {
          --bg:#07111f;
          --panel:#0d1a2b;
          --panel-2:#112239;
          --panel-3:#152942;
          --input:#081524;
          --text:#f7fbff;
          --muted:#9eafc5;
          --line:#25405f;
          --line-bright:#2c5c94;
          --navy:#0f438d;
          --navy-hi:#1d67d4;
          --green:#0b8a3d;
          --green-hi:#2fc553;
          --blue:#0c58c7;
          --blue-hi:#258cff;
          --purple:#5b2a9c;
          --purple-hi:#8747dc;
          --orange:#b96b00;
          --orange-hi:#f0a321;
          --red:#b91f2b;
          --red-hi:#ef3d40;
          --success-bg:#0b3d25;
          --success-text:#5df39b;
          --shadow:0 18px 42px rgba(0,0,0,.34);
          --soft-shadow:0 8px 20px rgba(0,0,0,.22);
        }
        """

    return """
    :root {
      --bg:#eef3f8;
      --panel:#ffffff;
      --panel-2:#f6f9fc;
      --panel-3:#edf4fb;
      --input:#ffffff;
      --text:#101827;
      --muted:#637086;
      --line:#d7e0ea;
      --line-bright:#8eb5e4;
      --navy:#163f7a;
      --navy-hi:#2872d8;
      --green:#158a49;
      --green-hi:#32bd68;
      --blue:#1e60c8;
      --blue-hi:#3b8df0;
      --purple:#6b36ad;
      --purple-hi:#9560df;
      --orange:#bd7200;
      --orange-hi:#efa523;
      --red:#c33139;
      --red-hi:#ef5357;
      --success-bg:#e8f8ef;
      --success-text:#137444;
      --shadow:0 16px 36px rgba(35,54,78,.12);
      --soft-shadow:0 7px 18px rgba(35,54,78,.08);
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


def set_cash_received(amount):
    """Set cash tendered from POS quick-cash buttons."""
    st.session_state.cash_received = max(float(amount), 0.0)


def quick_numeric_value():
    try:
        return float(st.session_state.quick_value or 0)
    except (TypeError, ValueError):
        return 0.0


def quick_display_value():
    raw = str(st.session_state.quick_value or "0")
    if st.session_state.quick_mode == "CUSTOM_TAX":
        if raw == "0":
            return "0.00%"
        return f"{raw}%"
    if raw == "0":
        return "0.00"
    return raw


def request_quick_input_sync():
    """Synchronize the visible Quick Entry field on the next rerun."""
    st.session_state.quick_input_sync_pending = True


def quick_keypad_press(value):
    current = str(st.session_state.get("quick_value", "0"))

    if value == "C":
        st.session_state.quick_value = "0"
        request_quick_input_sync()
        return

    if value == "⌫":
        trimmed = current[:-1]
        st.session_state.quick_value = trimmed if trimmed not in ("", "-") else "0"
        request_quick_input_sync()
        return

    if value == ".":
        if "." not in current:
            st.session_state.quick_value = current + "."
            request_quick_input_sync()
        return

    if not value.isdigit():
        return

    # Currency/tax entry is intentionally limited to 2 decimal places.
    if "." in current and len(current.split(".", 1)[1]) >= 2:
        return

    if current == "0":
        st.session_state.quick_value = value
    else:
        st.session_state.quick_value = current + value

    request_quick_input_sync()


def normalize_quick_keyboard_input():
    """Copy physical-keyboard input into the POS value safely."""
    raw = str(st.session_state.get("quick_input_widget", "") or "")
    raw = raw.replace("$", "").replace("%", "").replace(",", "").strip()

    cleaned = []
    dot_seen = False

    for ch in raw:
        if ch.isdigit():
            cleaned.append(ch)
        elif ch == "." and not dot_seen:
            cleaned.append(ch)
            dot_seen = True

    value = "".join(cleaned)

    if value.startswith("."):
        value = "0" + value

    if "." in value:
        whole, decimals = value.split(".", 1)
        value = f"{whole or '0'}.{decimals[:2]}"

    if value == "":
        value = "0"

    st.session_state.quick_value = value

    # If we stripped invalid characters or trimmed decimals, update the
    # visible field safely at the beginning of the rerun.
    if value != raw:
        request_quick_input_sync()

def quick_qty_adjust(delta):
    st.session_state.quick_qty = max(1, int(st.session_state.quick_qty) + int(delta))


def tax_rate_for_type(tax_type, custom_rate, settings):
    tax_type = (tax_type or "NONE").upper()
    if tax_type == "LOW":
        return float(settings.get("LOW_TAX", 0.0))
    if tax_type == "HIGH":
        return float(settings.get("HIGH_TAX", 0.0))
    if tax_type == "CUSTOM":
        return float(custom_rate or 0.0)
    return 0.0


def tax_badge(item, settings):
    tax_type = (item.get("tax_type") or "NONE").upper()
    rate = tax_rate_for_type(tax_type, item.get("custom_tax_rate", 0.0), settings)
    if tax_type == "LOW":
        return "Low Tax", rate, "tax-badge-low"
    if tax_type == "HIGH":
        return "High Tax", rate, "tax-badge-high"
    if tax_type == "CUSTOM":
        return "Custom Tax", rate, "tax-badge-custom"
    return "No Tax", 0.0, "tax-badge-none"


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


def add_quick_item(tax_type=None, custom_rate=0.0):
    price = quick_numeric_value()
    qty = int(st.session_state.quick_qty)
    tax_type = (tax_type or st.session_state.quick_tax or "NONE").upper()

    if tax_type == "CUSTOM" and st.session_state.quick_mode == "PRICE":
        return start_custom_tax_entry()

    if price <= 0:
        st.session_state.quick_message = "Enter a price greater than $0.00."
        return False

    st.session_state.cart.append(
        {
            "sku": f"MANUAL-{uuid.uuid4().hex[:6].upper()}",
            "product": "Custom Item",
            "price": float(price),
            "quantity": qty,
            "stock": None,
            "item_fee": 0.0,
            "tax_type": tax_type,
            "custom_tax_rate": float(custom_rate),
            "image_data": None,
            "manual": True,
        }
    )

    st.session_state.quick_value = "0"
    request_quick_input_sync()
    st.session_state.quick_qty = 1
    st.session_state.quick_tax = "NONE"
    st.session_state.quick_mode = "PRICE"
    st.session_state.quick_pending_price = 0.0
    st.session_state.quick_pending_qty = 1
    st.session_state.quick_message = "Item added. Enter the next price."
    return True


def start_custom_tax_entry():
    price = quick_numeric_value()
    if price <= 0:
        st.session_state.quick_tax = "CUSTOM"
        st.session_state.quick_message = "Enter the item price first, then choose Custom Tax."
        return False

    st.session_state.quick_pending_price = price
    st.session_state.quick_pending_qty = int(st.session_state.quick_qty)
    st.session_state.quick_tax = "CUSTOM"
    st.session_state.quick_mode = "CUSTOM_TAX"
    st.session_state.quick_value = "0"
    request_quick_input_sync()
    st.session_state.quick_message = "Enter the custom tax %, then press ADD ITEM."
    return True


def finish_custom_tax_item():
    rate = quick_numeric_value()
    price = float(st.session_state.quick_pending_price or 0.0)
    qty = int(st.session_state.quick_pending_qty or 1)

    if price <= 0:
        st.session_state.quick_mode = "PRICE"
        st.session_state.quick_message = "Enter the item price first."
        return False

    if rate < 0:
        st.session_state.quick_message = "Tax rate cannot be negative."
        return False

    st.session_state.cart.append(
        {
            "sku": f"MANUAL-{uuid.uuid4().hex[:6].upper()}",
            "product": "Custom Item",
            "price": price,
            "quantity": qty,
            "stock": None,
            "item_fee": 0.0,
            "tax_type": "CUSTOM",
            "custom_tax_rate": rate,
            "image_data": None,
            "manual": True,
        }
    )
    st.session_state.quick_value = "0"
    request_quick_input_sync()
    st.session_state.quick_qty = 1
    st.session_state.quick_tax = "NONE"
    st.session_state.quick_mode = "PRICE"
    st.session_state.quick_pending_price = 0.0
    st.session_state.quick_pending_qty = 1
    st.session_state.quick_message = "Custom-tax item added."
    return True


def cancel_custom_tax():
    price = float(st.session_state.quick_pending_price or 0.0)
    st.session_state.quick_value = str(price).rstrip("0").rstrip(".") if price else "0"
    request_quick_input_sync()
    st.session_state.quick_qty = int(st.session_state.quick_pending_qty or 1)
    st.session_state.quick_mode = "PRICE"
    st.session_state.quick_pending_price = 0.0
    st.session_state.quick_pending_qty = 1
    st.session_state.quick_message = "Custom tax canceled."


def exact_scan_submit():
    """Barcode scanners usually send Enter; exact SKU/barcode matches add automatically."""
    term = str(st.session_state.get("pos_search", "") or "").strip()
    if not term:
        return

    results = search_products(term, limit=8)
    exact = next(
        (
            row
            for row in results
            if str(row.get("sku") or "").lower() == term.lower()
            or str(row.get("barcode") or "") == term
        ),
        None,
    )
    if exact:
        ok, msg = add_product_to_cart(exact, 1)
        st.session_state.quick_message = msg
        st.session_state.selected_sku = exact["sku"]
        if ok:
            st.session_state.pos_search = ""


# ============================================================
# HEADER / NAVIGATION
# ============================================================


def render_header():
    with st.container(key="topbar"):
        brand_col, terminal_col, nav_col = st.columns(
            [3.2, 1.55, 3.25],
            vertical_alignment="center",
            gap="medium",
        )

        with brand_col:
            st.markdown(
                '<div class="brand-lockup"><span class="brand-mark">DT</span><span class="brand-name">Retail POS</span></div>',
                unsafe_allow_html=True,
            )

        with terminal_col:
            now = datetime.now()
            st.markdown(
                f'<div class="header-clock"><span>◷</span><div><b>{now.strftime("%b %d, %Y")}</b><small>{now.strftime("%I:%M %p")}</small></div></div>',
                unsafe_allow_html=True,
            )

        with nav_col:
            n1, n2, n3, n4 = st.columns([1, 1.15, 1, 1], gap="small")
            if n1.button("▥  POS", key="top_pos", use_container_width=True):
                goto("POS")
                st.rerun()
            if n2.button("⌕  Inventory", key="top_inventory", use_container_width=True):
                goto("Inventory")
                st.rerun()
            if n3.button("＋  Add", key="top_add", use_container_width=True):
                goto("Add Item")
                st.rerun()

            with n4.popover("⋮  More", use_container_width=True):
                st.markdown('<div class="more-menu-title">DT Retail POS</div>', unsafe_allow_html=True)
                if st.button("Manage Items", key="menu_manage", use_container_width=True):
                    goto("Manage Item")
                    st.rerun()
                if st.button("Sales History", key="menu_history", use_container_width=True):
                    goto("Sales History")
                    st.rerun()
                if st.button("Settings", key="menu_settings", use_container_width=True):
                    goto("Settings")
                    st.rerun()
                st.divider()
                st.toggle("Dark mode", key="dark_mode")
                st.caption(datetime.now().strftime("%b %d, %Y · %I:%M %p"))


# ============================================================
# CART UI
# ============================================================


def render_manual_icon():
    return """
    <div class="manual-thumb">
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <path d="M12 34L34 12h16l2 16-22 22L12 34z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
        <circle cx="42" cy="22" r="3" fill="currentColor"/>
      </svg>
    </div>
    """


def render_cart_item(index, item, settings):
    badge_name, badge_rate, badge_class = tax_badge(item, settings)

    with st.container(key=f"cart_row_{index}"):
        img_col, info_col, qty_group_col, total_col, edit_col, remove_col = st.columns(
            [0.82, 3.0, 1.8, 1.15, 0.78, 0.78],
            vertical_alignment="center",
            gap="small",
        )

        if item.get("manual"):
            img_col.markdown(render_manual_icon(), unsafe_allow_html=True)
            subtitle = "Manual Entry"
        else:
            img_col.markdown(
                image_markup(item.get("image_data"), item["product"], "cart-thumb", "thumb"),
                unsafe_allow_html=True,
            )
            subtitle = f'SKU: {esc(item["sku"])}'

        info_col.markdown(
            f"""
            <div class="cart-item-copy">
              <b>{esc(item['product'])}</b>
              <small>{subtitle}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Compact POS-style quantity stepper: [-] qty [+]
        with qty_group_col:
            with st.container(key=f"qty_stepper_{index}"):
                q_minus, q_value, q_plus = st.columns([1, 0.72, 1], gap="small", vertical_alignment="center")

                if q_minus.button("−", key=f"cart_minus_{index}", use_container_width=True):
                    item["quantity"] -= 1
                    if item["quantity"] <= 0:
                        st.session_state.cart.pop(index)
                        if st.session_state.editing_cart_index == index:
                            st.session_state.editing_cart_index = None
                    st.rerun()

                q_value.markdown(
                    f'<div class="cart-qty">{int(item["quantity"])}</div>',
                    unsafe_allow_html=True,
                )

                if q_plus.button("+", key=f"cart_plus_{index}", use_container_width=True):
                    if item.get("manual") or int(item["quantity"]) < int(item.get("stock") or 0):
                        item["quantity"] += 1
                        st.rerun()
                    else:
                        st.toast("No more stock available.")

        total_col.markdown(
            f"""
            <div class="cart-line-total">
              <b>{money(float(item['price']) * int(item['quantity']))}</b>
              <span class="tax-badge {badge_class}">{badge_name}{f' {badge_rate:.2f}%' if badge_rate else ''}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        edit_open = st.session_state.editing_cart_index == index
        if edit_col.button(
            "Edit" if not edit_open else "Close",
            key=f"cart_edit_toggle_{index}",
            use_container_width=True,
        ):
            st.session_state.editing_cart_index = None if edit_open else index
            st.rerun()

        if remove_col.button("Remove", key=f"cart_remove_{index}", use_container_width=True):
            st.session_state.cart.pop(index)
            st.session_state.editing_cart_index = None
            st.rerun()

        # Inline editor avoids Streamlit popover arrows and keeps the row predictable.
        if st.session_state.editing_cart_index == index:
            with st.container(key=f"cart_editor_{index}"):
                st.markdown('<div class="cart-editor-title">Edit item</div>', unsafe_allow_html=True)

                with st.form(key=f"cart_edit_form_{index}"):
                    e1, e2, e3 = st.columns([1.55, 1, 1], gap="medium")

                    with e1:
                        edit_name = item["product"]
                        if item.get("manual"):
                            edit_name = st.text_input(
                                "Description",
                                value=item["product"],
                                key=f"edit_name_{index}",
                            )
                            edit_price = st.number_input(
                                "Price",
                                min_value=0.01,
                                value=float(item["price"]),
                                step=0.01,
                                format="%.2f",
                                key=f"edit_price_{index}",
                            )
                        else:
                            st.text_input(
                                "Product",
                                value=item["product"],
                                disabled=True,
                                key=f"edit_product_readonly_{index}",
                            )
                            edit_price = float(item["price"])
                            st.caption(f"Inventory price: {money(edit_price)}")

                    with e2:
                        edit_tax_options = ["NONE", "LOW", "HIGH", "CUSTOM"]
                        current_tax = (item.get("tax_type") or "NONE").upper()
                        if current_tax not in edit_tax_options:
                            current_tax = "NONE"
                        edit_tax = st.selectbox(
                            "Tax",
                            edit_tax_options,
                            index=edit_tax_options.index(current_tax),
                            key=f"edit_tax_{index}",
                        )

                        edit_custom = float(item.get("custom_tax_rate") or 0.0)
                        if edit_tax == "CUSTOM":
                            edit_custom = st.number_input(
                                "Custom Tax %",
                                min_value=0.0,
                                value=edit_custom,
                                step=0.1,
                                format="%.2f",
                                key=f"edit_custom_tax_{index}",
                            )

                    with e3:
                        edit_fee = st.number_input(
                            "Item Fee",
                            min_value=0.0,
                            value=float(item.get("item_fee") or 0.0),
                            step=0.01,
                            format="%.2f",
                            key=f"edit_fee_{index}",
                        )

                    save_col, cancel_col = st.columns(2, gap="small")
                    save_changes = save_col.form_submit_button(
                        "Save Changes",
                        type="primary",
                        use_container_width=True,
                    )
                    cancel_changes = cancel_col.form_submit_button(
                        "Cancel",
                        use_container_width=True,
                    )

                    if save_changes:
                        item["product"] = edit_name.strip() or item["product"]
                        item["price"] = float(edit_price)
                        item["tax_type"] = edit_tax
                        item["custom_tax_rate"] = float(edit_custom if edit_tax == "CUSTOM" else 0.0)
                        item["item_fee"] = float(edit_fee)
                        st.session_state.editing_cart_index = None
                        st.rerun()

                    if cancel_changes:
                        st.session_state.editing_cart_index = None
                        st.rerun()


# ============================================================
# DATA
# ============================================================

render_header()
settings = get_settings()
low_tax = float(settings.get("LOW_TAX", 0.0))
high_tax = float(settings.get("HIGH_TAX", 0.0))
card_fee = float(settings.get("CARD_FEE", 0.0))
summary = get_dashboard_summary()


# ============================================================
# POS PAGE
# ============================================================

if st.session_state.page == "POS":
    left, right = st.columns([0.93, 1.07], gap="medium")

    # --------------------------------------------------------
    # QUICK ADD / SEARCH
    # --------------------------------------------------------
    with left:
        with st.container(key="quick_panel"):
            st.markdown('<div class="panel-title"><span class="bolt">ϟ</span> QUICK ADD ITEM</div>', unsafe_allow_html=True)

            mode_label = "CUSTOM TAX %" if st.session_state.quick_mode == "CUSTOM_TAX" else "PRICE"

            # Keyboard + touchscreen share the same large POS entry display.
            # The visible Streamlit widget uses quick_input_widget, while
            # quick_value remains independent POS/business state.
            with st.container(key="quick_entry_display"):
                st.markdown(
                    f'<div class="quick-display-label">{mode_label}</div>',
                    unsafe_allow_html=True,
                )
                st.text_input(
                    "Quick Entry",
                    key="quick_input_widget",
                    label_visibility="collapsed",
                    placeholder="0.00%" if st.session_state.quick_mode == "CUSTOM_TAX" else "0.00",
                    on_change=normalize_quick_keyboard_input,
                )
                st.markdown(
                    f'<div class="quick-qty-chip">Qty&nbsp; {int(st.session_state.quick_qty)}</div>',
                    unsafe_allow_html=True,
                )

            search_text = st.text_input(
                "Scan / Search",
                placeholder="Scan a barcode or type a SKU / product name",
                label_visibility="collapsed",
                key="pos_search",
                on_change=exact_scan_submit,
            )

            matches = search_products(search_text, limit=6) if search_text.strip() else []

            if matches:
                st.markdown('<div class="suggestions-title">Inventory Suggestions</div>', unsafe_allow_html=True)
                suggestion_cols = st.columns(min(3, len(matches)), gap="small")
                for idx, row in enumerate(matches[:3]):
                    with suggestion_cols[idx]:
                        with st.container(key=f"suggestion_card_{idx}"):
                            p1, p2 = st.columns([0.75, 1.65], gap="small", vertical_alignment="center")
                            p1.markdown(
                                image_markup(row.get("image_data"), row["product"], "suggestion-thumb", "thumb"),
                                unsafe_allow_html=True,
                            )
                            p2.markdown(
                                f"""
                                <div class="suggestion-card-copy">
                                  <b>{esc(row['product'])}</b>
                                  <small>{esc(row['sku'])}</small>
                                  <span>{money(row['price'])} · Stock {int(row['quantity'])}</span>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                            b1, b2 = st.columns(2, gap="small")
                            if b1.button("View", key=f"sview_{row['sku']}", use_container_width=True):
                                st.session_state.selected_sku = row["sku"]
                                st.rerun()
                            if b2.button(
                                "+ Add",
                                key=f"sadd_{row['sku']}",
                                use_container_width=True,
                                type="primary",
                                disabled=int(row["quantity"]) <= 0,
                            ):
                                ok, msg = add_product_to_cart(row, 1)
                                if ok:
                                    st.session_state.selected_sku = row["sku"]
                                    st.session_state.quick_message = msg
                                    st.rerun()
                                st.error(msg)

                selected = next(
                    (row for row in matches if row["sku"] == st.session_state.selected_sku),
                    None,
                )
                if selected:
                    with st.container(key="selected_product"):
                        pc1, pc2, pc3 = st.columns([0.95, 1.75, 1.15], gap="medium", vertical_alignment="center")
                        pc1.markdown(
                            image_markup(selected.get("image_data"), selected["product"], "selected-product-image", "detail"),
                            unsafe_allow_html=True,
                        )
                        pc2.markdown(
                            f"""
                            <div class="selected-copy">
                              <h3>{esc(selected['product'])}</h3>
                              <div><span>SKU</span><b>{esc(selected['sku'])}</b></div>
                              <div><span>Barcode</span><b>{esc(selected['barcode'] or '—')}</b></div>
                              <div><span>Price</span><b>{money(selected['price'])}</b></div>
                              <div><span>Stock</span><b class="stock-green">{int(selected['quantity'])}</b></div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        with pc3:
                            selected_qty = st.number_input(
                                "Quantity",
                                min_value=1,
                                max_value=max(int(selected["quantity"]), 1),
                                value=1,
                                step=1,
                                key=f"selected_qty_{selected['sku']}",
                                disabled=int(selected["quantity"]) <= 0,
                            )
                            if st.button(
                                "🛒 Add to Cart",
                                key=f"selected_add_{selected['sku']}",
                                type="primary",
                                use_container_width=True,
                                disabled=int(selected["quantity"]) <= 0,
                            ):
                                ok, msg = add_product_to_cart(selected, selected_qty)
                                if ok:
                                    st.session_state.quick_message = msg
                                    st.rerun()
                                st.error(msg)
            else:
                st.markdown(
                    '<div class="scan-hint"><span class="barcode-glyph">▥</span><span>Scan a barcode or type a SKU / product name.</span></div>',
                    unsafe_allow_html=True,
                )

            # Tax selector
            st.markdown('<div class="control-label">CHOOSE TAX</div>', unsafe_allow_html=True)
            tax_cols = st.columns(4, gap="small")
            tax_defs = [
                ("NONE", "⊘", "No Tax", "0%", "tax-none"),
                ("LOW", "↻", "Low Tax", f"{low_tax:.2f}%", "tax-low"),
                ("HIGH", "⊘", "High Tax", f"{high_tax:.2f}%", "tax-high"),
                ("CUSTOM", "⚙", "Custom Tax", "…", "tax-custom"),
            ]

            for col, (tax_value, icon, label, rate_text, css_key) in zip(tax_cols, tax_defs):
                active = st.session_state.quick_tax == tax_value
                with col:
                    if st.button(
                        f"{icon}  {label}\n{rate_text}",
                        key=f"quick_tax_{tax_value}",
                        use_container_width=True,
                        type="primary" if active else "secondary",
                    ):
                        if tax_value == "CUSTOM":
                            if start_custom_tax_entry():
                                st.rerun()
                            st.rerun()
                        else:
                            st.session_state.quick_tax = tax_value
                            # Requested workflow: price + tax button = immediate cart add.
                            if st.session_state.quick_mode == "PRICE" and quick_numeric_value() > 0:
                                if add_quick_item(tax_value):
                                    st.rerun()
                            else:
                                st.session_state.quick_message = f"{label} selected. Enter a price and press ADD ITEM."
                                st.rerun()

            # Keypad
            keypad_rows = [
                ["7", "8", "9", "⌫"],
                ["4", "5", "6", "+Q"],
                ["1", "2", "3", "−Q"],
                ["0", ".", "C", "ADD"],
            ]

            for r, row in enumerate(keypad_rows):
                cols = st.columns(4, gap="small")
                for c, key in enumerate(row):
                    if key == "+Q":
                        cols[c].button(
                            f"+\nQty {int(st.session_state.quick_qty)}",
                            key=f"keypad_{r}_{c}",
                            use_container_width=True,
                            on_click=quick_qty_adjust,
                            args=(1,),
                        )
                    elif key == "−Q":
                        cols[c].button(
                            "−\nQty",
                            key=f"keypad_{r}_{c}",
                            use_container_width=True,
                            on_click=quick_qty_adjust,
                            args=(-1,),
                        )
                    elif key == "ADD":
                        add_label = "APPLY & ADD" if st.session_state.quick_mode == "CUSTOM_TAX" else "🛒 ADD ITEM"
                        if cols[c].button(add_label, key=f"keypad_{r}_{c}", use_container_width=True, type="primary"):
                            if st.session_state.quick_mode == "CUSTOM_TAX":
                                if finish_custom_tax_item():
                                    st.rerun()
                            else:
                                if add_quick_item(st.session_state.quick_tax):
                                    st.rerun()
                            st.rerun()
                    else:
                        cols[c].button(
                            key,
                            key=f"keypad_{r}_{c}",
                            use_container_width=True,
                            on_click=quick_keypad_press,
                            args=(key,),
                        )

            if st.session_state.quick_mode == "CUSTOM_TAX":
                if st.button("← Cancel custom tax", key="cancel_custom_tax", use_container_width=True):
                    cancel_custom_tax()
                    st.rerun()

            st.markdown(
                f'<div class="terminal-message"><span>✓</span><div>{esc(st.session_state.quick_message)}</div></div>',
                unsafe_allow_html=True,
            )

    # --------------------------------------------------------
    # CART / PAYMENT
    # --------------------------------------------------------
    with right:
        with st.container(key="cart_panel"):
            cart_title, cart_clear = st.columns([4, 1], vertical_alignment="center")
            cart_title.markdown(
                f'<div class="panel-title"><span>🛒</span> CART ({sum(int(i["quantity"]) for i in st.session_state.cart)} ITEMS)</div>',
                unsafe_allow_html=True,
            )
            if cart_clear.button(
                "🗑  Clear Cart",
                key="clear_cart",
                use_container_width=True,
                disabled=not st.session_state.cart,
            ):
                st.session_state.cart = []
                st.rerun()

            # Keep the cart panel compact.
            # Only the cart item list scrolls; totals and payment stay visible.
            if st.session_state.cart:
                with st.container(
                    height=330,
                    border=False,
                    key="cart_items_scroll",
                ):
                    for index, item in enumerate(st.session_state.cart):
                        render_cart_item(index, item, settings)
            else:
                st.markdown(
                    '<div class="empty-cart"><span class="empty-cart-icon">🛒</span><b>Your cart is empty</b><small>Scan inventory or use Quick Add.</small></div>',
                    unsafe_allow_html=True,
                )

            totals = calculate_cart_totals(
                st.session_state.cart,
                st.session_state.payment_method,
                "PRODUCT DEFAULT",
                0.0,
                st.session_state.apply_card_fee,
                settings,
            )

            st.markdown(
                f"""
                <div class="totals-card">
                  <div><span>Subtotal</span><b>{money(totals['subtotal'])}</b></div>
                  <div><span>Product Fees</span><b>{money(totals['fees'])}</b></div>
                  <div class="tax-total"><span>Tax</span><b>{money(totals['tax'])}</b></div>
                  <div><span>Card Fee</span><b>{money(totals['card_fee'])}</b></div>
                  <hr>
                  <div class="grand-total"><span>TOTAL</span><b>{money(totals['total'])}</b></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown('<div class="payment-title">Payment</div>', unsafe_allow_html=True)
            pay_cash, pay_card = st.columns(2, gap="medium")

            if pay_cash.button(
                f"💵  CASH     {money(totals['total'])}",
                key="cash_btn",
                use_container_width=True,
                type="primary" if st.session_state.payment_method == "CASH" else "secondary",
            ):
                st.session_state.payment_method = "CASH"
                st.rerun()

            if pay_card.button(
                f"▣  CARD     {money(totals['total'])}",
                key="card_btn",
                use_container_width=True,
                type="primary" if st.session_state.payment_method == "CARD" else "secondary",
            ):
                st.session_state.payment_method = "CARD"
                st.rerun()

            cash_received = 0.0
            change_due = 0.0

            if st.session_state.payment_method == "CASH":
                st.markdown('<div class="cash-label">Cash Received</div>', unsafe_allow_html=True)

                # POS quick-cash buttons. Callback runs before the number
                # input is created on the rerun, so state updates safely.
                cash_presets = [
                    ("Exact", float(totals["total"])),
                    ("$20", 20.0),
                    ("$50", 50.0),
                    ("$100", 100.0),
                    ("$200", 200.0),
                ]
                preset_cols = st.columns(5, gap="small")
                for col, (label, amount) in zip(preset_cols, cash_presets):
                    col.button(
                        label,
                        key=f"cash_preset_{label.replace('$', '').lower()}",
                        use_container_width=True,
                        on_click=set_cash_received,
                        args=(amount,),
                    )

                st.number_input(
                    "Cash Received Amount",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key="cash_received",
                    label_visibility="collapsed",
                    help="Type an amount and press Enter, or use a quick-cash button above.",
                )

                # Always read the committed widget value from session state.
                cash_received = float(st.session_state.get("cash_received", 0.0) or 0.0)
                change_due = max(cash_received - float(totals["total"]), 0.0)

                st.markdown(
                    f'<div class="change-card"><span>Change Due</span><b>{money(change_due)}</b></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.checkbox(
                    f"Apply Card Fee ({card_fee:.2f}%)",
                    key="apply_card_fee",
                )
                totals = calculate_cart_totals(
                    st.session_state.cart,
                    "CARD",
                    "PRODUCT DEFAULT",
                    0.0,
                    st.session_state.apply_card_fee,
                    settings,
                )
                st.markdown(
                    f'<div class="change-card"><span>Card Total</span><b>{money(totals["total"])}</b></div>',
                    unsafe_allow_html=True,
                )

            action1, action2 = st.columns(2, gap="medium")
            can_complete = bool(st.session_state.cart)
            if st.session_state.payment_method == "CASH" and can_complete:
                can_complete = cash_received >= totals["total"]

            if action1.button(
                "✓  COMPLETE SALE",
                key="complete_sale",
                use_container_width=True,
                type="primary",
                disabled=not can_complete,
            ):
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
                        "cash_received": float(cash_received),
                        "change_due": float(change_due),
                    }
                    st.session_state.cart = []
                    st.session_state.show_receipt = True
                    st.session_state.reset_cash_pending = True
                    st.toast(f"Sale complete · {receipt_id}")
                    st.rerun()

            if action2.button(
                "▣  PRINT RECEIPT",
                key="print_receipt",
                use_container_width=True,
                disabled=st.session_state.last_receipt is None,
            ):
                st.session_state.show_receipt = not st.session_state.show_receipt

            with st.expander("More Options", expanded=False):
                st.caption("Cart and checkout controls")
                m1, m2 = st.columns(2)
                if m1.button("Inventory", key="cart_inventory", use_container_width=True):
                    goto("Inventory")
                    st.rerun()
                if m2.button("Settings", key="cart_settings", use_container_width=True):
                    goto("Settings")
                    st.rerun()

            if st.session_state.show_receipt and st.session_state.last_receipt:
                with st.expander("Receipt Preview", expanded=True):
                    components.html(
                        build_receipt_html(st.session_state.last_receipt),
                        height=560,
                        scrolling=True,
                    )


# ============================================================
# INVENTORY
# ============================================================

elif st.session_state.page == "Inventory":
    st.markdown('<div class="page-heading"><span>Inventory</span><small>Search stock and send products directly to the POS.</small></div>', unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4, gap="medium")
    m1.metric("Products", summary["products"])
    m2.metric("Units in Stock", summary["units"])
    m3.metric("Inventory Value", money(summary["inventory_value"]))
    m4.metric("Sales Revenue", money(summary["revenue"]))

    with st.container(key="inventory_search_card"):
        inventory_search = st.text_input(
            "Search Inventory",
            placeholder="Search product, SKU, barcode, or category",
            key="inventory_search",
        )

    inventory = search_products(inventory_search, limit=50) if inventory_search.strip() else list_inventory()

    if not inventory:
        st.info("No inventory matches found.")

    for item in inventory:
        with st.container(key=f"inventory_row_{item['sku']}"):
            i1, i2, i3, i4, i5, i6 = st.columns(
                [0.78, 2.7, 0.92, 0.92, 1.05, 1.2],
                vertical_alignment="center",
                gap="small",
            )
            i1.markdown(
                image_markup(item.get("image_data"), item["product"], "inventory-thumb", "thumb"),
                unsafe_allow_html=True,
            )
            i2.markdown(
                f'<div class="inventory-copy"><b>{esc(item["product"])}</b><small>{esc(item["sku"])} · {esc(item["barcode"] or "No barcode")}</small></div>',
                unsafe_allow_html=True,
            )
            i3.metric("Stock", int(item["quantity"]))
            i4.metric("Price", money(item["price"]))
            i5.metric("Value", money(float(item["quantity"]) * float(item["price"])))
            stock_qty = int(item["quantity"])
            label = "Restock" if stock_qty <= 0 else "+ Add to POS"
            if i6.button(
                label,
                key=f"inv_action_{item['sku']}",
                use_container_width=True,
                type="primary" if stock_qty > 0 else "secondary",
            ):
                if stock_qty <= 0:
                    st.session_state.manage_sku = item["sku"]
                    goto("Manage Item")
                    st.rerun()
                ok, msg = add_product_to_cart(item, 1)
                if ok:
                    goto("POS")
                    st.session_state.quick_message = msg
                    st.rerun()
                st.error(msg)


# ============================================================
# ADD ITEM
# ============================================================

elif st.session_state.page == "Add Item":
    st.markdown('<div class="page-heading"><span>Add Item</span><small>Create a new inventory product.</small></div>', unsafe_allow_html=True)

    with st.container(key="form_card"):
        form, photo = st.columns([1.55, 1], gap="large")
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
            st.markdown('<div class="form-section-title">Product Picture</div>', unsafe_allow_html=True)
            uploaded = st.file_uploader("Upload product picture", type=["png", "jpg", "jpeg"])
            preview = prepare_image_data(uploaded) if uploaded else None
            st.markdown(
                image_markup(preview, product or "Product", "upload-preview", "detail"),
                unsafe_allow_html=True,
            )

        if st.button("＋ ADD PRODUCT", key="add_product", type="primary", use_container_width=True):
            clean_sku = sku.strip().upper()
            clean_product = product.strip()
            clean_category = category.strip()
            clean_barcode = barcode.strip()
            if not clean_sku or not clean_product or not clean_category:
                st.error("SKU, product name, and category are required.")
            else:
                ok, msg = add_inventory_item(
                    clean_sku,
                    clean_barcode,
                    clean_product,
                    clean_category,
                    quantity,
                    price,
                    item_fee,
                    tax_type,
                    custom_tax_rate,
                    preview,
                )
                if ok:
                    st.success("Product added successfully.")
                else:
                    st.error(msg)


# ============================================================
# MANAGE ITEM
# ============================================================

elif st.session_state.page == "Manage Item":
    st.markdown('<div class="page-heading"><span>Manage Item</span><small>Edit stock, price, tax, barcode, or product picture.</small></div>', unsafe_allow_html=True)
    inventory = list_inventory()

    if not inventory:
        st.info("No inventory items found.")
    else:
        options = {f'{row["sku"]} — {row["product"]}': row for row in inventory}
        labels = list(options.keys())
        requested_sku = st.session_state.get("manage_sku")
        selected_index = 0
        if requested_sku:
            for idx, label in enumerate(labels):
                if options[label]["sku"] == requested_sku:
                    selected_index = idx
                    break

        selected_label = st.selectbox("Select Item", labels, index=selected_index, key="manage_selector")
        item = options[selected_label]
        st.session_state.manage_sku = item["sku"]

        with st.container(key="form_card"):
            photo, edit = st.columns([1, 2], gap="large")
            with photo:
                st.markdown('<div class="form-section-title">Product Picture</div>', unsafe_allow_html=True)
                st.markdown(
                    image_markup(item.get("image_data"), item["product"], "manage-preview", "detail"),
                    unsafe_allow_html=True,
                )
                new_image_file = st.file_uploader(
                    "Change product picture",
                    type=["png", "jpg", "jpeg"],
                    key=f"img_{item['sku']}",
                )
                remove_image = st.checkbox("Remove current picture", key=f"remove_img_{item['sku']}")

            with edit:
                new_barcode = st.text_input("Barcode", value=item["barcode"] or "", key=f"bar_{item['sku']}")
                new_quantity = st.number_input(
                    "Stock Quantity",
                    min_value=0,
                    value=int(item["quantity"]),
                    step=1,
                    key=f"qty_{item['sku']}",
                )
                new_price = st.number_input(
                    "Price",
                    min_value=0.01,
                    value=float(item["price"]),
                    step=0.01,
                    format="%.2f",
                    key=f"price_{item['sku']}",
                )
                new_fee = st.number_input(
                    "Item Fee",
                    min_value=0.0,
                    value=float(item["item_fee"] or 0),
                    step=0.01,
                    format="%.2f",
                    key=f"fee_{item['sku']}",
                )
                tax_options = ["NONE", "LOW", "HIGH", "CUSTOM"]
                current_tax = item["tax_type"] if item["tax_type"] in tax_options else "NONE"
                new_tax_type = st.selectbox(
                    "Tax Type",
                    tax_options,
                    index=tax_options.index(current_tax),
                    key=f"tax_{item['sku']}",
                )
                new_custom_tax = float(item["custom_tax_rate"] or 0)
                if new_tax_type == "CUSTOM":
                    new_custom_tax = st.number_input(
                        "Custom Tax %",
                        min_value=0.0,
                        value=new_custom_tax,
                        step=0.1,
                        format="%.2f",
                        key=f"custom_{item['sku']}",
                    )

            if st.button("✓ SAVE CHANGES", key="save_changes", type="primary", use_container_width=True):
                if new_image_file:
                    new_image_data = prepare_image_data(new_image_file)
                    keep_existing = False
                elif remove_image:
                    new_image_data = None
                    keep_existing = False
                else:
                    new_image_data = None
                    keep_existing = True

                update_inventory_item(
                    item["sku"],
                    new_barcode.strip(),
                    new_quantity,
                    new_price,
                    new_fee,
                    new_tax_type,
                    new_custom_tax,
                    new_image_data,
                    keep_existing,
                )
                st.success("Item updated successfully.")
                st.rerun()

            st.divider()
            confirm = st.checkbox(f'I confirm I want to delete {item["product"]}')
            if st.button("🗑 DELETE ITEM", key="delete_item", use_container_width=True):
                if confirm:
                    delete_inventory_item(item["sku"])
                    st.success("Item deleted.")
                    st.rerun()
                st.warning("Confirm deletion first.")


# ============================================================
# SALES HISTORY
# ============================================================

elif st.session_state.page == "Sales History":
    st.markdown('<div class="page-heading"><span>Sales History</span><small>Completed retail transactions.</small></div>', unsafe_allow_html=True)
    sales = list_sales()
    with st.container(key="data_card"):
        if sales:
            st.dataframe(sales, use_container_width=True, hide_index=True)
        else:
            st.info("No sales have been recorded yet.")


# ============================================================
# SETTINGS
# ============================================================

elif st.session_state.page == "Settings":
    st.markdown('<div class="page-heading"><span>Settings</span><small>Configure taxes, card fees, and display preferences.</small></div>', unsafe_allow_html=True)

    with st.container(key="form_card"):
        st.markdown('<div class="form-section-title">POS Settings</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3, gap="medium")
        new_low_tax = c1.number_input("Low Tax %", min_value=0.0, value=low_tax, step=0.1, format="%.2f")
        new_high_tax = c2.number_input("High Tax %", min_value=0.0, value=high_tax, step=0.1, format="%.2f")
        new_card_fee = c3.number_input("Card Fee %", min_value=0.0, value=card_fee, step=0.1, format="%.2f")
        if st.button("✓ SAVE SETTINGS", key="save_settings", type="primary", use_container_width=True):
            update_settings(new_low_tax, new_high_tax, new_card_fee)
            st.success("Settings saved.")
            st.rerun()

    st.markdown('<div class="section-spacer"></div><div class="form-section-title">Recently Added Inventory</div>', unsafe_allow_html=True)
    recent = list_recent_additions(25)
    with st.container(key="data_card"):
        if recent is None:
            st.info("Run pos_inventory_history_upgrade.sql once to enable added-date history.")
        elif recent:
            st.dataframe(recent, use_container_width=True, hide_index=True)
        else:
            st.info("No recently added products yet.")