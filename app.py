import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from pos_service import (
    add_inventory_item,
    calculate_cart_totals,
    complete_sale,
    delete_inventory_item,
    get_dashboard_summary,
    get_settings,
    list_inventory,
    list_sales,
    search_products,
    update_inventory_item,
    update_settings,
    validate_cart_stock,
)
from receipt import build_receipt_html


# ============================================================
# APP SHELL / PRESENTATION
# ============================================================

st.set_page_config(
    page_title="DT Retail POS",
    page_icon="🛒",
    layout="wide",
)


def load_css(filename="styles.css"):
    css_path = Path(__file__).with_name(filename)
    st.markdown(
        f"<style>{css_path.read_text(encoding='utf-8')}</style>",
        unsafe_allow_html=True,
    )


load_css()

st.title("DT Retail POS")
st.caption(
    "Retail inventory, checkout, sales history, and configurable POS settings powered by Databricks"
)


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "cart": [],
    "qty_buffer": "1",
    "payment_method": "CASH",
    "tax_override": "PRODUCT DEFAULT",
    "custom_tax_override": 0.0,
    "apply_card_fee": True,
    "last_receipt": None,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# SETTINGS + SUMMARY
# ============================================================

settings = get_settings()
low_tax = settings.get("LOW_TAX", 0.0)
high_tax = settings.get("HIGH_TAX", 0.0)
card_fee = settings.get("CARD_FEE", 0.0)

summary = get_dashboard_summary()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Products", summary["products"])
m2.metric("Units in Stock", summary["units"])
m3.metric("Inventory Value", f'${summary["inventory_value"]:,.2f}')
m4.metric("Recorded Sales", f'${summary["revenue"]:,.2f}')


# ============================================================
# TABS
# ============================================================

pos_tab, inventory_tab, add_tab, manage_tab, history_tab, settings_tab = st.tabs(
    [
        "POS",
        "Inventory",
        "Add Item",
        "Manage Item",
        "Sales History",
        "Settings",
    ]
)


# ============================================================
# POS TAB
# ============================================================

