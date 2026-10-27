from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from app.schemas import Input, StoredText, Text
from pydantic import Field, field_validator, model_validator

Kind = Literal["research", "education", "marketing", "sales"]
Alias = Literal["S1", "S2", "S3"]


class SourceInput(Input):
    name: Text
    kind: Literal["internal_note", "public_excerpt"]
    content: Annotated[StoredText, Field(min_length=10, max_length=1500)]
    attribution: Annotated[StoredText, Field(min_length=1, max_length=1000)]
    source_url: Annotated[StoredText, Field(max_length=2000)] | None = None
    rights_confirmed: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def permission_and_reference(self):
        if not self.rights_confirmed:
            raise ValueError("Confirm permission to use this text")
        if self.kind == "public_excerpt" and not self.source_url:
            raise ValueError("Public excerpts require a reference URL")
        if self.source_url:
            url = urlsplit(self.source_url)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or any(c.isspace() for c in self.source_url)
            ):
                raise ValueError("Use an HTTPS reference URL without credentials")
        return self


class RunInput(Input):
    kind: Kind
    brief: Annotated[StoredText, Field(min_length=10, max_length=1000)]
    source_ids: list[UUID] = Field(default_factory=list, max_length=3)

    @field_validator("source_ids")
    @classmethod
    def distinct(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Source IDs must be distinct")
        return values


class Section(Input):
    heading: Annotated[StoredText, Field(min_length=1, max_length=100)]
    body: Annotated[StoredText, Field(min_length=1, max_length=800)]
    sources: Annotated[list[Alias], Field(max_length=3)]


class Quote(Input):
    source: Alias
    quote: Annotated[StoredText, Field(min_length=1, max_length=300)]


class Part(Input):
    body: Annotated[StoredText, Field(min_length=1, max_length=320)]
    sources: Annotated[list[Alias], Field(max_length=3)]


class ModelOutput(Input):
    title: Text
    overview: Part
    deliverable: Part
    checks: Part
    evidence_quotes: Annotated[list[Quote], Field(max_length=3)]
    questions: Annotated[
        list[Annotated[StoredText, Field(min_length=1, max_length=150)]], Field(max_length=2)
    ]


class Output(Input):
    title: Text
    sections: Annotated[list[Section], Field(min_length=3, max_length=3)]
    evidence_quotes: Annotated[list[Quote], Field(max_length=3)]
    questions: Annotated[
        list[Annotated[StoredText, Field(min_length=1, max_length=300)]], Field(max_length=4)
    ]


class ReviewInput(Input):
    decision: Literal["accepted", "rejected"]
    note: Annotated[StoredText, Field(min_length=1, max_length=1000)]
