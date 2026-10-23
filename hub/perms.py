"""Role-based permissions: which roles can view / edit each module."""
from __future__ import annotations

CA, PM, TL, EMP, HR, RC, FIN, SUB, PA = (
    "Company Administrator", "Project Manager", "Team Leader", "Employee",
    "HR / Training Manager", "Risk / Compliance Manager", "Finance Manager", "Subcontractor",
    "Platform Administrator",
)
MANAGERS = {CA, PM, TL, HR, RC, FIN}

# page key -> (roles that can view, roles that can edit)
PAGES: dict[str, tuple[set, set]] = {
    "dashboard":      (MANAGERS, set()),
    "my_work":        ({EMP, SUB, TL, PM}, {EMP, SUB, TL, PM}),
    "employees":      ({CA, PM, TL, HR, RC}, {CA, HR}),
    "allocation":     ({CA, PM, TL, HR}, {CA, PM}),
    "absences":       ({CA, PM, TL, HR}, {CA, PM, TL, HR}),
    "projects":       ({CA, PM, TL, FIN, RC}, {CA, PM}),
    "tasks":          ({CA, PM, TL}, {CA, PM, TL}),
    "gantt":          ({CA, PM, TL, EMP, RC}, {CA, PM}),
    "budget":         ({CA, PM, FIN}, {CA, FIN}),
    "risks":          ({CA, PM, TL, RC, HR, FIN}, {CA, PM, RC}),
    "risk_areas":     ({CA, RC, PM}, {CA, RC}),
    "onboarding":     ({CA, HR, TL, PM}, {CA, HR}),
    "access":         ({CA, HR, RC, PM}, {CA, HR, RC}),
    "subcontractors": ({CA, PM, RC, FIN}, {CA, PM, RC}),
    "clients":        ({CA, PM, RC, FIN}, {CA, PM}),
    "gdpr":           ({CA, RC}, {CA, RC}),
    "notifications":  ({CA, RC, PM}, {CA}),
    "reports":        ({CA, PM, RC, HR, FIN}, set()),
    "audit":          ({CA, RC}, set()),
    "users":          ({CA}, {CA}),
    "settings":       ({CA}, {CA}),
    "security":       (MANAGERS | {EMP, SUB}, set()),
    "platform":       ({PA}, {PA}),
}

# Roles allowed to see contract values (spec 18: "where authorized")
CONTRACT_VALUE_ROLES = {CA, FIN}


def can_view(role: str, page: str) -> bool:
    return role in PAGES.get(page, (set(), set()))[0]


def can_edit(role: str, page: str) -> bool:
    return role in PAGES.get(page, (set(), set()))[1]
