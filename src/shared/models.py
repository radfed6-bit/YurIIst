import enum
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, JSON, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class DocType(str, enum.Enum):
    CONSTITUTION = "constitution"
    CODE = "code"
    FEDERAL_LAW = "federal_law"
    PRESIDENTIAL_DECREE = "presidential_decree"
    GOVERNMENT_RESOLUTION = "government_resolution"
    SANPIN = "sanpin"
    OTHER = "other"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(1000), nullable=False)
    short_title = Column(String(255))
    doc_type = Column(Enum(DocType), nullable=False, index=True)
    official_number = Column(String(100))
    adoption_date = Column(DateTime, nullable=True)
    effective_date = Column(DateTime, nullable=True)
    current_version = Column(String(50), default="original")
    source_url = Column(String(1000))
    metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    articles = relationship("Article", back_populates="document", cascade="all, delete-orphan",
                            order_by="Article.order")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    article_number = Column(String(50), nullable=False, index=True)
    title = Column(String(1000), default="")
    content = Column(Text, nullable=False)
    chapter = Column(String(500), default="")
    section = Column(String(500), default="")
    paragraph = Column(String(500), default="")
    parent_article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    order = Column(Integer, default=0)

    document = relationship("Document", back_populates="articles")

    __table_args__ = (
        Index("ix_articles_doc_number", "document_id", "article_number", unique=True),
    )
