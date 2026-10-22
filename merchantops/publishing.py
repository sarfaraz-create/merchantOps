"""Build-derived decision memo and explicit source allowlist for downloads."""

from pathlib import Path
import zipfile


def decision_memo(payload):
    rows = payload["monthly"]
    total = lambda month, key: sum(
        r[key] for r in rows if r["month"].strftime("%Y-%m") == month
    )
    rupees = lambda x: f"₹{x/100:,.2f}"
    cost_change = total("2026-06", "discount") - total("2026-01", "discount")
    paid = next(r for r in payload["acquisition"] if r["channel"] == "Paid social")
    products = {}
    for r in payload["products"]:
        item = products.setdefault(
            r["product"], {"refund": 0, "charged": 0, "orders": 0, "refunded": 0}
        )
        for key, source in [
            ("refund", "refund_amount"),
            ("charged", "charged_revenue"),
            ("orders", "orders"),
            ("refunded", "refunded_orders"),
        ]:
            item[key] += r[source]
    top = max(products, key=lambda k: products[k]["refund"] / products[k]["charged"])
    r = products[top]
    return [
        {
            "title": "1. Audit discount policy before chasing more volume",
            "evidence": f'January-to-June discounts increased by {rupees(cost_change)}. Contribution changed by {rupees(total("2026-06","contribution")-total("2026-01","contribution"))}. Review promotion eligibility and contribution per order.',
            "limitation": "An accounting decomposition cannot establish that discounts caused the change. Product mix and order volume also changed.",
        },
        {
            "title": f"2. Investigate {top} refund reasons",
            "evidence": f'{top} has the highest store-wide refund-value rate: {100*r["refund"]/r["charged"]:.2f}% ({rupees(r["refund"])} / {rupees(r["charged"])} charged); {r["refunded"]}/{r["orders"]} orders received a refund. Check return reasons and product expectations.',
            "limitation": "Order-date view includes all loaded refunds. No reason codes or recovered inventory costs exist; recent orders are less mature. This does not prove a quality problem.",
        },
        {
            "title": "3. Review acquisition cohorts before changing ad budgets",
            "evidence": f'Paid social spent {rupees(paid["ad_spend"])} across {paid["first_customers"]} first-observed customers: CAC {rupees(paid["first_order_cac_paise"])}. Blended net revenue/spend is {paid["blended_revenue_to_spend"]:.2f}× and includes repeat purchases.',
            "limitation": "First order in the observed period is not proven lifetime acquisition. Attribution is recorded channel; no causal lift or lifetime-value estimate is available.",
        },
    ]


def export_memo(memo):
    text = "# MerchantOps decision memo\n\nSynthetic scenario • January–June 2026 • INR • no realised business outcomes\n\n"
    for item in memo:
        text += f'## {item["title"]}\n\n{item["evidence"]}\n\nLimitation: {item["limitation"]}\n\n'
    text += "Evidence: dist/data.json, models/monthly.sql, models/sku_returns.sql and models/channel_acquisition.sql. Generated from the same verified snapshot as the interface.\n"
    Path("docs/decision-memo.md").write_text(text)
    Path("dist/decision-memo.md").write_text(text)


def package_source():
    # Never ship local databases, quarantine payloads, credentials, host metadata or caches.
    with zipfile.ZipFile("dist/source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for base in [
            "merchantops",
            "models",
            "macros",
            "tests",
            "data_tests",
            "docs",
            "examples",
            ".github",
        ]:
            for file in sorted(Path(base).rglob("*")):
                if file.is_file() and "__pycache__" not in str(file):
                    archive.write(file)
        for name in [
            "README.md",
            "requirements.txt",
            "dbt_project.yml",
            "profiles.yml",
            ".gitignore",
            "dist/index.html",
            "dist/app.js",
            "dist/style.css",
            "dist/guide.html",
            "dist/integration.html",
            "dist/data.json",
            "dist/benchmark.json",
            "dist/gap-review.md",
            "dist/decision-memo.md",
        ]:
            if Path(name).exists():
                archive.write(name)


if __name__ == "__main__":
    package_source()
