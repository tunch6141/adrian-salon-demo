"""Append reviewed replacements; never edit an earlier approval or raw record."""
from copy import deepcopy
from .adapter import Intake
from .clarification import questions, proposed, decision
from analytics.persistence import scoped_decisions, build_snapshot


def scope_key(row):
    raw=str(row['raw_value'])
    if row['table']=='bookings' and row['field']=='staff_id':raw=raw.strip().casefold()
    return row['table'],row['field'],raw,row.get('record_id','')


def current_rules(raw,decisions):
    return list({scope_key(d):d for d in scoped_decisions(raw,decisions)}.values())


def revision_question(raw,decisions,old):
    remaining=[d for d in scoped_decisions(raw,decisions) if scope_key(d)!=scope_key(old)]
    kind={'bookings':'staff','inventory_items':'cost','customer_import_batch':'identity'}[old['table']]
    return next((q for q in questions(Intake(raw,remaining)) if q['kind']==kind and str(q['raw_value']).strip().casefold()==str(old['raw_value']).strip().casefold() and (not old.get('record_id') or q['record_id']==old['record_id'])),None)


def prepare_revision(raw,cp,old,value,actor,reason):
    if not reason.strip():raise ValueError('Explain why the earlier approval should change.')
    if value==old['value']:raise ValueError('Choose a different corrected value.')
    q=revision_question(raw,cp['decisions'],old)
    if not q:raise ValueError('This rule does not apply to the current raw snapshot.')
    label=next((o['label'] for o in q['options'] if o['value']==value),value)
    evidence=('keep separate' if value=='new_identity' else label+' '+value)+'; reason: '+reason.strip()
    new=decision(proposed(q,value,evidence),actor)
    new.update(previous_value=old['value'],supersedes_rule_id=old.get('rule_id'),change_reason=reason.strip())
    updated=deepcopy(cp);updated['decisions'].append(new)
    before,after=build_snapshot(raw,cp),build_snapshot(raw,updated)
    changes=[]
    from .adapter import KEYS
    for table,rows in after['tables'].items():
        previous={r[KEYS[table]]:r for r in before['tables'].get(table,[])}
        for row in rows:
            prior=previous.get(row[KEYS[table]],{})
            for field in row:
                if prior.get(field)!=row[field]:changes.append({'Table':table,'Record':row[KEYS[table]],'Field':field,'Before':str(prior.get(field,'')),'After':str(row[field])})
    if not changes:raise ValueError('This replacement would not change the current cleaned data.')
    return updated,changes
