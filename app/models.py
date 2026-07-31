"""Modèles : politiciens, parcours (mandats), liens d'intérêts, débats, résumés, posts IG."""
from datetime import datetime, date
from sqlalchemy import (String, Integer, Boolean, Date, DateTime, Text,
                        ForeignKey, UniqueConstraint, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Politician(Base):
    """Toute personnalité publique suivie : parlementaires fédéraux, conseillers
    fédéraux, juges fédéraux, élus cantonaux… Identifiée par (source, source_id)."""
    __tablename__ = "politicians"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # interne
    source: Mapped[str] = mapped_column(String(30), default="parlament")  # parlament | bger | canton-XX | csv
    source_id: Mapped[str] = mapped_column(String(50))  # ex. PersonNumber du Parlement
    role_type: Mapped[str] = mapped_column(String(30), default="parliament", index=True)
    # parliament | federal_council | federal_judge | cantonal_exec | cantonal_parl
    level: Mapped[str] = mapped_column(String(20), default="federal")  # federal | cantonal
    institution: Mapped[str | None] = mapped_column(String(200))  # ex. Tribunal fédéral, Conseil d'État VD
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    party_abbr: Mapped[str | None] = mapped_column(String(20))
    party_name: Mapped[str | None] = mapped_column(String(200))
    canton: Mapped[str | None] = mapped_column(String(50))
    canton_abbr: Mapped[str | None] = mapped_column(String(5))
    council: Mapped[str | None] = mapped_column(String(50))   # Conseil national / Conseil des États
    birth_year: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(1))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    date_joining: Mapped[date | None] = mapped_column(Date)
    lobbywatch_id: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)

    mandates: Mapped[list["Mandate"]] = relationship(back_populates="politician",
                                                     cascade="all, delete-orphan")
    interests: Mapped[list["Interest"]] = relationship(back_populates="politician",
                                                       cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_person_source"),)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Mandate(Base):
    """Une étape du parcours : conseil, parti, commission, profession."""
    __tablename__ = "mandates"

    id: Mapped[int] = mapped_column(primary_key=True)
    politician_id: Mapped[int] = mapped_column(ForeignKey("politicians.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # council | party | committee | occupation
    label: Mapped[str] = mapped_column(String(300))
    organization: Mapped[str | None] = mapped_column(String(300))
    start: Mapped[date | None] = mapped_column(Date)
    end: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(50))

    politician: Mapped["Politician"] = relationship(back_populates="mandates")

    __table_args__ = (UniqueConstraint("politician_id", "kind", "label", "start",
                                       name="uq_mandate"),)


class Interest(Base):
    """Lien d'intérêts : organisation, fonction, secteur, rémunération."""
    __tablename__ = "interests"

    id: Mapped[int] = mapped_column(primary_key=True)
    politician_id: Mapped[int] = mapped_column(ForeignKey("politicians.id"), index=True)
    organization: Mapped[str] = mapped_column(String(300))
    function: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(120), index=True)
    paid: Mapped[str | None] = mapped_column(String(20))  # oui | non | inconnu
    since: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(50), default="lobbywatch")

    politician: Mapped["Politician"] = relationship(back_populates="interests")

    __table_args__ = (UniqueConstraint("politician_id", "organization", "function",
                                       name="uq_interest"),)


class Debate(Base):
    """Un débat = un objet traité un jour donné dans un conseil (regroupe les retranscriptions)."""
    __tablename__ = "debates"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    council_abbr: Mapped[str | None] = mapped_column(String(10))  # N / S
    subject_id: Mapped[str] = mapped_column(String(50))           # IdSubject de l'API
    business_number: Mapped[str | None] = mapped_column(String(30))
    raw_title: Mapped[str | None] = mapped_column(String(500))
    transcript_count: Mapped[int] = mapped_column(Integer, default=0)
    groups: Mapped[str | None] = mapped_column(String(200))  # partis impliqués, ex. "PS|UDC|PLR"
    raw_text_path: Mapped[str | None] = mapped_column(String(300))  # texte brut archivé sur disque
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    summaries: Mapped[list["Summary"]] = relationship(back_populates="debate",
                                                      cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("day", "council_abbr", "subject_id",
                                       name="uq_debate"),
                      Index("ix_debate_day_council", "day", "council_abbr"))


class Summary(Base):
    """Résumé d'un débat dans une langue : contexte, tenants/aboutissants, issue."""
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    debate_id: Mapped[int] = mapped_column(ForeignKey("debates.id"), index=True)
    lang: Mapped[str] = mapped_column(String(2))  # fr | de | it
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)       # de quoi il s'agit + positions
    stakes: Mapped[str | None] = mapped_column(Text)   # tenants et aboutissants
    outcome: Mapped[str | None] = mapped_column(Text)  # issue / prochaine étape
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    debate: Mapped["Debate"] = relationship(back_populates="summaries")

    __table_args__ = (UniqueConstraint("debate_id", "lang", name="uq_summary_lang"),)


class IGPost(Base):
    __tablename__ = "ig_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True)
    caption: Mapped[str | None] = mapped_column(Text)
    image_paths: Mapped[str | None] = mapped_column(Text)  # chemins séparés par |
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    ig_published_at: Mapped[datetime | None] = mapped_column(DateTime)
    fb_published_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    """Paramètres modifiables depuis le panel admin (ex. identifiants Meta).
    Prioritaires sur les variables d'environnement équivalentes."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="user")  # user | admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    alerts: Mapped[list["Alert"]] = relationship(back_populates="user",
                                                 cascade="all, delete-orphan")


class Alert(Base):
    """Alerte par mots-clés : l'utilisateur est notifié par e-mail quand un
    résumé quotidien contient l'un de ses mots-clés."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    keywords: Mapped[str] = mapped_column(String(300))  # séparés par des virgules
    lang: Mapped[str] = mapped_column(String(2), default="fr")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_match_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="alerts")
