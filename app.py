"""Adrian's fictional salon demo. All findings are calculated from six source CSVs."""
from pathlib import Path
import pandas as pd
import streamlit as st

ASOF = pd.Timestamp('2026-09-13 23:59:59')
THIS = pd.Timestamp('2026-09-07')
NEXT = pd.Timestamp('2026-09-14')
BASE = pd.date_range('2026-08-10', periods=4, freq='7D')
FILES = ['customers', 'services', 'staff_capacity', 'appointments', 'retail_sales', 'customer_followups']

def parse_dates(series):
    # Excel may rewrite ISO dates as Australian day/month/year strings.
    text = series.astype('string')
    slash = text.str.contains('/', na=False)
    result = pd.Series(pd.NaT, index=series.index, dtype='datetime64[ns]')
    result.loc[slash] = pd.to_datetime(series.loc[slash], dayfirst=True, format='mixed', errors='raise')
    result.loc[~slash] = pd.to_datetime(series.loc[~slash], format='mixed', errors='raise')
    return result

def load_data(root):
    tables = {}
    for name in FILES:
        paths = [Path(root) / 'Dummy Data' / (name + '.csv')]
        paths = [p for p in paths if p.is_file()]
        if len(paths) != 1:
            raise ValueError(f'Expected one {name}.csv below the app folder, found {len(paths)}. Keep one copy of each source CSV in Dummy Data or beside app.py.')
        tables[name] = pd.read_csv(paths[0])
    a, c, s = tables['appointments'], tables['customers'], tables['services']
    for field in ['appointment_start', 'appointment_end', 'booking_created_at', 'cancelled_at', 'completed_at', 'week_start']:
        a[field] = parse_dates(a[field])
    c['first_completed_visit_date'] = parse_dates(c['first_completed_visit_date'])
    tables['staff_capacity']['work_date'] = parse_dates(tables['staff_capacity']['work_date'])
    tables['customer_followups']['contacted_at'] = parse_dates(tables['customer_followups']['contacted_at'])
    s['colour_service'] = s['colour_service'].astype(str).str.lower().eq('true')
    a = a.merge(s[['service_id', 'service_name', 'colour_service', 'service_revenue_per_hour_aud']], on='service_id', validate='many_to_one')
    a = a.merge(c[['customer_id', 'customer_name', 'first_completed_visit_date']], on='customer_id', validate='many_to_one')
    a['hours'] = a['booked_duration_minutes'] / 60
    tables['appointments'] = a
    return tables

def completed(t, weeks):
    a = t['appointments']
    return a[a.week_start.isin(weeks) & a.status.eq('completed') & a.completed_at.le(ASOF)].copy()

def capacity(t, week):
    c = t['staff_capacity']
    return c.loc[c.work_date.ge(week) & c.work_date.lt(week + pd.Timedelta(days=7)), 'bookable_hours'].sum()

def snapshot(t, week):
    a = t['appointments']; cutoff = week - pd.Timedelta(seconds=1)
    a = a[a.week_start.eq(week) & a.booking_created_at.le(cutoff) & (a.cancelled_at.isna() | a.cancelled_at.gt(cutoff))].copy()
    a['Customer type'] = a.first_completed_visit_date.isna() | a.first_completed_visit_date.gt(cutoff.normalize())
    a['Customer type'] = a['Customer type'].map({True: 'New', False: 'Returning'})
    return a

def staff_results(t):
    rows = []
    for label, weeks, divisor in [('Four-week average', BASE, 4), ('This week', [THIS], 1)]:
        a = completed(t, weeks)
        r = t['retail_sales']
        r = r[r.appointment_id.isin(a.appointment_id) & r.product_name.eq('Colour-care shampoo')]
        for name in sorted(a.staff_name.unique()):
            aa = a[a.staff_name.eq(name)]; colours = aa[aa.colour_service]
            rr = r[r.appointment_id.isin(colours.appointment_id)]
            # Distinct customer/week exposures; one buyer can return in multiple weeks.
            eligible = colours[['customer_id', 'week_start']].drop_duplicates().shape[0]
            buyers = colours[colours.appointment_id.isin(rr.appointment_id)][['customer_id', 'week_start']].drop_duplicates().shape[0]
            rows.append({'Staff': name, 'Period': label, 'Hours': aa.hours.sum()/divisor, 'Colour customers': eligible/divisor,
                         'Shampoo buyers': buyers/divisor, 'Purchase rate': buyers/eligible if eligible else 0,
                         'Service revenue': aa.service_revenue_aud.sum()/divisor, 'Shampoo revenue': rr.retail_revenue_aud.sum()/divisor})
    return pd.DataFrame(rows)

