from typing import Annotated, Literal

from app.schemas import Input
from pydantic import Field


class Question(Input):
    question: Annotated[str, Field(min_length=2, max_length=1000)]


class SearchPlan(Input):
    product_query: Annotated[str, Field(min_length=1, max_length=120)] | None
    currency: Literal["IRR", "IRT", "USD", "EUR"] = "IRR"
