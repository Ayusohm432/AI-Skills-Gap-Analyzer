from datetime import datetime
from typing import List, Optional, Any, Dict
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
    hashed_password: Optional[str] = None  # None for pure OAuth users
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    analysis_history: List[PyObjectId] = []
    target_role: Optional[str] = None
    skills: List[str] = []
    # ── Auth provider fields ───────────────────────────────────────────
    github_username: Optional[str] = None
    auth_provider: Optional[str] = Field(
        default="local",
        description="local | google | github | supabase",
    )
    oauth_provider_id: Optional[str] = None
    email_verified: bool = False
    picture: Optional[str] = None
    github_access_token: Optional[str] = Field(default=None, description="Encrypted GitHub OAuth token")
    github_refresh_token: Optional[str] = Field(default=None, description="Encrypted GitHub OAuth refresh token")


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
                "skills": ["Python", "FastAPI"],
                "github_username": "octocat",
                "auth_provider": "local",
                "email_verified": True,
                "picture": None,
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
    # ── Auth / provider fields ─────────────────────────────────────────
    github_username: Optional[str] = None
    auth_provider: Optional[str] = Field(
        default="local",
        description="local | google | github | supabase",
    )
    oauth_provider_id: Optional[str] = None
    email_verified: bool = False
    picture: Optional[str] = Field(
        default=None,
        description="Profile photo URL (populated from OAuth provider)",
    )

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
                "skills": ["Python", "FastAPI"],
                "github_username": "octocat",
                "auth_provider": "github",
                "oauth_provider_id": "12345678",
                "email_verified": True,
                "picture": "https://avatars.githubusercontent.com/u/12345678",
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
    github_username: Optional[str] = None

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
        json_schema_extra={
            "example": {
                "name": "Updated User Name",
                "target_role": "Full-Stack Developer",
                "skills": ["Python", "FastAPI", "React", "MongoDB"],
                "github_username": "octocat"
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
    analysis_id:          Optional[str] = Field(default=None, description="The DB ID of the generated analysis")
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
    role_probabilities:    dict                    = Field(default_factory=dict,
                                                           description="Full {role: probability} map for all roles")
    top_predictive_skills: List[str]               = Field(default_factory=list,
                                                           description="User's skills most predictive for the predicted role")
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
                "role_probabilities": {
                    "Data Scientist": 0.92,
                    "ML Engineer": 0.06,
                    "Backend Developer": 0.01,
                    "Frontend Developer": 0.01,
                },
                "top_predictive_skills": ["Python", "scikit-learn", "Pandas"],
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
    job_id:            str
    status:            str = "pending"
    message:           str = "Analysis job queued. Poll /api/v1/jobs/{job_id} for results."
    estimated_seconds: int = 30   # rough SLA hint so the frontend can set polling intervals


class JobStatusResponse(BaseModel):
    """Returned by GET /api/v1/jobs/{job_id}."""
    job_id:     str
    status:     str                          # pending | processing | completed | failed
    # Pipeline step progress (1-9; set during processing; 9 = storage done)
    step:       Optional[int] = None
    step_name:  Optional[str] = None
    filename:   Optional[str]   = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    result:     Optional[AnalysisResult] = None   # present when status=completed
    error:      Optional[str]   = None            # present when status=failed


# ── /predict-role endpoint models ────────────────────────────────────────────

class PredictRoleRequest(BaseModel):
    """Request body for POST /api/v1/predict-role."""
    skills: List[str] = Field(
        ...,
        min_length=1,
        description="List of skills extracted from a resume or entered manually.",
        json_schema_extra={"example": ["Python", "Pandas", "scikit-learn", "SQL", "TensorFlow"]},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"skills": ["Python", "Pandas", "scikit-learn", "SQL", "TensorFlow"]}
        }
    )


