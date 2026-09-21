from typing import Literal
from pydantic import BaseModel, Field


class Scope(BaseModel):
    objective: str | None
    subject: str | None
    entities: list[str] | None = Field(max_length=12)
    start_date: str | None
    end_date: str | None
    measures: list[str] | None = Field(max_length=8)
    category: str | None
    display: Literal['text','table','line','bar','pie'] | None


class Reference(BaseModel):
    result: int = Field(ge=0, description='Zero-based result_index from supplied results. This is an ADDRESS, never the monetary value, count or result id.')
    row: int = Field(ge=0, description='Zero-based index within that result rows array.')
    column: str = Field(description='Exact column key of the cited cell in that row.')
    format: Literal['plain','money','percent'] = 'plain'


class Statement(BaseModel):
    text: str = Field(description='Concise plain-English sentence using digits for quantities. Numeric facts must exactly match or faithfully round cited evidence. Optional [[0]] inserts the first evidence cell; never embed reference objects in text. Evidence supports the WHOLE meaning.')
    evidence: list[Reference] = Field(default_factory=list,max_length=12)
    context_ids: list[str] = Field(default_factory=list,max_length=6)
    level: Literal['observed','supported_interpretation','unverified_possibility']


class Hypothesis(BaseModel):
    explanation: str
    test: str = Field(description='Evidence that would distinguish this from competing explanations')
    status: Literal['untested','supported','contradicted','inconclusive']
    evidence: list[Reference] = Field(default_factory=list,max_length=8)


class ToolCall(BaseModel):
    kind: Literal['sql','staff_performance','revenue_total','revenue_trend','booking','calculate']
    purpose: str = Field(description='What uncertainty this calculation resolves; not a generic metric list')
    sql: str = Field(default='',description='Only kind=sql: one SQLite SELECT from one exact schema view. Never query a returned evidence packet as a SQL table.')
    staff: list[str] = Field(default_factory=list,description='Exact staff names or IDs. Empty selects all staff for staff_performance; whole-business total for revenue tools.')
    start_date: str = ''
    end_date: str = ''
    comparison_start: str = ''
    comparison_end: str = ''
    comparison_divisor: int = 1
    category: Literal['all','service','product','part'] = 'all'
    grain: Literal['day','week','month'] = 'month'
    identifier: str = Field(default='',description='Only kind=booking: actual booking ID supplied by owner. Not a label for a query. Other tools leave empty.')
    expression: str = Field(default='',description='For calculate: ONE scalar arithmetic expression using v0,v1... bound to inputs. + - * / and numeric constants. No tuples, commas, functions/code.')
    inputs: list[Reference] = Field(default_factory=list,max_length=12)
    label: str = ''


class Visual(BaseModel):
    kind: Literal['none','line','bar','pie'] = 'none'
    result: int = 0
    x: str = ''
    y: str = ''
    series: str = ''
    reason: str = ''


class ContextReview(BaseModel):
    context_id: str
    relevance: Literal['relevant','not_relevant','conflicting']
    interpretation: str


class Diagnosis(BaseModel):
    direct_answer: Statement
    key_evidence: list[Statement] = Field(max_length=3)
    primary_driver: Statement | None
    secondary_drivers: list[Statement] = Field(max_length=2)
    alternatives: list[Statement] = Field(max_length=2)
    confidence: Literal['strongly supported','likely contributor','possible explanation','insufficient evidence']
    next_step_kind: Literal['action','investigation','none']
    next_step: Statement | None
    visual: Visual
    table_results: list[int] = Field(max_length=2)
    context_review: list[ContextReview]
    limitations: str


class ContextDraft(BaseModel):
    entity: str
    start_date: str
    end_date: str
    event_type: str
    explanation: str


class Step(BaseModel):
    intent: Literal['lookup','analysis','context','clarify','method']
    topic_relation: Literal['new','continue','modify']
    scope: Scope = Field(description='For a new topic fill the scope. For continuation/modification set unchanged fields null to inherit active_state or current_investigation. Explicit values replace only those fields. Entities [] means whole business.')
    hypotheses: list[Hypothesis] = Field(max_length=4)
    calls: list[ToolCall] = Field(max_length=3)
    final: Diagnosis | None
    draft: ContextDraft | None
    clarification: str
    unresolved: list[str] = Field(max_length=4)


class Audit(BaseModel):
    approved: bool
    problems: list[str] = Field(max_length=6)