def retention(t):
    a = t['appointments']; f = t['customer_followups']; c = t['customers'].set_index('customer_id')
    done = a[a.status.eq('completed') & a.completed_at.le(ASOF)]
    future = set(a.loc[a.status.eq('booked') & a.appointment_start.gt(ASOF), 'customer_id'])
    recent = set(f.loc[f.contacted_at.ge(ASOF-pd.Timedelta(days=14)) & f.contacted_at.le(ASOF), 'customer_id'])
    rows = []
    for cid, group in done.groupby('customer_id'):
        group = group.sort_values('appointment_start')
        if len(group) < 3:
            continue
        dates = group.appointment_start.dt.normalize()
        interval = round(dates.diff().dt.days.dropna().median())
        due = dates.iloc[-1] + pd.Timedelta(days=interval)
        if due > ASOF.normalize():
            continue
        last = group.iloc[-1]
        action = 'Already booked' if cid in future else 'Recently contacted' if cid in recent else 'Review and contact'
        if str(c.loc[cid, 'contact_permission']).lower() != 'yes':
            action = 'No contact permission'
        rows.append({'Customer ID': cid, 'Customer': c.loc[cid, 'customer_name'], 'Preferred staff': c.loc[cid, 'preferred_staff_name'],
                     'Last visit': dates.iloc[-1].date(), 'Usual gap (days)': interval, 'Estimated due': due.date(),
                     'Days overdue': (ASOF.normalize()-due).days, 'Last service': last.service_name,
                     'Potential hours': last.hours, 'Potential value (AUD)': last.quoted_service_amount_aud, 'Action': action})
    return pd.DataFrame(rows).sort_values('Days overdue', ascending=False)

def mix_results(t):
    rows = []
    for label, weeks, divisor in [('Four-week average', BASE, 4), ('This week', [THIS], 1)]:
        a = completed(t, weeks)
        for service, g in a.groupby('service_name'):
            rows.append({'Service': service, 'Period': label, 'Appointments': len(g)/divisor, 'Hours': g.hours.sum()/divisor,
                         'Revenue': g.service_revenue_aud.sum()/divisor, 'Revenue per hour': g.service_revenue_aud.sum()/g.hours.sum()})
    return pd.DataFrame(rows)

def show_table(frame):
    st.dataframe(frame, hide_index=True, use_container_width=True)

def money_change(value):
    return f"{'-' if value < 0 else '+'}${abs(value):,.2f}"


def setting(name, default=''):
    import os
    try:
        return str(st.secrets.get(name, os.environ.get(name, default)))
    except FileNotFoundError:
        return os.environ.get(name, default)