class PredictRoleResponse(BaseModel):
    """
    Response for the synchronous POST /api/v1/predict-role endpoint.

    Provides the Random Forest role prediction together with interpretability
    fields so the frontend can display *why* a role was chosen.
    """
    predicted_role:        str              = Field(description="Best-matching role or 'Auto Detect' when confidence is low")
    confidence:            float            = Field(ge=0.0, le=1.0, description="Model confidence (0–1)")
    role_probabilities:    dict             = Field(description="Full {role: probability} map")
    top_predictive_skills: List[str]        = Field(description="User skills most predictive for the result")
    role_alternatives:     List[RoleAlternative] = Field(default_factory=list,
                                                         description="Next-best role predictions")
    inference_ms:          float            = Field(default=0.0, description="Server-side inference time in ms")
    source:                str              = Field(description="'ml' | 'low_confidence' | 'fallback'")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "predicted_role": "Data Scientist",
                "confidence": 0.87,
                "role_probabilities": {
                    "Data Scientist": 0.87,
                    "ML Engineer": 0.09,
                    "Backend Developer": 0.04,
                },
                "top_predictive_skills": ["Python", "scikit-learn", "Pandas"],
                "role_alternatives": [
                    {"role": "ML Engineer", "confidence": 0.09},
                ],
                "inference_ms": 3.7,
                "source": "ml",
            }
        }
    )


# ── GitHub Integration models ─────────────────────────────────────────────────

class GithubAnalyzeRequest(BaseModel):
    """
    Request body for POST /api/v1/analyze/github.

    Fields
    ------
    github_username : str
        Public GitHub username to analyse (e.g. "octocat").
    resume_skills   : list[str]
        Optional skills already extracted from a resume.  They are
        union-merged with GitHub-derived skills — no duplicates.
    max_repos       : int
        Maximum number of repositories to inspect (1-30, default 10).
        Repositories are sorted by star count, forks excluded first.
    """
    github_username: str = Field(
        ...,
        min_length=1,
        max_length=39,   # GitHub username max length
        description="Public GitHub username",
        json_schema_extra={"example": "octocat"},
    )
    resume_skills: List[str] = Field(
        default_factory=list,
        description="Skills already detected from a resume (optional)",
        json_schema_extra={"example": ["Python", "Docker"]},
    )
    max_repos: int = Field(
        default=10,
        ge=1,
        le=30,
        description="Maximum repositories to inspect (1-30)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "github_username": "octocat",
                "resume_skills": ["Python", "Docker"],
                "max_repos": 10,
            }
        }
    )


class GithubAnalyzeResponse(BaseModel):
    """
    Response for POST /api/v1/analyze/github.

    Fields
    ------
    github_username  : echo of the requested username
    repos_analyzed   : number of repositories actually inspected
    github_skills    : canonical skills extracted from GitHub data alone
    resume_skills    : skills that were passed in from a resume (echoed back)
    merged_skills    : deduplicated union of github_skills + resume_skills
    skill_categories : merged_skills grouped into frontend/backend/devops/data
    languages_found  : raw GitHub language -> occurrence-count map
    topics_found     : deduplicated repository topic tags
    source           : always "github" for provenance tracking
    """
    github_username:  str        = Field(description="Requested GitHub username")
    repos_analyzed:   int        = Field(description="Number of repositories inspected")
    github_skills:    List[str]  = Field(description="Skills extracted from GitHub data")
    resume_skills:    List[str]  = Field(description="Resume skills supplied in the request")
    merged_skills:    List[str]  = Field(description="Deduplicated union of all skill sources")
    skill_categories: dict       = Field(
        description="Merged skills grouped by domain (frontend/backend/devops/data)"
    )
    languages_found:  dict       = Field(
        description="GitHub-reported language names and their repository occurrence counts"
    )
    topics_found:     List[str]  = Field(description="Deduplicated repository topic tags")
    source:           str        = Field(default="github", description="Data provenance marker")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "github_username":  "octocat",
                "repos_analyzed":   8,
                "github_skills":    ["Python", "TypeScript", "Docker"],
                "resume_skills":    ["Python", "Docker"],
                "merged_skills":    ["Python", "TypeScript", "Docker"],
                "skill_categories": {
                    "backend":  ["Python"],
                    "frontend": ["TypeScript"],
                    "devops":   ["Docker"],
                    "data":     [],
                },
                "languages_found": {"Python": 5, "TypeScript": 3},
                "topics_found":    ["machine-learning", "api"],
                "source":          "github",
            }
        }
    )


