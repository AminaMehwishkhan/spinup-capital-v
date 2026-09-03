from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.models import Base, Treasury
from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(reset: bool = False):
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        if db.query(Treasury).count() == 0:
            db.add(Treasury(balance=settings.STARTING_TREASURY, note="Firm founded"))
            db.commit()
    finally:
        db.close()


def get_treasury_balance(db) -> float:
    row = db.query(Treasury).order_by(Treasury.id.desc()).first()
    return row.balance if row else settings.STARTING_TREASURY


def adjust_treasury(db, delta: float, note: str):
    balance = get_treasury_balance(db) + delta
    db.add(Treasury(balance=balance, note=note))
    db.commit()
    return balance
