"""Canonical extension keys and capability dependencies, independent of entitlements."""
EXTENSION_KEYS = {
 'supplier_credits':'supplier_credit_id','pricing_scenarios':'scenario_id',
 'services':'service_id','service_components':'component_id','staff_skills':'skill_id','vehicles':'vehicle_id',
 'suppliers':'supplier_id','purchase_orders':'order_id','purchase_receipts':'receipt_id',
 'purchase_receipt_items':'receipt_item_id','inventory_batches':'batch_id',
 'enquiries':'enquiry_id','quotes':'quote_id','quote_versions':'quote_version_id','quote_followups':'quote_followup_id',
 'invoices':'invoice_id','payments':'payment_id','insights':'insight_id','actions':'action_id',
 'review_checkpoints':'checkpoint_id','price_history':'price_event_id',
}
DEPENDENCIES = {
 'revenue':['transactions','transaction_items','items'],
 'bookings':['bookings','booking_history'],
 'staff_capacity':['staff','staff_availability','bookings','booking_services'],
 'customers':['customers','bookings'],
 'inventory':['inventory_items','inventory_movements'],
 'suppliers':['suppliers','purchase_receipts','purchase_receipt_items'],
 'services':['services','transaction_items','transactions','booking_services'],
 'quotes':['quotes'], 'receivables':['invoices','payments'],
 'pricing':['transaction_items','items'], 'insights':['insights','actions','review_checkpoints'],
 'gross_margin':['transaction_items'], 'follow_up':['customer_followups'],
}
