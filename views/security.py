"""Honest statement of implemented security controls and production gaps."""
from __future__ import annotations

import streamlit as st

from hub import ui
from hub.i18n import lang, t

IMPLEMENTED = {
    "en": [
        "Passwords hashed with salted PBKDF2-SHA256 (150,000 iterations); plain passwords are never stored.",
        "No shared or hard-coded administrator password: each company administrator sets their own; the platform administrator is created from deployment secrets.",
        "Account lock-out for 15 minutes after 5 failed sign-ins; generic error messages (no user enumeration).",
        "Company-level data isolation: every query is filtered by the company id of the signed-in user, never by a value from the browser.",
        "Role-based permissions for 9 roles; menus and edit actions are hidden and refused for unauthorised roles.",
        "One-time password-reset codes (hashed, 30-minute expiry) and admin-issued one-time temporary passwords.",
        "Audit log of sign-ins, failed sign-ins and every important change (who, what, when).",
        "SMTP password read from a secret, never stored in the database.",
        "No automatic reassignment, deadline change, access grant or incident confirmation: a human decision is always required.",
    ],
    "fr": [
        "Mots de passe hachés avec PBKDF2-SHA256 salé (150 000 itérations) ; aucun mot de passe en clair.",
        "Aucun mot de passe administrateur partagé ou codé en dur : chaque administrateur choisit le sien ; l'administrateur de la plateforme est créé depuis les secrets de déploiement.",
        "Verrouillage du compte 15 minutes après 5 échecs ; messages d'erreur génériques.",
        "Isolation des données par entreprise : chaque requête est filtrée par l'identifiant d'entreprise de l'utilisateur connecté.",
        "Droits par rôle (9 rôles) ; menus et actions refusés aux rôles non autorisés.",
        "Codes de réinitialisation à usage unique (hachés, 30 minutes) et mots de passe temporaires émis par l'administrateur.",
        "Journal d'audit des connexions, échecs et modifications importantes.",
        "Mot de passe SMTP lu depuis un secret, jamais stocké en base.",
        "Aucune réaffectation, modification d'échéance, ouverture d'accès ou confirmation d'incident automatique.",
    ],
}
GAPS = {
    "en": [
        "Multi-factor authentication (TOTP / SSO with an identity provider).",
        "Database-level isolation (e.g. PostgreSQL row-level security or one schema per tenant) instead of application-level filtering on SQLite.",
        "Persistent managed database with backups: on Streamlit Community Cloud the SQLite file is reset when the app restarts.",
        "Password-reset e-mails require a configured SMTP account; HTTPS and secure cookies are provided by the hosting platform only.",
        "Rate limiting and bot protection on registration / sign-in; e-mail verification of new companies.",
        "Encryption of sensitive fields at rest, data retention rules and a GDPR data-subject request process for the platform itself.",
        "Independent penetration test, dependency scanning and a formal secure development lifecycle.",
        "Integration with real identity providers to actually disable accounts (currently status tracking only).",
    ],
    "fr": [
        "Authentification multifacteur (TOTP / SSO avec un fournisseur d'identité).",
        "Isolation au niveau base de données (sécurité au niveau ligne PostgreSQL ou schéma par client) au lieu d'un filtrage applicatif sur SQLite.",
        "Base de données gérée et persistante avec sauvegardes : sur Streamlit Community Cloud, le fichier SQLite est réinitialisé au redémarrage.",
        "Les e-mails de réinitialisation nécessitent un compte SMTP configuré ; HTTPS est fourni par l'hébergeur.",
        "Limitation de débit et protection anti-robots ; vérification de l'e-mail des nouvelles entreprises.",
        "Chiffrement des champs sensibles, règles de conservation et processus de demandes RGPD pour la plateforme elle-même.",
        "Test d'intrusion indépendant, analyse des dépendances et cycle de développement sécurisé formalisé.",
        "Intégration avec de vrais fournisseurs d'identité pour désactiver les comptes (actuellement suivi de statut uniquement).",
    ],
}


def render(ctx: dict) -> None:
    ui.page_header("security", t("Security notes"), t("What is implemented in this prototype, and what is still required for production"))
    L = "fr" if lang() == "fr" else "en"
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("✅ " + t("Implemented"))
        for x in IMPLEMENTED[L]:
            st.markdown(f"- {x}")
    with c2:
        st.subheader("🚧 " + t("Required before production"))
        for x in GAPS[L]:
            st.markdown(f"- {x}")
    st.subheader("🧠 " + t("About the 'AI' in this prototype"))
    st.markdown(t("Risk detection is rule-based and explainable. No machine-learning model has been trained and no external AI service is called. "
                  "The module hub/ai_interface.py defines the interface where a trained model or a language model can be integrated later."))
