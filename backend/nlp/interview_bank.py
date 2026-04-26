"""
interview_bank.py
=================
A repository of categorized interview questions by role, skill, and difficulty.
"""

from typing import List, Dict, Any

# General behavioral questions applicable to all roles
BEHAVIORAL_QUESTIONS = [
    {"question": "Tell me about a time you had to learn a new technology quickly.", "difficulty": "easy", "category": "behavioral"},
    {"question": "Describe a situation where you disagreed with a team member on a technical decision. How did you resolve it?", "difficulty": "medium", "category": "behavioral"},
    {"question": "Can you walk us through your most complex project, including the architecture and challenges?", "difficulty": "hard", "category": "behavioral"},
    {"question": "How do you handle tight deadlines and shifting priorities?", "difficulty": "medium", "category": "behavioral"},
    {"question": "Describe a time you failed or made a significant mistake. What did you learn?", "difficulty": "medium", "category": "behavioral"},
]

# System design questions by broad domain
SYSTEM_DESIGN_QUESTIONS = {
    "backend": [
        {"question": "How would you design a URL shortening service like bit.ly?", "difficulty": "medium", "category": "system design"},
        {"question": "Design a highly available and scalable notification system.", "difficulty": "hard", "category": "system design"},
        {"question": "How do you handle database sharding and replication for a globally distributed app?", "difficulty": "hard", "category": "system design"}
    ],
    "frontend": [
        {"question": "How would you design the front-end architecture for a real-time collaborative document editor?", "difficulty": "hard", "category": "system design"},
        {"question": "Explain how you would build a highly performant infinite scrolling feed.", "difficulty": "medium", "category": "system design"}
    ],
    "data": [
        {"question": "Design a real-time data ingestion pipeline for millions of events per second.", "difficulty": "hard", "category": "system design"},
        {"question": "How would you architect a data warehouse for a global e-commerce platform?", "difficulty": "hard", "category": "system design"}
    ],
    "general": [
        {"question": "Explain the trade-offs between monolithic and microservices architectures.", "difficulty": "medium", "category": "system design"}
    ]
}

# Technical questions mapped to specific skills
TECHNICAL_SKILL_QUESTIONS = {
    "python": [
        {"question": "Explain the difference between a list and a tuple in Python.", "difficulty": "easy", "category": "technical"},
        {"question": "How does Python's Garbage Collector work?", "difficulty": "medium", "category": "technical"},
        {"question": "What are decorators in Python and how do you write a custom one?", "difficulty": "medium", "category": "technical"}
    ],
    "java": [
        {"question": "Explain the difference between HashMap and ConcurrentHashMap.", "difficulty": "medium", "category": "technical"},
        {"question": "What is the JVM memory model and how does garbage collection work in Java?", "difficulty": "hard", "category": "technical"}
    ],
    "javascript": [
        {"question": "Explain closures in JavaScript with an example.", "difficulty": "medium", "category": "technical"},
        {"question": "How does the event loop work in Node.js/JavaScript?", "difficulty": "hard", "category": "technical"}
    ],
    "react": [
        {"question": "What is the Virtual DOM and how does React use it?", "difficulty": "medium", "category": "technical"},
        {"question": "Explain the differences between useEffect, useMemo, and useCallback hooks.", "difficulty": "medium", "category": "technical"}
    ],
    "sql": [
        {"question": "Explain the difference between INNER JOIN, LEFT JOIN, and CROSS JOIN.", "difficulty": "easy", "category": "technical"},
        {"question": "How do you optimize a slow-running SQL query?", "difficulty": "medium", "category": "technical"}
    ],
    "docker": [
        {"question": "What is the difference between a Docker image and a container?", "difficulty": "easy", "category": "technical"},
        {"question": "Explain how Docker networking works and the different network drivers.", "difficulty": "medium", "category": "technical"}
    ],
    "kubernetes": [
        {"question": "What are Pods, Services, and Deployments in Kubernetes?", "difficulty": "medium", "category": "technical"},
        {"question": "How does Kubernetes handle self-healing and auto-scaling?", "difficulty": "hard", "category": "technical"}
    ],
    "aws": [
        {"question": "What is the difference between an EC2 instance and a serverless Lambda function?", "difficulty": "medium", "category": "technical"},
        {"question": "Explain how you would secure an AWS VPC.", "difficulty": "hard", "category": "technical"}
    ],
    "machine learning": [
        {"question": "Explain the bias-variance tradeoff.", "difficulty": "medium", "category": "technical"},
        {"question": "How do you handle imbalanced datasets in classification problems?", "difficulty": "hard", "category": "technical"}
    ],
    "tensorflow": [
        {"question": "What is a computational graph in TensorFlow?", "difficulty": "medium", "category": "technical"}
    ],
    "fastapi": [
        {"question": "How does FastAPI handle asynchronous requests compared to Flask?", "difficulty": "medium", "category": "technical"}
    ]
}

def get_role_domain(role: str) -> str:
    """Map a job role to a broad domain for system design questions."""
    role_lower = role.lower()
    if "data" in role_lower or "machine learning" in role_lower or "ai" in role_lower:
        return "data"
    elif "frontend" in role_lower or "ui" in role_lower:
        return "frontend"
    elif "backend" in role_lower or "full stack" in role_lower or "devops" in role_lower:
        return "backend"
    return "general"
