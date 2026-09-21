"""Small native tool contracts. No benchmark questions or entity names."""
from typing import Literal
from pydantic import BaseModel, Field
from .models import ContextDraft


class AnalysisScope(BaseModel):
    objective: str | None = None
    subject: str | None = None
    entities: list[str] | None = Field(default=None,description='Only identities explicitly selected by the owner. Empty list means entire business, including unattributed rows. Null inherits previous scope.')
    start_date: str | None = Field(default=None,description='Start of the CURRENT requested period only, inclusive ISO date. Null inherits. Empty for undated snapshot.')
    end_date: str | None = Field(default=None,description='End of CURRENT requested period only. Actual results cannot extend beyond reporting date.')
    comparison_start: str | None = Field(default=None,description='Start of an optional separate baseline of equal duration or full calendar month. Empty means no comparison.')
    comparison_end: str | None = Field(default=None,description='End of the optional baseline. For current partial month use previous_month_matched_elapsed from calendar, not full previous month.')
    category: Literal['all','service','product','part'] | None = None
    measures: list[str] | None = None
    display: Literal['text','table','line','bar','pie'] | None = None


class FrameQuestion(BaseModel):
    intent: Literal['lookup','analysis','context','clarify']
    relation: Literal['new','continue','modify']
    scope: AnalysisScope = Field(description='Use null for unchanged fields on a follow-up. Explicit entities replace the previous people. Dates are inclusive.')
    hypotheses: list[str] = Field(max_length=3,description='Competing explanations to investigate, not assumed facts. Empty for a lookup.')
    clarification: str = ''
    context_draft: ContextDraft | None = None
    current_window: Literal['custom','inherit','last_complete_week','current_week_elapsed','last_complete_month','current_month_elapsed','next_week'] = Field(default='custom',description='Prefer a named reporting-calendar window when applicable; it determines current start/end. custom uses scope dates. inherit preserves prior dates.')
    baseline_window: Literal['custom','none','inherit','preceding_complete_week','preceding_complete_month','previous_month_matched_elapsed'] = Field(default='custom',description='A separate comparable baseline, never part of the current window. Named windows replace comparison dates. none clears comparison.')


class Measure(BaseModel):
    column: str
    operation: Literal['sum','count','count_distinct','mean','min','max']
    name: str = Field(description='Short unique output column name')


class Ratio(BaseModel):
    numerator: str = Field(description='Name of a measure in this query')
    denominator: str = Field(description='Name of a measure in this same query, with identical grouping and filters')
    scale: Literal[1,100] = 1
    name: str


class DataFilter(BaseModel):
    column: str
    operator: Literal['eq','ne','in','gt','gte','lt','lte','contains','not_null']
    values: list[str] = Field(max_length=100)


class QueryMeasures(BaseModel):
    dataset: str
    purpose: str = Field(description='What question or competing explanation this evidence tests')
    dimensions: list[str] = Field(max_length=4)
    measures: list[Measure] = Field(max_length=8)
    ratios: list[Ratio] = Field(default_factory=list,max_length=3)
    filters: list[DataFilter] = Field(default_factory=list,max_length=8)
    whole_business_context: bool = Field(default=False,description='Only true for contextual evidence that cannot be attributed to the selected people. Never treat this as their performance.')
    limit: int = Field(default=100,ge=1,le=100)


class QueryData(QueryMeasures):
    period: Literal['current','comparison','compare','snapshot'] = 'current'
    time_grain: Literal['none','day','week','month'] = 'none'


class QueryCurrentData(QueryMeasures):
    period: Literal['current','comparison','snapshot'] = Field(default='current',description='One active period or a current snapshot. For changes between periods use compare_periods instead.')
    time_grain: Literal['none','day','week','month'] = Field(default='none',description='none returns totals by dimensions; day/week/month returns a time trend within the selected period.')


class ComparePeriods(QueryMeasures):
    pass


class ReadRecords(BaseModel):
    dataset: str
    columns: list[str] = Field(max_length=15)
    filters: list[DataFilter] = Field(max_length=8)
    limit: int = Field(default=20,ge=1,le=100)


class StaffPerformance(BaseModel):
    compare_periods: bool = False


class BookingRecord(BaseModel):
    identifier: str


class ReadSQL(BaseModel):
    purpose: str
    sql: str = Field(description='One read-only SQLite SELECT on one available view. No joins, subqueries or window functions. Active dates/people/category are applied by the application.')


class ChartRequest(BaseModel):
    kind: Literal['none','line','bar','pie'] = 'none'
    source: str = ''
    x: str = ''
    y: str = ''
    series: str = ''


class FinishAnswer(BaseModel):
    answer: str = Field(description='Direct commercial answer, at most 3 short sentences. Challenge a false or unproven premise.')
    evidence: list[str] = Field(max_length=3,description='Natural-language key factual sentences, NOT source IDs. Only facts needed to support the answer; digits, AUD excluding GST.')
    sources: list[str] = Field(max_length=12,description='Evidence IDs supporting factual statements, e.g. E1. No row/cell addresses.')
    explanation: str = Field(description='Explain the supported commercial mechanism or remaining uncertainty; never repeat a metric list.')
    next_step: str = Field(description='One supported action, or the next investigation if cause remains uncertain. Empty for a complete lookup.')
    confidence: Literal['strongly supported','likely contributor','possible explanation','insufficient evidence']
    limitations: str
    context_used: list[str] = Field(max_length=8,description='IDs of relevant owner notes considered. Irrelevant candidates must not be shown.')
    chart: ChartRequest
    table_source: str = ''
    tested_explanations: list[str] = Field(default_factory=list,max_length=3,description='Brief supported/contradicted/unresolved outcomes of the hypotheses actually tested; cite Evidence IDs. Empty for a lookup.')


class Review(BaseModel):
    evidence_inventory: list[str] = Field(default_factory=list,max_length=6,description='First inventory what the retrieved evidence actually measures. Do not copy claims from the proposed answer.')
    unsupported_statements: list[str] = Field(default_factory=list,max_length=6,description='Copy any factual or causal statement for which the retrieved evidence is absent or contradictory, including qualitative high/low/profit/demand claims without measurements or comparators.')
    blocking_errors: list[str] = Field(max_length=4,description='Only demonstrably false or unsupported claims in the answer. Missing proof of a cause is NOT an error if the answer explicitly says it is unknown.')
    evidence_needed: list[str] = Field(max_length=3,description='Specific available evidence worth retrieving to correct errors; avoid requests for data already present.')
