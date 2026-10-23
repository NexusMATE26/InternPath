"""Deterministic database seed script for InternPath AI.

Usage:
    python -m app.seed          # Idempotently seed default data
    python -m app.seed --reset  # Clean existing demo data and reseed
"""
import sys
from sqlalchemy.orm import Session
from .database import engine, SessionLocal
from .models import (
    Student,
    Skill,
    StudentSkill,
    EvidenceItem,
    Role,
    RoleRequirement,
    SkillPrerequisite,
)
from .crud import (
    DEV_STUDENT_EMAIL,
    DEV_STUDENT_NAME,
    validate_no_prerequisite_cycles,
)

DEMO_SKILLS = [
    {
        "id": 1,
        "name": "Programming Foundations",
        "category": "Foundations",
        "max_level": 3,
        "description": "Core logic, variables, control flow, functions, and algorithmic thinking.",
    },
    {
        "id": 2,
        "name": "Python Programming",
        "category": "Languages",
        "max_level": 3,
        "description": "Idiomatic Python, OOP, typing, data manipulation, and packaging.",
    },
    {
        "id": 3,
        "name": "C++ Systems Programming",
        "category": "Languages",
        "max_level": 3,
        "description": "C++20 standards, manual memory management, RAII, move semantics, and templates.",
    },
    {
        "id": 4,
        "name": "Backend APIs (FastAPI)",
        "category": "Backend",
        "max_level": 3,
        "description": "RESTful API design, async execution, Pydantic schemas, and HTTP protocols.",
    },
    {
        "id": 5,
        "name": "Data Structures & Algorithms",
        "category": "Algorithms",
        "max_level": 3,
        "description": "AVL trees, hash tables, graphs, heaps, dynamic programming, and amortized analysis.",
    },
    {
        "id": 6,
        "name": "High-Scale Distributed Systems",
        "category": "Systems",
        "max_level": 3,
        "description": "Consensus protocols, caching strategies, replication, and microservice architectures.",
    },
    {
        "id": 7,
        "name": "Git & Linux Fundamentals",
        "category": "Tools",
        "max_level": 3,
        "description": "Bash scripting, Unix toolchains, branching strategies, and CI workflows.",
    },
    {
        "id": 8,
        "name": "Docker & Containerization",
        "category": "DevOps",
        "max_level": 3,
        "description": "Container image construction, volume mounting, compose networks, and multi-stage builds.",
    },
    {
        "id": 9,
        "name": "Relational Databases & SQL",
        "category": "Backend",
        "max_level": 3,
        "description": "Relational schema normalization, indexing, query optimization, and transactions.",
    },
    {
        "id": 10,
        "name": "Cloud Deployment & K8s",
        "category": "DevOps",
        "max_level": 3,
        "description": "Kubernetes orchestration, Pod management, cloud networking, and observability.",
    },
]

DEMO_PREREQUISITES = [
    (1, 2),  # Foundations -> Python
    (1, 3),  # Foundations -> C++
    (2, 4),  # Python -> FastAPI
    (9, 4),  # SQL -> FastAPI
    (3, 5),  # C++ -> DSA
    (4, 6),  # FastAPI -> Distributed Systems
    (5, 6),  # DSA -> Distributed Systems
    (7, 8),  # Git/Linux -> Docker
    (8, 10), # Docker -> Kubernetes
]

DEMO_ROLES = [
    {
        "role_id": "distributed-systems-intern",
        "title": "Distributed Systems Engineering Intern",
        "department": "Infrastructure & Platform Architecture",
        "location": "San Francisco, CA (Hybrid / Remote)",
        "description": "Design and benchmark high-scale distributed services, fault-tolerant replication, and containerized clusters.",
        "requirements": [
            {
                "skill_id": 6,
                "required_level": 3,
                "mandatory": True,
                "role_context": "Core requirement for distributed consensus and cluster operations",
            },
            {
                "skill_id": 10,
                "required_level": 2,
                "mandatory": False,
                "role_context": "Preferred for staging deployments and container orchestration",
            },
        ],
    },
    {
        "role_id": "backend-api-intern",
        "title": "Backend Platform Engineering Intern",
        "department": "Core Product Engineering",
        "location": "New York, NY (Remote)",
        "description": "Build high-throughput async services, structured database schemas, and microservice integrations.",
        "requirements": [
            {
                "skill_id": 4,
                "required_level": 2,
                "mandatory": True,
                "role_context": "Core requirement for REST endpoint delivery and middleware",
            },
            {
                "skill_id": 9,
                "required_level": 2,
                "mandatory": True,
                "role_context": "Core requirement for relational modeling and transactions",
            },
            {
                "skill_id": 8,
                "required_level": 1,
                "mandatory": False,
                "role_context": "Preferred for local microservice containerized dev environment",
            },
        ],
    },
]

DEMO_STUDENT = {
    "name": DEV_STUDENT_NAME,
    "email": DEV_STUDENT_EMAIL,
    "target_role_id": "distributed-systems-intern",
    "weekly_hours": 15,
    "skills": [
        {"skill_id": 1, "declared_level": 2, "verified_level": 2, "is_verified": True},
        {"skill_id": 2, "declared_level": 2, "verified_level": 2, "is_verified": True},
        {"skill_id": 7, "declared_level": 1, "verified_level": 0, "is_verified": False},
    ],
    "evidence": [
        {
            "skill_id": 1,
            "title": "CS101 Intro to Programming",
            "description": "Coursework in core algorithmic foundations and data structures",
            "url": "https://github.com/alexchen/cs101-assignments",
            "evidence_type": "course",
            "verified_by_staff": True,
        },
        {
            "skill_id": 2,
            "title": "Async Web Scraper",
            "description": "Built async scraper handling 50 req/sec with aiohttp and pydantic",
            "url": "https://github.com/alexchen/fast-scraper",
            "evidence_type": "project",
            "verified_by_staff": True,
        },
        {
            "skill_id": 7,
            "title": "Homelab Linux Server",
            "description": "Configured Ubuntu server with systemd services and SSH hardening",
            "url": "https://github.com/alexchen/homelab-infra",
            "evidence_type": "project",
            "verified_by_staff": False,
        },
    ],
}