# ── Mock Interview Models ───────────────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    analysis_id: Optional[str] = Field(
        None, 
        description="ID of the analysis to use for context. If omitted, the latest completed analysis for the user is used."
    )

class InterviewResponseRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000, description="User's response to the interviewer's question")

class InterviewSessionResponse(BaseModel):
    session_id: str
    status: str = Field("active", description="Current status of the session (active/completed/expired)")
    message: str = Field(..., description="The interviewer's next question or feedback")
    history: List[Dict[str, str]] = Field(default_factory=list, description="The full conversation history so far")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "60d5ecb8b392d3001f3b3b3b",
                "status": "active",
                "message": "That's a great explanation of Python decorators. How would you handle a scenario where you need to preserve the metadata of the original function?",
                "history": [
                    {"role": "assistant", "content": "Welcome to your mock interview for the Python Backend Developer role. Let's start with decorators. Can you explain how they work?"},
                    {"role": "user", "content": "Sure, decorators are functions that wrap other functions to modify their behavior."}
                ]
            }
        }
    )

# ── Readiness Levels Models ───────────────────────────────────────────────────

class ReadinessLevel(BaseModel):
    score: float = Field(ge=0.0, le=100.0)
    matched_skills: List[str]
    missing_skills: List[str]
    required_skills: List[str]

class ReadinessLevelResponse(BaseModel):
    role: str
    beginner: Optional[ReadinessLevel] = None
    intermediate: Optional[ReadinessLevel] = None
    advanced: Optional[ReadinessLevel] = None
    no_analysis: bool = False


# ── Market Companies & Work Mode Models ────────────────────────────────────

class CompanyInfo(BaseModel):
    name:      str = Field(description="Company name")
    logo_url:  str = Field(description="URL to the company's logo image")
    job_count: int = Field(description="Approximate number of open positions for this role")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name":      "Google",
                "logo_url":  "https://logo.clearbit.com/google.com",
                "job_count": 120,
            }
        }
    }


class TopCompaniesResponse(BaseModel):
    role:      str              = Field(description="Target job role queried")
    companies: List[CompanyInfo] = Field(description="Top hiring companies for the role (up to 5)")
    data_source: str            = Field(default="seeded", description="'seeded' | 'live'")

    model_config = {
        "json_schema_extra": {
            "example": {
                "role": "Backend Developer",
                "data_source": "seeded",
                "companies": [
                    {"name": "Google",    "logo_url": "https://logo.clearbit.com/google.com",    "job_count": 120},
                    {"name": "Amazon",   "logo_url": "https://logo.clearbit.com/amazon.com",    "job_count": 95},
                    {"name": "Flipkart", "logo_url": "https://logo.clearbit.com/flipkart.com", "job_count": 80},
                    {"name": "Razorpay", "logo_url": "https://logo.clearbit.com/razorpay.com", "job_count": 45},
                    {"name": "Swiggy",   "logo_url": "https://logo.clearbit.com/swiggy.com",   "job_count": 38},
                ],
            }
        }
    }


class WorkModeBreakdown(BaseModel):
    remote: float  = Field(ge=0.0, le=100.0, description="Percentage of remote positions")
    hybrid: float  = Field(ge=0.0, le=100.0, description="Percentage of hybrid positions")
    onsite: float  = Field(ge=0.0, le=100.0, description="Percentage of onsite positions")


class WorkModeResponse(BaseModel):
    role:        str               = Field(description="Target job role queried")
    breakdown:   WorkModeBreakdown = Field(description="Work mode percentage breakdown")
    data_source: str               = Field(default="seeded", description="'seeded' | 'live'")

    model_config = {
        "json_schema_extra": {
            "example": {
                "role": "Backend Developer",
                "data_source": "seeded",
                "breakdown": {"remote": 35.0, "hybrid": 45.0, "onsite": 20.0},
            }
        }
    }
