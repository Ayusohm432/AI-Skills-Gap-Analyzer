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


# ── Job / Background-task models ──────────────────────────────────────────────

class AnalysisResult(BaseModel):
    """Full analysis payload stored inside a completed job document."""
    target_role:        str
    skills_detected:    List[str]
    skill_confidences:  dict = {}
    missing_skills:     List[str]
    readiness_score:    float
    roadmap:            list
    interview_questions: List[str]
    ml_role_source:     Optional[str] = None
    ml_missing_source:  Optional[str] = None


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

