"""Customer facts calculated from the active cleaned snapshot."""
from datetime import date
from analytics.diagnostics import packet


def customer_answer(db, plan):
    request = plan.customer
    identifier = request.identifier.strip().casefold()
    matches = [dict(r) for r in db.intake.tables.get('customers', [])
               if identifier in (str(r.get('customer_id', '')).casefold(), str(r.get('customer_name', '')).casefold())]
    base = dict(plan=plan.model_dump(), answer=None, results=[], contexts=[], issues=[])
    if len(matches) != 1:
        base['plan']['missing_information'] = 'Please confirm the customer ID or full name; the cleaned records do not identify one unique customer.'
        return {**base, 'status': 'clarify'}
    customer = matches[0]
    day = date.fromisoformat(request.as_of_date or db.intake.asof.date().isoformat())
    first = customer.get('first_completed_visit_date')
    status = ('existing' if first < day.isoformat() else 'new on this date' if first == day.isoformat()
              else 'no completed visit recorded by this date') if first else 'unknown; first completed visit is not recorded'
    bookings = db.frames['booking_records']
    visits = bookings[(bookings.customer_id == customer['customer_id']) & (bookings.appointment_date <= day.isoformat())]
    customer.update(assessed_on=day.isoformat(), customer_status=status,
                    completed_bookings_in_export=int((visits.status == 'Completed').sum()))
    results = [packet(db.intake, 'approved_customer_profile', [customer], 'Cleaned customer first completed visit compared with the requested date'),
               packet(db.intake, 'customer_booking_history', visits.sort_values('appointment_start').tail(100).to_dict('records'), 'Latest 100 cleaned bookings through the assessment date')]
    message = f"{customer['customer_name']} ({customer['customer_id']}) was {status} on {day.isoformat()}."
    if first: message += f" First recorded completed visit: {first}."
    message += f" The current export contains {customer['completed_bookings_in_export']} completed bookings through that date; this is not a lifetime visit count."
    answer = dict(claims=[dict(text=message, evidence=[dict(result=0,row=0,column='customer_status',format='plain')],context_ids=[])],
                  chart=dict(kind='none',result=0,x='',y='',series=''), investigation='',recommendation='',measurement='',
                  missing_information='',context_review=[])
    return {**base, 'answer':answer,'results':results,'status':'answered'}
