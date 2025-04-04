import difflib
import re
from typing import Type, Dict, Any, Tuple
import pandas as pd
from pydantic import BaseModel, Field

def _clean(text: str) -> str:
    """Normalize text for fuzzy comparison."""
    return re.sub(r"[^a-zA-Z0-9]+", " ", text.lower()).strip()

def _string_similarity(a: str, b: str) -> float:
    """Compute normalized string similarity."""
    return difflib.SequenceMatcher(None, _clean(a), _clean(b)).ratio()

def auto_suggest_field_map(
    prev_ret: BaseModel,
    next_model_class: Type,
    alpha: float = 0.4,          # weight for name similarity
    beta: float = 0.4,           # weight for description similarity
    gamma: float = 0.3,          # weight for exact type match
    delta: float = 0.3,          # weight for context factor
    threshold: float = 0.5       # final score threshold for mapping
) -> Tuple[Dict[str, str], pd.DataFrame]:
    """
    Suggest a field map from prev_ret to next_model_class().args,
    using name, description, type match, and a context factor
    based on how many fields of the same type exist.
    """
    source_fields = prev_ret.model_fields
    target_fields = next_model_class().args.model_fields

    # Count how many source & target fields share each type
    from collections import Counter
    source_type_count = Counter(f.annotation for f in source_fields.values())
    target_type_count = Counter(f.annotation for f in target_fields.values())

    score_matrix = {}

    # Build a row (dict) of scores for each target field
    for target_name, target_field in target_fields.items():
        row_scores = {}
        t_desc = target_field.description or target_name
        t_type = target_field.annotation

        # Precompute how many fields in source have the same type as the target
        m = source_type_count[t_type]
        n = target_type_count[t_type]

        for source_name, source_field in source_fields.items():
            s_desc = source_field.description or source_name
            s_type = source_field.annotation

            # 1) Name & description similarities
            name_score = _string_similarity(target_name, source_name)
            desc_score = _string_similarity(t_desc, s_desc)

            # 2) Exact type match
            type_score = 1.0 if (s_type == t_type) else 0.0

            # 3) Context factor = 1 / (m * n) if types match, else 0
            if s_type == t_type and m > 0 and n > 0:
                context_factor = 1.0 / (m * n)
            else:
                context_factor = 0.0

            # Combine them with weighted average
            weighted_score = (
                alpha * name_score
                + beta * desc_score
                + gamma * type_score
                + delta * context_factor
            ) / (alpha + beta + gamma + delta)

            row_scores[source_name] = weighted_score

        score_matrix[target_name] = row_scores

    # Build a DataFrame for debugging
    df = pd.DataFrame(score_matrix).T

    # Greedily pick best match per target field
    suggested_map = {}
    for target_name, row in score_matrix.items():
        best_source = max(row, key=row.get)  # name with highest score
        best_score = row[best_source]
        if best_score >= threshold:
            suggested_map[target_name] = best_source

    return suggested_map, df

def smart_build_by_ret(ret_data: Dict[str, Any], model_cls: Type, field_map: Dict[str, str]) -> Any:
    """Build a model instance with .args filled from return data."""
    model = model_cls()
    for target_field in model.args.model_fields:
        source_field = field_map.get(target_field, target_field)
        if source_field in ret_data:
            setattr(model.args, target_field, ret_data[source_field])
    return model


# --------------------
# 🧪 Mock Test Classes
# --------------------

class MockRet(BaseModel):
    result: int = Field(..., description="The doubled result of input number")

class MockNextModel:
    class Args(BaseModel):
        n: int = Field(0, description="The number for computing Fibonacci")  # default = no validation error

    def __init__(self):
        self.args = self.Args()

# ---------------------
# 🔬 Extended Test Suite
# ---------------------

class MockRet(BaseModel):
    result: int = Field(0, description="The doubled result of input number")

class MockNextModel:
    class Args(BaseModel):
        n: int = Field(0, description="The number for computing Fibonacci")
    def __init__(self):
        self.args = self.Args()


class MockRetA(BaseModel):
    value: float = Field(0.0, description="The temperature in Celsius")

class MockNextModelA:
    class Args(BaseModel):
        temp: float = Field(0.0, description="Temperature in Celsius")
    def __init__(self):
        self.args = self.Args()


class MockRetB(BaseModel):
    age: int = Field(0, description="Years since birth")
    name: str = Field("", description="Name of the user")

class MockNextModelB:
    class Args(BaseModel):
        user_age: int = Field(0, description="Age in years")
        id_name: str = Field("", description="Identifier for something")
    def __init__(self):
        self.args = self.Args()


class Address(BaseModel):
    city: str = Field("", description="City name")
    zipcode: int = Field(0, description="Postal code")

class MockRetC(BaseModel):
    location: Address = Field(default_factory=Address, description="User location")

class MockNextModelC:
    class Args(BaseModel):
        city: str = Field("", description="Name of the city")
        zip: int = Field(0, description="Zip code of user")
    def __init__(self):
        self.args = self.Args()


