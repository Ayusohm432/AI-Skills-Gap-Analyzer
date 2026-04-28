from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict, GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import core_schema
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls.validate),
                ]),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x), when_used='always'
            ),
        )

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> Any:
        return handler(core_schema.str_schema())

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase):
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    analysis_history: List[PyObjectId] = []
    target_role: Optional[str] = None
    skills: List[str] = []

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
        json_schema_extra={
            "example": {
                "email": "test@example.com",
                "name": "Test User",
                "hashed_password": "somehashedpassword",
                "analysis_history": [],
                "target_role": "Backend Developer",
                "skills": ["Python", "FastAPI"]
            }
        }
    )

class UserResponse(UserBase):
    id: PyObjectId = Field(alias="_id")
    created_at: datetime
    updated_at: datetime
    analysis_history: List[PyObjectId] = []
    target_role: Optional[str] = None
    skills: List[str] = []

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
        json_schema_extra={
            "example": {
                "id": "60d0fe4f53592a2a0c6e2a2a",
                "email": "test@example.com",
                "name": "Test User",
                "created_at": "2023-01-01T12:00:00Z",
                "updated_at": "2023-01-01T12:00:00Z",
                "analysis_history": [],
                "target_role": "Backend Developer",
                "skills": ["Python", "FastAPI"]
            }
        }
    )

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class LoginRequest(BaseModel):
    """Credentials for the JSON login endpoint."""
    email:    EmailStr = Field(..., description="Registered email address",
                               json_schema_extra={"example": "user@example.com"})
    password: str      = Field(..., min_length=1, description="Account password",
                               json_schema_extra={"example": "yourpassword"})

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "yourpassword",
            }
        }
    )


class UserUpdate(BaseModel):
    name: Optional[str] = None
    target_role: Optional[str] = None
    skills: Optional[List[str]] = None

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
        json_schema_extra={
            "example": {
                "name": "Updated User Name",
                "target_role": "Full-Stack Developer",
                "skills": ["Python", "FastAPI", "React", "MongoDB"]
            }
        }
    )


# ── Interview Questions Models ──────────────────────────────────────────────

class InterviewQuestion(BaseModel):
    question:   str
    category:   str  = Field(description="technical | behavioral | system design")
    difficulty: str  = Field(description="easy | medium | hard")

class InterviewQuestionRequest(BaseModel):
    predicted_role: str = Field(..., description="The target or predicted job role")
    missing_skills: List[str] = Field(..., description="List of missing skills identified")

class InterviewQuestionResponse(BaseModel):
    questions: List[InterviewQuestion]

# ── Job / Background-task models ──────────────────────────────────────────────

class RoleAlternative(BaseModel):
    """A single alternative role prediction with its confidence score."""
    role:       str
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence (0–1)")


class MissingSkillRanked(BaseModel):
    """A recommended missing skill with ML-derived metadata."""
    skill:      str
    likelihood: float  = Field(ge=0.0, le=1.0, description="LSTM sigmoid probability (0–1)")
    category:   str    = Field(default="general",  description="Skill domain category")
    priority:   str    = Field(default="medium",   description="high | medium | low")


class AnalysisResult(BaseModel):
    """
    Full analysis payload stored inside a completed job document.

    Core fields
    -----------
    predicted_role, skills_detected, missing_skills, readiness_score,
    roadmap, interview_questions

    ML-derived enrichment fields
    ----------------------------
    role_confidence        – model's probability for the top-predicted role (0–1)
    role_alternatives      – ranked list of next-best role predictions
    skill_categories       – detected skills grouped by domain (backend, frontend, …)
    missing_skills_ranked  – missing skills with likelihood, category, priority
    model_version          – version string matching ML_MODEL_VERSION env var
    """
    # ── Core ──────────────────────────────────────────────────────────
    predicted_role:       str          = Field(description="The ML/NLP-predicted (or user-selected) role")
    skills_detected:      List[str]
    skill_confidences:    dict                     = Field(default_factory=dict,
                                                           description="NLP confidence per detected skill")
    missing_skills:       List[str]
    readiness_score:      float                    = Field(ge=0.0, le=100.0)
    roadmap:              list
    interview_questions:  List[InterviewQuestion]

    # ── ML enrichment ─────────────────────────────────────────────────
    role_confidence:       float                   = Field(default=0.0, ge=0.0, le=1.0,
                                                           description="Confidence for the predicted role")
    role_alternatives:     List[RoleAlternative]   = Field(default_factory=list,
                                                           description="Top alternative role predictions")
    skill_categories:      dict                    = Field(default_factory=dict,
                                                           description="Detected skills grouped by domain")
    missing_skills_ranked: List[MissingSkillRanked] = Field(default_factory=list,
                                                            description="Missing skills with ML ranking")
    model_version:         str                     = Field(default="unknown",
                                                           description="ML artifact version used")

    # ── Provenance ────────────────────────────────────────────────────
    ml_role_source:        Optional[str]           = Field(
        default=None,
        description=(
            "Origin of the role prediction. "
            "'ml' = high-confidence Random Forest; "
            "'low_confidence' = RF below 0.60 threshold, NLP used instead; "
            "'fallback' = model file missing or exception raised."
        ),
    )
    ml_missing_source:     Optional[str]           = Field(
        default=None,
        description=(
            "Origin of the missing-skills list. "
            "'ml' = LSTM inference; "
            "'static_lookup' = LSTM unavailable, rule-based table used; "
            "'fallback' = LSTM exception or bundle missing."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "predicted_role": "Data Scientist",
                "skills_detected": ["Python", "Pandas", "SQL"],
                "skill_confidences": {"Python": 0.98, "Pandas": 0.91},
                "missing_skills": ["TensorFlow", "MLOps"],
                "readiness_score": 72.5,
                "roadmap": [],
                "interview_questions": [
                    {
                        "question": "Explain the bias-variance tradeoff.",
                        "category": "technical",
                        "difficulty": "medium"
                    }
                ],
                "role_confidence": 0.92,
                "role_alternatives": [
                    {"role": "ML Engineer", "confidence": 0.06},
                    {"role": "Data Analyst",  "confidence": 0.02},
                ],
                "skill_categories": {
                    "data":     ["Python", "Pandas", "SQL"],
                    "general":  [],
                },
                "missing_skills_ranked": [
                    {"skill": "TensorFlow", "likelihood": 0.89, "category": "ml", "priority": "high"},
                    {"skill": "MLOps",      "likelihood": 0.74, "category": "mlops", "priority": "medium"},
                ],
                "model_version": "v1.0",
                "ml_role_source": "ml",
                "ml_missing_source": "fallback",
            }
        }
    )


class JobAcceptedResponse(BaseModel):
    """Returned immediately (HTTP 202) when a resume analysis job is submitted."""
    job_id:  str
    status:  str = "pending"
    message: str = "Analysis job queued. Poll /api/v1/jobs/{job_id} for results."


class JobStatusResponse(BaseModel):
    """Returned by GET /api/v1/jobs/{job_id}."""
    job_id:     str
    status:     str                         # pending | processing | completed | failed
    filename:   Optional[str]   = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    result:     Optional[AnalysisResult] = None   # present when status=completed
    error:      Optional[str]   = None            # present when status=failed

