def calculate_trade_costs(
    buy_value,
    sell_value,
    gross_pnl
):

    # Zerodha CNC Delivery Estimates

    stt = (
        buy_value * 0.001
    ) + (
        sell_value * 0.001
    )

    stamp_duty = (
        buy_value * 0.00015
    )

    exchange_charges = (
        buy_value + sell_value
    ) * 0.0000345

    sebi_charges = (
        buy_value + sell_value
    ) * 0.000001

    gst = (
        exchange_charges
    ) * 0.18

    dp_charge = 15.93

    total_charges = (
        stt
        + stamp_duty
        + exchange_charges
        + sebi_charges
        + gst
        + dp_charge
    )

    tax_reserve = 0

    if gross_pnl > 0:
        tax_reserve = (
            gross_pnl * 0.20
        )

    net_pnl = (
        gross_pnl -
        total_charges
    )

    return {
        "gross_pnl": gross_pnl,
        "charges": round(
            total_charges,
            2
        ),
        "net_pnl": round(
            net_pnl,
            2
        ),
        "estimated_tax_reserve": round(
            tax_reserve,
            2
        )
    }