with pos_tab:
    left, right = st.columns([1, 1.18], gap="large")

    # --------------------------------------------------------
    # LEFT: SEARCH / SCAN + KEYPAD + QUICK TAX
    # --------------------------------------------------------
    with left:
        st.subheader("Search / Scan Item")

        search_text = st.text_input(
            "Barcode / SKU / Product Name",
            placeholder="Scan barcode or type SKU / product name",
            label_visibility="collapsed",
            key="pos_search",
        )

        matches = search_products(search_text)
        selected_product = None

        if matches:
            options = {
                f'{row["sku"]} — {row["product"]} | ${float(row["price"]):.2f} | Stock {int(row["quantity"])}': row
                for row in matches
            }

            selected_label = st.selectbox(
                "Matching items",
                list(options.keys()),
                label_visibility="collapsed",
            )
            selected_product = options[selected_label]

            st.markdown(
                f"""
                <div class="pos-card">
                    <h3 style="margin:0 0 10px 0;">{selected_product['product']}</h3>
                    <div><b>SKU:</b> {selected_product['sku']}</div>
                    <div><b>Barcode:</b> {selected_product['barcode'] or 'Not assigned'}</div>
                    <div><b>Category:</b> {selected_product['category']}</div>
                    <div><b>Price:</b> ${float(selected_product['price']):.2f}</div>
                    <div><b>Stock:</b> {int(selected_product['quantity'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif search_text.strip():
            st.warning("No matching inventory item found.")

        st.markdown("#### Quantity")

        qty_display = st.text_input(
            "Quantity",
            value=st.session_state.qty_buffer,
            key="qty_display",
            label_visibility="collapsed",
        )

        if qty_display.isdigit() and int(qty_display) > 0:
            st.session_state.qty_buffer = qty_display

        keypad = [
            ["7", "8", "9"],
            ["4", "5", "6"],
            ["1", "2", "3"],
            ["C", "0", "⌫"],
        ]

        for row_index, row in enumerate(keypad):
            cols = st.columns(3)
            for col_index, label in enumerate(row):
                if cols[col_index].button(
                    label,
                    key=f"keypad_{row_index}_{col_index}_{label}",
                    use_container_width=True,
                ):
                    if label == "C":
                        st.session_state.qty_buffer = "1"
                    elif label == "⌫":
                        new_value = st.session_state.qty_buffer[:-1]
                        st.session_state.qty_buffer = new_value if new_value else "1"
                    else:
                        if st.session_state.qty_buffer == "1":
                            st.session_state.qty_buffer = label
                        else:
                            st.session_state.qty_buffer += label
                    st.rerun()

        if selected_product:
            requested_qty = max(int(st.session_state.qty_buffer or "1"), 1)

            if st.button("Add to Cart", type="primary", use_container_width=True):
                if requested_qty > int(selected_product["quantity"]):
                    st.error("Not enough stock.")
                else:
                    existing = next(
                        (
                            item
                            for item in st.session_state.cart
                            if item.get("sku") == selected_product["sku"]
                            and not item.get("manual")
                        ),
                        None,
                    )

                    if existing:
                        new_qty = existing["quantity"] + requested_qty
                        if new_qty > int(selected_product["quantity"]):
                            st.error("Cart quantity exceeds available stock.")
                        else:
                            existing["quantity"] = new_qty
                            st.session_state.qty_buffer = "1"
                            st.rerun()
                    else:
                        st.session_state.cart.append(
                            {
                                "sku": selected_product["sku"],
                                "product": selected_product["product"],
                                "price": float(selected_product["price"]),
                                "quantity": requested_qty,
                                "stock": int(selected_product["quantity"]),
                                "item_fee": float(selected_product["item_fee"] or 0),
                                "tax_type": selected_product["tax_type"] or "NONE",
                                "custom_tax_rate": float(
                                    selected_product["custom_tax_rate"] or 0
                                ),
                                "manual": False,
                            }
                        )
                        st.session_state.qty_buffer = "1"
                        st.rerun()

        with st.expander("Manual Price Item"):
            manual_name = st.text_input(
                "Description",
                placeholder="Miscellaneous Item",
                key="manual_name",
            )
            manual_price = st.number_input(
                "Manual Price",
                min_value=0.01,
                step=0.01,
                format="%.2f",
                key="manual_price",
            )
            manual_quantity = st.number_input(
                "Quantity",
                min_value=1,
                step=1,
                key="manual_quantity",
            )
            manual_fee = st.number_input(
                "Item Fee",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="manual_fee",
            )
            manual_tax = st.selectbox(
                "Tax",
                ["NONE", "LOW", "HIGH", "CUSTOM"],
                key="manual_tax",
            )

            manual_custom_tax = 0.0
            if manual_tax == "CUSTOM":
                manual_custom_tax = st.number_input(
                    "Custom Tax %",
                    min_value=0.0,
                    step=0.1,
                    key="manual_custom_tax",
                )

            if st.button("Add Manual Item", use_container_width=True):
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
                            "manual": True,
                        }
                    )
                    st.rerun()

        st.markdown("#### Quick Tax")
        tax_cols = st.columns(5)
        tax_choices = [
            ("No Tax", "NO TAX"),
            ("Low Tax", "LOW TAX"),
            ("High Tax", "HIGH TAX"),
            ("Custom", "CUSTOM TAX"),
            ("Product", "PRODUCT DEFAULT"),
        ]

        for idx, (label, value) in enumerate(tax_choices):
            if tax_cols[idx].button(label, key=f"tax_{value}", use_container_width=True):
                st.session_state.tax_override = value
                st.rerun()

        st.caption(f'Current tax mode: {st.session_state.tax_override}')

        if st.session_state.tax_override == "CUSTOM TAX":
            st.session_state.custom_tax_override = st.number_input(
                "Custom Tax %",
                min_value=0.0,
                value=float(st.session_state.custom_tax_override),
                step=0.1,
                format="%.2f",
                key="pos_custom_tax",
            )

        st.markdown(
            f"""
            <div class="pos-card">
                <b>POS Settings</b><br>
                Low Tax: {low_tax:.2f}% &nbsp;&nbsp;|&nbsp;&nbsp;
                High Tax: {high_tax:.2f}% &nbsp;&nbsp;|&nbsp;&nbsp;
                Card Fee: {card_fee:.2f}%
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------
    # RIGHT: CART + PAYMENT + RECEIPT
    # --------------------------------------------------------
    with right:
        st.subheader("Cart")

        if not st.session_state.cart:
            st.info("Cart is empty.")

        for index, item in enumerate(st.session_state.cart):
            c1, c2, c3, c4, c5 = st.columns([3.2, 1.1, 1.2, 1.4, 0.6])

            c1.markdown(
                f'**{item["product"]}**  \n<span class="muted">SKU: {item["sku"]}</span>',
                unsafe_allow_html=True,
            )

            if c2.button("−", key=f"minus_{index}", use_container_width=True):
                item["quantity"] -= 1
                if item["quantity"] <= 0:
                    st.session_state.cart.pop(index)
                st.rerun()

            c2.markdown(
                f'<div style="text-align:center;font-weight:700;">{item["quantity"]}</div>',
                unsafe_allow_html=True,
            )

            if c2.button("+", key=f"plus_{index}", use_container_width=True):
                if item.get("manual") or item["quantity"] < item["stock"]:
                    item["quantity"] += 1
                    st.rerun()
                else:
                    st.warning("No more stock available.")

            c3.write(f'${float(item["price"]):.2f}')
            line_base = float(item["price"]) * int(item["quantity"])
            c4.write(f"${line_base:,.2f}")

            if c5.button("✕", key=f"remove_{index}", use_container_width=True):
                st.session_state.cart.pop(index)
                st.rerun()

            st.divider()

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
            <div class="total-box">
                <div style="display:flex;justify-content:space-between;"><span>Subtotal</span><b>${totals['subtotal']:,.2f}</b></div>
                <div style="display:flex;justify-content:space-between;"><span>Product Fees</span><b>${totals['fees']:,.2f}</b></div>
                <div style="display:flex;justify-content:space-between;"><span>Tax</span><b>${totals['tax']:,.2f}</b></div>
                <div style="display:flex;justify-content:space-between;"><span>Card Fee</span><b>${totals['card_fee']:,.2f}</b></div>
                <hr>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span class="big-total">Total</span>
                    <span class="big-total">${totals['total']:,.2f}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### Payment")
        pay1, pay2 = st.columns(2)

        if pay1.button(
            "Cash",
            type="primary" if st.session_state.payment_method == "CASH" else "secondary",
            use_container_width=True,
        ):
            st.session_state.payment_method = "CASH"
            st.rerun()

        if pay2.button(
            "Card",
            type="primary" if st.session_state.payment_method == "CARD" else "secondary",
            use_container_width=True,
        ):
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
            st.metric("Change Due", f"${max(change_due, 0):,.2f}")
        else:
            st.session_state.apply_card_fee = st.checkbox(
                f"Apply Card Fee ({card_fee:.2f}%)",
                value=st.session_state.apply_card_fee,
            )
            totals = calculate_cart_totals(
                st.session_state.cart,
                st.session_state.payment_method,
                st.session_state.tax_override,
                st.session_state.custom_tax_override,
                st.session_state.apply_card_fee,
                settings,
            )
            st.metric("Card Total", f'${totals["total"]:,.2f}')

        if st.button(
            "Complete Sale",
            type="primary",
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
                    receipt_id = (
                        "DT-"
                        + datetime.now().strftime("%Y%m%d-")
                        + uuid.uuid4().hex[:6].upper()
                    )

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
                    st.success(f"Sale completed — {receipt_id}")
                    st.rerun()

        if st.session_state.last_receipt:
            st.markdown("#### Last Receipt")
            components.html(
                build_receipt_html(st.session_state.last_receipt),
                height=600,
                scrolling=True,
            )


# ============================================================
# INVENTORY TAB
# ============================================================

with inventory_tab:
    st.subheader("Current Inventory")
    st.dataframe(list_inventory(), use_container_width=True, hide_index=True)


# ============================================================
# ADD ITEM TAB
# ============================================================

with add_tab:
    st.subheader("Add New Inventory Item")

    with st.form("add_item_form"):
        c1, c2 = st.columns(2)

        with c1:
            sku = st.text_input("SKU", placeholder="DT-1005")
            barcode = st.text_input("Barcode", placeholder="100000000005")
            product = st.text_input("Product Name")
            category = st.text_input("Category")

        with c2:
            quantity = st.number_input("Quantity", min_value=0, step=1)
            price = st.number_input("Price", min_value=0.01, step=0.01, format="%.2f")
            item_fee = st.number_input("Item Fee", min_value=0.0, step=0.01, format="%.2f")
            tax_type = st.selectbox("Tax Type", ["NONE", "LOW", "HIGH", "CUSTOM"])

        custom_tax_rate = 0.0
        if tax_type == "CUSTOM":
            custom_tax_rate = st.number_input(
                "Custom Tax %",
                min_value=0.0,
                step=0.1,
                format="%.2f",
            )

        submitted = st.form_submit_button("Add Item")

    if submitted:
        clean_sku = sku.strip().upper()
        clean_barcode = barcode.strip() or None

        if not clean_sku or not product.strip() or not category.strip():
            st.error("SKU, product name, and category are required.")
        else:
            ok, message = add_inventory_item(
                clean_sku,
                clean_barcode,
                product.strip(),
                category.strip(),
                quantity,
                price,
                item_fee,
                tax_type,
                custom_tax_rate,
            )
            if ok:
                st.success(message)
                st.rerun()
            else:
                st.error(message)


# ============================================================
# MANAGE ITEM TAB
# ============================================================

with manage_tab:
    st.subheader("Manage Inventory")
    products = list_inventory()

    if not products:
        st.info("No inventory items.")
    else:
        options = {f'{row["sku"]} — {row["product"]}': row for row in products}
        selected_label = st.selectbox("Select Item", list(options.keys()))
        item = options[selected_label]

        c1, c2 = st.columns(2)

        with c1:
            edit_barcode = st.text_input("Barcode", value=item["barcode"] or "", key="edit_barcode")
            edit_quantity = st.number_input(
                "Quantity",
                min_value=0,
                value=int(item["quantity"]),
                step=1,
                key="edit_quantity",
            )
            edit_price = st.number_input(
                "Price",
                min_value=0.01,
                value=float(item["price"]),
                step=0.01,
                format="%.2f",
                key="edit_price",
            )

        with c2:
            edit_fee = st.number_input(
                "Item Fee",
                min_value=0.0,
                value=float(item["item_fee"]),
                step=0.01,
                format="%.2f",
                key="edit_fee",
            )

            tax_types = ["NONE", "LOW", "HIGH", "CUSTOM"]
            current_tax = item["tax_type"] if item["tax_type"] in tax_types else "NONE"
            edit_tax = st.selectbox(
                "Tax Type",
                tax_types,
                index=tax_types.index(current_tax),
                key="edit_tax",
            )

            edit_custom_tax = 0.0
            if edit_tax == "CUSTOM":
                edit_custom_tax = st.number_input(
                    "Custom Tax %",
                    min_value=0.0,
                    value=float(item["custom_tax_rate"]),
                    step=0.1,
                    format="%.2f",
                    key="edit_custom_tax",
                )

        if st.button("Save Item Changes", type="primary"):
            update_inventory_item(
                item["sku"],
                edit_barcode.strip() or None,
                edit_quantity,
                edit_price,
                edit_fee,
                edit_tax,
                edit_custom_tax,
            )
            st.success("Item updated.")
            st.rerun()

        st.divider()
        st.warning("Deleting an item removes it from inventory.")
        confirm = st.checkbox(
            f'I confirm I want to delete {item["product"]}',
            key="confirm_delete",
        )

        if st.button("Delete Item"):
            if not confirm:
                st.error("Confirm the deletion first.")
            else:
                delete_inventory_item(item["sku"])
                st.success("Item deleted.")
                st.rerun()


# ============================================================
# SALES HISTORY TAB
# ============================================================

with history_tab:
    st.subheader("Sales History")
    sales = list_sales()
    if sales:
        st.dataframe(sales, use_container_width=True, hide_index=True)
    else:
        st.info("No sales have been recorded yet.")


# ============================================================
# SETTINGS TAB
# ============================================================

with settings_tab:
    st.subheader("POS Settings")
    st.caption("Edit tax rates and the optional card fee.")

    s1, s2, s3 = st.columns(3)

    with s1:
        new_low_tax = st.number_input(
            "Low Tax %",
            min_value=0.0,
            value=float(low_tax),
            step=0.1,
            format="%.2f",
        )

    with s2:
        new_high_tax = st.number_input(
            "High Tax %",
            min_value=0.0,
            value=float(high_tax),
            step=0.1,
            format="%.2f",
        )

    with s3:
        new_card_fee = st.number_input(
            "Card Fee %",
            min_value=0.0,
            value=float(card_fee),
            step=0.1,
            format="%.2f",
        )

    if st.button("Save Settings", type="primary"):
        update_settings(new_low_tax, new_high_tax, new_card_fee)
        st.success("Settings saved.")
        st.rerun()