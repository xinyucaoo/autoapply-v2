from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class Address(BaseModel):
    street: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    country: str = ""


class Personal(BaseModel):
    first_name: str = ""
    last_name: str = ""
    preferred_name: str | None = None
    pronouns: str | None = None
    email: str = ""
    phone: str = ""
    address: Address = Address()
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    github_url: str | None = None


class WorkAuthorization(BaseModel):
    authorized_us: bool = True
    sponsorship_needed: bool = False
    citizenship: str = ""
    visa_status: str | None = None


class Education(BaseModel):
    school: str = ""
    degree: str = ""
    field: str = ""
    graduation_date: str = ""  # "2020-05" YYYY-MM
    gpa: str | None = None


class Experience(BaseModel):
    company: str = ""
    title: str = ""
    start_date: str = ""  # "2020-06" YYYY-MM
    end_date: str | None = None  # None = current
    description: str = ""
    location: str | None = None


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
    date: str | None = None


class EEO(BaseModel):
    gender: str | None = None
    race_ethnicity: str | None = None
    veteran_status: str | None = None
    disability_status: str | None = None


class CustomQA(BaseModel):
    question: str = ""   # Pattern / substring to match field labels
    answer: str = ""
    scope: str | None = None     # Optional company or role scope
    policy: str = "autofill"


class Salary(BaseModel):
    minimum: int | None = None
    desired: int | None = None
    currency: str = "USD"


class Preferences(BaseModel):
    remote_preference: str | None = None   # "remote", "hybrid", "onsite"
    relocation_willing: bool | None = None
    desired_start_date: str | None = None
    years_of_experience: int | None = None


class Document(BaseModel):
    name: str = ""   # "default_resume", "swe_resume", etc.
    path: str = ""   # Absolute path
    type: Literal["resume", "cover_letter", "other"] = "resume"
    default: bool = False


class Profile(BaseModel):
    personal: Personal = Personal()
    work_authorization: WorkAuthorization = WorkAuthorization()
    education: list[Education] = []
    experience: list[Experience] = []
    skills: list[str] = []
    certifications: list[Certification] = []
    eeo: EEO | None = None
    documents: list[Document] = []
    cover_letter: str | None = None
    custom_qa: list[CustomQA] = []
    salary: Salary | None = None
    preferences: Preferences | None = None
    answer_policies: dict[str, str] = {}