def reset_database(db: Session) -> None:
    """Clear all records in reverse foreign key order."""
    db.query(EvidenceItem).delete()
    db.query(StudentSkill).delete()
    db.query(Student).delete()
    db.query(RoleRequirement).delete()
    db.query(Role).delete()
    db.query(SkillPrerequisite).delete()
    db.query(Skill).delete()
    db.commit()


def seed_database(db: Session, reset: bool = False) -> None:
    if reset:
        print("[seed] Resetting existing database records...")
        reset_database(db)

    # 1. Seed Skills
    print("[seed] Seeding canonical skills (0-3 scale)...")
    for s_data in DEMO_SKILLS:
        skill = db.query(Skill).filter(Skill.id == s_data["id"]).first()
        if not skill:
            skill = Skill(
                id=s_data["id"],
                name=s_data["name"],
                category=s_data["category"],
                max_level=s_data["max_level"],
                description=s_data["description"],
                is_demo=True,
            )
            db.add(skill)
        else:
            skill.name = s_data["name"]
            skill.category = s_data["category"]
            skill.max_level = s_data["max_level"]
            skill.description = s_data["description"]
    db.commit()

    # 2. Seed Prerequisites with cycle validation
    print("[seed] Seeding prerequisite relationships with DAG cycle validation...")
    for prereq_id, skill_id in DEMO_PREREQUISITES:
        edge = (
            db.query(SkillPrerequisite)
            .filter(
                SkillPrerequisite.prerequisite_id == prereq_id,
                SkillPrerequisite.skill_id == skill_id,
            )
            .first()
        )
        if not edge:
            validate_no_prerequisite_cycles(db, prereq_id, skill_id)
            db.add(SkillPrerequisite(prerequisite_id=prereq_id, skill_id=skill_id))
    db.commit()

    # 3. Seed Roles & Requirements
    print("[seed] Seeding internship catalogue roles and competency requirements...")
    for r_data in DEMO_ROLES:
        role = db.query(Role).filter(Role.role_id == r_data["role_id"]).first()
        if not role:
            role = Role(
                role_id=r_data["role_id"],
                title=r_data["title"],
                department=r_data["department"],
                location=r_data["location"],
                description=r_data["description"],
                is_demo=True,
            )
            db.add(role)
            db.commit()
            db.refresh(role)

        for req in r_data["requirements"]:
            existing_req = (
                db.query(RoleRequirement)
                .filter(
                    RoleRequirement.role_id == role.role_id,
                    RoleRequirement.skill_id == req["skill_id"],
                )
                .first()
            )
            if not existing_req:
                db.add(
                    RoleRequirement(
                        role_id=role.role_id,
                        skill_id=req["skill_id"],
                        required_level=req["required_level"],
                        mandatory=req["mandatory"],
                        role_context=req["role_context"],
                    )
                )
    db.commit()

    # 4. Seed Dev Student Profile & Evidence
    print("[seed] Seeding dev student profile and portfolio evidence...")
    student = db.query(Student).filter(Student.email == DEMO_STUDENT["email"]).first()
    if not student:
        student = Student(
            name=DEMO_STUDENT["name"],
            email=DEMO_STUDENT["email"],
            target_role_id=DEMO_STUDENT["target_role_id"],
            weekly_hours=DEMO_STUDENT["weekly_hours"],
            is_demo=True,
        )
        db.add(student)
        db.commit()
        db.refresh(student)

    for sk in DEMO_STUDENT["skills"]:
        st_skill = (
            db.query(StudentSkill)
            .filter(
                StudentSkill.student_id == student.id,
                StudentSkill.skill_id == sk["skill_id"],
            )
            .first()
        )
        if not st_skill:
            db.add(
                StudentSkill(
                    student_id=student.id,
                    skill_id=sk["skill_id"],
                    declared_level=sk["declared_level"],
                    verified_level=sk["verified_level"],
                    is_verified=sk["is_verified"],
                )
            )

    for ev in DEMO_STUDENT["evidence"]:
        existing_ev = (
            db.query(EvidenceItem)
            .filter(
                EvidenceItem.student_id == student.id,
                EvidenceItem.skill_id == ev["skill_id"],
                EvidenceItem.title == ev["title"],
            )
            .first()
        )
        if not existing_ev:
            db.add(
                EvidenceItem(
                    student_id=student.id,
                    skill_id=ev["skill_id"],
                    title=ev["title"],
                    description=ev["description"],
                    url=ev["url"],
                    evidence_type=ev["evidence_type"],
                    verified_by_staff=ev["verified_by_staff"],
                )
            )
    db.commit()
    print("[seed] Database seeding completed successfully.")


def main():
    reset = "--reset" in sys.argv
    db = SessionLocal()
    try:
        seed_database(db, reset=reset)
    finally:
        db.close()


if __name__ == "__main__":
    main()
