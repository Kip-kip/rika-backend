# Rika product-samples API (T-B6-01)
# Public "Samples of work" for product pages — borrows the case-studies pattern.
# Returns published Rika Project Photos filtered by product_category and/or product_type, no PII.
import frappe


@frappe.whitelist(allow_guest=True)
def get_product_samples():
    """GET /rika/api/product-samples?category=window&product=sliding&limit=12
    Filters:
      - category (product_category): window / door / glass / shopfront / partition
      - product  (product_type / style): sliding / casement / fixed / bay / hinged / partition / shopfront / glass / door
      - role (image_role): project (default) or product
    Both category and product are optional; when both are given they are AND-ed.
    """
    d = frappe.form_dict
    category = (d.get("category") or "").strip()
    product = (d.get("product") or "").strip()
    role = (d.get("role") or "project").strip()
    limit = int(d.get("limit") or 12)
    limit = max(1, min(limit, 50))  # clamp 1–50

    # Always filter on image_role so project and product images never mix.
    # role=product -> product-role images only (hero lightbox).
    # role=project (default) -> project-role images only (samples grid).
    filters = {"published": 1, "image_role": role}
    if category:
        filters["product_category"] = category
    if product:
        filters["product_type"] = product

    rows = frappe.get_all(
        "Rika Project Photo",
        filters=filters,
        fields=[
            "name", "project", "image", "caption",
            "product_category", "product_type", "image_role", "creation",
        ],
        order_by="creation desc",
        limit_page_length=limit,
    )

    out = []
    for r in rows:
        out.append({
            "name": r.name,
            "project": r.project,
            "image": r.image,
            "caption": r.caption or "",
            "product_category": r.product_category or "",
            "product_type": r.product_type or "",
            "image_role": r.image_role or "project",
            "created": str(r.creation)[:10],
        })

    return {"ok": True, "samples": out}