def main():
    st.set_page_config(page_title="Adrian | Salon Insights", page_icon='✂', layout='wide')
    st.markdown('''<style>
    .stApp {background-color:#f7f8fa;color:#172b3a}
    h1,h2,h3 {color:#173b45}
    [data-testid="stMetric"] {background:white;border:1px solid #dce5e8;border-radius:12px;padding:18px}
    .block-container {max-width:1250px;padding-top:2rem}
    </style>''', unsafe_allow_html=True)
    st.caption('ADRIAN’S SALON · BUSINESS INSIGHTS')
    st.title('Know what changed. Decide what to do.')
    st.caption('Synthetic demo · Handoff specification 18 September 2026')
    view = st.radio('View', ['Ask your salon', 'Business evidence', 'Legacy demo'], horizontal=True)
    if view == 'Ask your salon':
        from analyst_ui import render
        from analytics.runtime import load_snapshot
        render(load_snapshot(st.session_state), setting)
        return
    if view == 'Business evidence':
        from analytics.dashboard import render
        render(setting)
        return
    st.info('Archived six-CSV demo, as at 13 September 2026. It does not use current corrections. Use Ask your salon or Business evidence for the expanded data.')
    try:
        t = load_data(Path(__file__).resolve().parent)
    except (ValueError, KeyError, OSError) as e:
        st.error(str(e)); st.stop()
    current = completed(t, [THIS]); base = completed(t, BASE)
    next_a = snapshot(t, NEXT); cap = capacity(t, NEXT)
    b_rev, c_rev = base.service_revenue_aud.sum()/4, current.service_revenue_aud.sum()
    b_h, c_h = base.hours.sum()/4, current.hours.sum()
    cols = st.columns(3)
    cols[0].metric('This week’s service revenue', f'${c_rev:,.0f}', f'{money_change(c_rev-b_rev)} vs four-week average')
    cols[1].metric('Next week booked', f'{next_a.hours.sum()/cap:.0%}')
    cols[1].caption(f'{next_a.hours.sum():g} of {cap:g} hours')
    cols[2].metric('Service revenue per hour', f'${c_rev/c_h:.2f}', f'{money_change(c_rev/c_h-b_rev/b_h)} vs four-week baseline')
    st.caption('This week: 7–13 Sep · Baseline: 10 Aug–6 Sep · Next week: 14–20 Sep')
    tabs = st.tabs(['1 · Sarah’s sales', '2 · Fill next week', '3 · Service value'])

    with tabs[0]:
        sr = staff_results(t)
        b = sr[(sr.Staff=='Sarah') & (sr.Period=='Four-week average')].iloc[0]
        n = sr[(sr.Staff=='Sarah') & (sr.Period=='This week')].iloc[0]
        loss = b['Shampoo revenue']-n['Shampoo revenue']
        st.subheader('Why did Sarah’s sales fall while she was fully booked?')
        st.info(f"Sarah’s service revenue stayed at AUD {n['Service revenue']:,.0f}. Shampoo revenue fell by AUD {loss:,.0f}, with {n['Shampoo buyers']:g} buyer this week versus {b['Shampoo buyers']:g} on average.")
        cols = st.columns(3)
        cols[0].metric('Sarah’s completed hours', f"{n['Hours']:g}")
        cols[1].metric('Colour customers', f"{n['Colour customers']:g}")
        cols[2].metric('Shampoo purchase rate', f"{n['Purchase rate']:.0%}", f"{(n['Purchase rate']-b['Purchase rate'])*100:.0f} percentage points")
        rates = sr.pivot(index='Staff', columns='Period', values='Purchase rate').mul(100)
        st.write('**Shampoo buyers per 100 colour-service customers**')
        st.bar_chart(rates, color=['#8ba8ad', '#176c70'], stack=False)
        st.caption('Matthew and Sam maintain broadly similar purchase rates. Their colour-customer volumes differ, so raw shampoo sales alone are not a fair comparison.')
        with st.expander('See the five colouring appointments'):
            colour = current[current.staff_name.eq('Sarah') & current.colour_service].copy()
            purchases = t['retail_sales'].groupby('appointment_id').quantity.sum()
            colour['Shampoo bottles'] = colour.appointment_id.map(purchases).fillna(0).astype(int)
            show_table(colour[['customer_name','appointment_start','service_name','Shampoo bottles']].rename(columns={'customer_name':'Customer','appointment_start':'Appointment','service_name':'Service'}))
        with st.expander('Compare the supporting numbers'):
            show_table(sr.round(3))
        st.write('**Next action:** review these visits with Sarah. Ask whether customers needed shampoo, had recently bought it, or received a recommendation.')
        st.caption('Five customers is a small sample. The data explains the revenue change, but does not establish why customers did not buy. Stock and recommendation records are not included.')

    with tabs[1]:
        st.subheader('Why is next week quiet — and who could we invite back?')
        rows=[]
        for period, weeks, divisor in [('Four-week average', BASE, 4), ('Next week', [NEXT], 1)]:
            for typ in ['New','Returning']:
                frames=[snapshot(t,w) for w in weeks]
                group=pd.concat(frames);group=group[group['Customer type'].eq(typ)]
                rows.append({'Period':period,'Customer type':typ,'Appointments':len(group)/divisor,'Hours':group.hours.sum()/divisor})
        booking=pd.DataFrame(rows)
        st.info('New-customer hours are stable. The booking gap is in returning customers.')
        show_table(booking)
        st.bar_chart(booking.pivot(index='Customer type',columns='Period',values='Hours'), color=['#8ba8ad','#176c70'], stack=False)
        st.caption('Hours booked at the same lead time: Sunday before each target week. New means no completed visit before that cutoff, including first-visit history from before the CSV period.')
        pool=retention(t)
        st.write('**Customers to review for follow-up**')
        action=st.selectbox('Show customers', ['Review and contact','Recently contacted','Already booked','All due customers'])
        staff=st.selectbox('Preferred staff', ['All','Sarah','Matthew','Sam'])
        filtered=pool if action=='All due customers' else pool[pool.Action.eq(action)]
        if staff!='All':filtered=filtered[filtered['Preferred staff'].eq(staff)]
        st.caption(f'{len(filtered)} customers shown. Due dates are estimates from at least three completed visits, using their median return interval. Review suitability before contacting.')
        show_table(filtered)
        st.download_button('Download this customer list', filtered.to_csv(index=False).encode('utf-8-sig'), 'salon_followup_list.csv', 'text/csv')
        with st.expander('See available hours by staff next week'):
            cc=t['staff_capacity'];cc=cc[cc.work_date.ge(NEXT)&cc.work_date.lt(NEXT+pd.Timedelta(days=7))]
            avail=cc.groupby('staff_name').bookable_hours.sum().rename('Available hours').to_frame()
            avail['Booked hours']=next_a.groupby('staff_name').hours.sum().reindex(avail.index,fill_value=0)
            avail['Unbooked hours']=avail['Available hours']-avail['Booked hours']
            show_table(avail.reset_index().rename(columns={'staff_name':'Staff'}))
        st.write('**Next action:** contact suitable returning customers whose usual services fit the available appointments. Track contacts, resulting bookings and completed visits separately.')
        st.caption('The follow-up pool is a recovery opportunity, not proof of why every missing booking was lost. Exporting a list does not contact customers. This demo does not save new follow-up outcomes.')

    with tabs[2]:
        st.subheader('Why are we equally busy but earning less per hour?')
        st.info(f'Completed hours stayed at {c_h:g}. Service revenue fell by ${b_rev-c_rev:,.2f}, as more time went to lower-value services.')
        mix=mix_results(t)
        st.write('**Completed hours by service**')
        st.bar_chart(mix.pivot(index='Service',columns='Period',values='Hours'),color=['#8ba8ad','#176c70'], stack=False, horizontal=True, height=450)
        with st.expander('See revenue and hours for each service', expanded=True):
            show_table(mix.round(2))
        shift=base.loc[base.service_revenue_per_hour_aud.eq(130),'hours'].sum()/4-current.loc[current.service_revenue_per_hour_aud.eq(130),'hours'].sum()
        st.write(f'**What explains the difference:** {shift:g} hours moved from AUD 130/hour services to AUD 80/hour services. At an AUD 50 difference per hour, that accounts for AUD {shift*50:,.2f}. Prices and discounts are unchanged in this sample.')
        st.write('**Next action:** review whether targeted promotion of colouring packages could increase suitable bookings. Start with customers due for colouring, then measure package bookings, utilisation and revenue per hour.')
        st.caption('Revenue per hour is not profit. Product costs and campaign enquiries are absent, so we cannot calculate package margins or prove that promotion will increase demand.')
    with st.expander('How this demo works'):
        st.write('All results are calculated from the six source CSVs. The chat proposes read-only SQL over the source data and checks evidence before presenting an explanation. Supabase can store owner-reviewed context when connected. No customer messages are sent. The snapshot date is fixed so future bookings are not mistaken for completed revenue.')
        st.write('Capacity assumes 38 fully bookable hours per staff member per week. Breaks, admin and colour-processing overlaps are not modelled. Service revenue and retail revenue are aggregated separately to prevent double-counting.')

if __name__ == '__main__':
    main()
