def build_receipt_html(receipt):
    item_rows = ""
    for item in receipt["items"]:
        line = float(item["price"]) * int(item["quantity"])
        item_rows += f"""
        <div class="receipt-row">
            <span>{item['product']} &nbsp; {item['quantity']} × ${float(item['price']):.2f}</span>
            <span>${line:.2f}</span>
        </div>
        """

    cash_section = ""
    if receipt["payment_method"] == "CASH":
        cash_section = f"""
        <div>Cash Received: ${receipt['cash_received']:.2f}</div>
        <div>Change Due: ${receipt['change_due']:.2f}</div>
        """

    return f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                padding: 20px;
                color: #111;
                background: white;
            }}
            .receipt {{ max-width: 360px; margin: 0 auto; }}
            h2 {{ text-align: center; margin-bottom: 5px; }}
            hr {{ border: 0; border-top: 1px dashed #555; margin: 12px 0; }}
            .receipt-row {{ display:flex; justify-content:space-between; gap:12px; }}
            .total {{ font-size: 20px; font-weight: bold; }}
            button {{ width:100%; margin-top:18px; padding:12px; font-size:16px; cursor:pointer; }}
            @media print {{ button {{ display:none; }} }}
        </style>
    </head>
    <body>
        <div class="receipt">
            <h2>DT RETAIL POS</h2>
            <div style="text-align:center;">Receipt: {receipt['receipt_id']}</div>
            <div style="text-align:center;">{receipt['date']}</div>

            <hr>
            {item_rows}
            <hr>

            <div class="receipt-row"><span>Subtotal</span><span>${receipt['totals']['subtotal']:.2f}</span></div>
            <div class="receipt-row"><span>Product Fees</span><span>${receipt['totals']['fees']:.2f}</span></div>
            <div class="receipt-row"><span>Tax</span><span>${receipt['totals']['tax']:.2f}</span></div>
            <div class="receipt-row"><span>Card Fee</span><span>${receipt['totals']['card_fee']:.2f}</span></div>

            <hr>

            <div class="receipt-row total">
                <span>TOTAL</span>
                <span>${receipt['totals']['total']:.2f}</span>
            </div>

            <p>Payment: {receipt['payment_method']}</p>
            {cash_section}

            <p style="text-align:center;">Thank you!</p>
            <button onclick="window.print()">Print Receipt</button>
        </div>
    </body>
    </html>
    """
