from pydantic import BaseModel, Field, model_validator

class MatchRequest(BaseModel):
    student_levels: list[int] = Field(min_length=1, max_length=256)
    required_levels: list[int] = Field(min_length=1, max_length=256)
    weights: list[int] = Field(min_length=1, max_length=256)
    mandatory: list[int] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def check_values(self):
        lengths = {len(self.student_levels), len(self.required_levels), len(self.weights), len(self.mandatory)}
        if len(lengths) != 1:
            raise ValueError("all four arrays must have equal length")
        if any(not 0 <= n <= 3 for n in self.student_levels):
            raise ValueError("student levels must be between 0 and 3")
        if any(not 1 <= n <= 3 for n in self.required_levels):
            raise ValueError("required levels must be between 1 and 3")
        if any(not 1 <= n <= 5 for n in self.weights):
            raise ValueError("weights must be between 1 and 5")
        if any(n not in (0,1) for n in self.mandatory):
            raise ValueError("mandatory values must be 0 or 1")
        return self

class MatchResponse(BaseModel):
    earned_points: int
    max_points: int
    missing_mandatory: int
    mandatory_requirements_met: bool
    coverage_percent: float
