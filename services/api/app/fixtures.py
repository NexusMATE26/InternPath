"""Curated local fixtures for InternPath AI Phase 3.1.

All records are demo fixtures for university DSA and prototype integration.
"""

from typing import Any

CURATED_SKILLS: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Programming Foundations",
        "category": "Foundations",
        "max_level": 5,
        "description": "Core logic, variables, control flow, functions, and algorithmic thinking.",
        "prerequisites": [],
        "unlocked_skills": [2, 3],
    },
    {
        "id": 2,
        "name": "Python Programming",
        "category": "Languages",
        "max_level": 5,
        "description": "Idiomatic Python, OOP, typing, data manipulation, and packaging.",
        "prerequisites": [1],
        "unlocked_skills": [4],
    },
    {
        "id": 3,
        "name": "C++ Systems Programming",
        "category": "Languages",
        "max_level": 5,
        "description": "C++20 standards, manual memory management, RAII, move semantics, and templates.",
        "prerequisites": [1],
        "unlocked_skills": [5],
    },
    {
        "id": 4,
        "name": "Backend APIs (FastAPI)",
        "category": "Backend",
        "max_level": 5,
        "description": "RESTful API design, async execution, Pydantic schemas, and HTTP protocols.",
        "prerequisites": [2, 9],
        "unlocked_skills": [6],
    },
    {
        "id": 5,
        "name": "Data Structures & Algorithms",
        "category": "Algorithms",
        "max_level": 5,
        "description": "AVL trees, hash tables, graphs, heaps, dynamic programming, and amortized analysis.",
        "prerequisites": [3],
        "unlocked_skills": [6],
    },
    {
        "id": 6,
        "name": "High-Scale Distributed Systems",
        "category": "Systems",
        "max_level": 5,
        "description": "Consensus protocols, caching strategies, replication, and microservice architectures.",
        "prerequisites": [4, 5],
        "unlocked_skills": [],
    },
    {
        "id": 7,
        "name": "Git & Linux Fundamentals",
        "category": "Tools",
        "max_level": 5,
        "description": "Bash scripting, Unix toolchains, branching strategies, and CI workflows.",
        "prerequisites": [],
        "unlocked_skills": [8],
    },
    {
        "id": 8,
        "name": "Docker & Containerization",
        "category": "DevOps",
        "max_level": 5,
        "description": "Container image construction, volume mounting, compose networks, and multi-stage builds.",
        "prerequisites": [7],
        "unlocked_skills": [10],
    },
    {
        "id": 9,
        "name": "Relational Databases & SQL",
        "category": "Backend",
        "max_level": 5,
        "description": "Relational schema normalization, indexing, query optimization, and transactions.",
        "prerequisites": [],
        "unlocked_skills": [4],
    },
    {
        "id": 10,
        "name": "Cloud Deployment & K8s",
        "category": "DevOps",
        "max_level": 5,
        "description": "Kubernetes orchestration, Pod management, cloud networking, and observability.",
        "prerequisites": [8],
        "unlocked_skills": [],
    },
]

CURATED_ROLES: list[dict[str, Any]] = [
    {
        "role_id": "distributed-systems-intern",
        "title": "Distributed Systems Engineering Intern",
        "department": "Infrastructure & Platform Architecture",
        "location": "San Francisco, CA (Hybrid / Remote)",
        "description": "Design and benchmark high-scale distributed services, fault-tolerant replication, and containerized clusters.",
        "requirements": [
            {
                "skill_id": 6,
                "skill_name": "High-Scale Distributed Systems",
                "required_level": 3,
                "mandatory": True,
                "role_context": "Core requirement for distributed consensus and cluster operations",
            },
            {
                "skill_id": 10,
                "skill_name": "Cloud Deployment & K8s",
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
                "skill_name": "Backend APIs (FastAPI)",
                "required_level": 2,
                "mandatory": True,
                "role_context": "Core requirement for REST endpoint delivery and middleware",
            },
            {
                "skill_id": 9,
                "skill_name": "Relational Databases & SQL",
                "required_level": 2,
                "mandatory": True,
                "role_context": "Core requirement for relational modeling and transactions",
            },
            {
                "skill_id": 8,
                "skill_name": "Docker & Containerization",
                "required_level": 1,
                "mandatory": False,
                "role_context": "Preferred for local microservice containerized dev environment",
            },
        ],
    },
]

DEFAULT_SAMPLE_STUDENT_SKILLS: list[dict[str, Any]] = [
    {"skill_id": 1, "level": 2, "is_verified": True},   # Programming Foundations (Verified)
    {"skill_id": 2, "level": 2, "is_verified": True},   # Python (Verified)
    {"skill_id": 7, "level": 1, "is_verified": False},  # Git & Linux (Self-Reported)
]