class MockRetD(BaseModel):
    user_id: int = Field(0, description="User ID as a number")

class MockNextModelD:
    class Args(BaseModel):
        user_id: str = Field("", description="User ID as a string")
    def __init__(self):
        self.args = self.Args()


class MockRetE(BaseModel):
    success: bool = Field(False, description="Operation succeeded")

class MockNextModelE:
    class Args(BaseModel):
        count: int = Field(0, description="Number of attempts")
    def __init__(self):
        self.args = self.Args()

class MockRetF(BaseModel):
    user_status: str = Field("active", description="The current status of the user")
    last_seen: str = Field("2025-03-28", description="Last seen timestamp")

class MockNextModelF:
    class Args(BaseModel):
        status: str = Field("unknown", description="User status description")
        last_seen_date: str = Field("", description="Date user was last seen")

    def __init__(self):
        self.args = self.Args()
        
class MockRetG(BaseModel):
    is_admin: bool = Field(False, description="True if user is admin")

class MockNextModelG:
    class Args(BaseModel):
        admin: bool = Field(False, description="Admin privileges")

    def __init__(self):
        self.args = self.Args()
        
class MockRetH(BaseModel):
    items: list[str] = Field(default_factory=list, description="List of purchased items")

class MockNextModelH:
    class Args(BaseModel):
        purchased_items: list[str] = Field(default_factory=list, description="Items that were bought")

    def __init__(self):
        self.args = self.Args()
        
class MockRetI(BaseModel):
    score: float = Field(0.0, description="Final evaluation score")

class MockNextModelI:
    class Args(BaseModel):
        final_score: float = Field(0.0, description="The score achieved at the end")

    def __init__(self):
        self.args = self.Args()
        
class MockRetJ(BaseModel):
    metrics: Dict[str, float] = Field(default_factory=lambda: {"accuracy": 0.98, "loss": 0.1})

class MockNextModelJ:
    class Args(BaseModel):
        accuracy: float = Field(0.0, description="Model accuracy")
        loss: float = Field(0.0, description="Model loss")

    def __init__(self):
        self.args = self.Args()
        
from datetime import datetime

class MockRetK(BaseModel):
    timestamp: str = Field("2025-03-28T12:00:00Z", description="ISO datetime string")

class MockNextModelK:
    class Args(BaseModel):
        event_time: datetime = Field(default_factory=datetime.utcnow, description="Time of the event")

    def __init__(self):
        self.args = self.Args()

if __name__ == "__main__":
    # --------------------
    # ✅ Test Execution
    # --------------------

    # # Simulate previous step's output
    # prev_model_ret = MockRet(result=13)
    # ret_dict = prev_model_ret.model_dump()

    # # Suggest field map and build new model
    # suggested_map, confusion_df = auto_suggest_field_map(prev_model_ret, MockNextModel)
    # next_model = smart_build_by_ret(ret_dict, MockNextModel, suggested_map)

    # # Output results
    # print("🔧 Suggested Field Map:", suggested_map)
    # print("📊 Confusion Matrix:\n", confusion_df)
    # print("🧾 Previous .ret dict:", ret_dict)
    # print("📦 Built .args:", next_model.args)
    # print("✅ Final value for 'n':", next_model.args.n)
        
    # ---------------------
    # 🧪 Test Harness
    # ---------------------

    test_cases = [
        ("Test 1 - Basic", MockRet(result=21), MockNextModel),
        ("Test 2 - Temp", MockRetA(value=36.6), MockNextModelA),
        ("Test 3 - Age/Name", MockRetB(age=30, name="Alice"), MockNextModelB),
        ("Test 4 - Nested Address", MockRetC(location=Address(city="Paris", zipcode=75000)), MockNextModelC),
        ("Test 5 - Type Mismatch", MockRetD(user_id=42), MockNextModelD),
        ("Test 6 - Unrelated Fields", MockRetE(success=True), MockNextModelE),
        ("Test 7 - Optional Fields", MockRetF(), MockNextModelF),
        ("Test 8 - Boolean Match", MockRetG(), MockNextModelG),
        ("Test 9 - List Handling", MockRetH(items=["apple", "banana"]), MockNextModelH),
        ("Test 10 - Slight Mismatch", MockRetI(score=0.92), MockNextModelI),
        ("Test 11 - Dict Flatten", MockRetJ(), MockNextModelJ),
        ("Test 12 - Datetime Parsing", MockRetK(), MockNextModelK),
    ]

    for label, ret_obj, model_cls in test_cases:
        print(f"\n#########🧪 {label}")
        ret_dict = ret_obj.model_dump()
        field_map, matrix = auto_suggest_field_map(ret_obj, model_cls)
        print("🔧 Suggested Map:", field_map)
        print("📊 Confusion Matrix:\n", matrix)

        model_instance = smart_build_by_ret(ret_dict, model_cls, field_map)
        print("📦 Final Args:", model_instance.args)

