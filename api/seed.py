import sys
import os

# Ensure aurum-os root is in sys.path when running as script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session
from sqlalchemy import select
from api.core.db import engine
from api.models.trade import TradeIdea
from api.models.journal import JournalEntry

def seed():
    with Session(engine) as session:
        # Check if we already have data
        if session.exec(select(TradeIdea)).first():
            print("Seed data already exists.")
            return

        print("Seeding database...")
        trade1 = TradeIdea(
            user_id="seed_user",
            symbol="XAUUSD",
            direction="LONG",
            entry_price=2045.50,
            stop_price=2030.00,
            target_price=2080.00,
            invalidation_notes="4H close below 2028 breaks market structure.",
            thesis="Bullish order block tap and sweep of Asian session lows.",
            status="Approved"
        )
        
        trade2 = TradeIdea(
            user_id="seed_user",
            symbol="XAUUSD",
            direction="SHORT",
            entry_price=2085.00,
            stop_price=2092.00,
            target_price=2060.00,
            invalidation_notes="Strong H1 close above 2095 opens door to 2100+.",
            thesis="Bearish divergence on H4 RSI, tapping into weekly supply zone.",
            status="Draft"
        )

        session.add(trade1)
        session.add(trade2)
        session.commit()
        session.refresh(trade1)
        
        journal1 = JournalEntry(
            user_id="seed_user",
            trade_idea_id=trade1.id,
            expected_behaviour="Immediate reaction from OB.",
            actual_behaviour="Chopped for 2 hours before triggering.",
            thesis_validity="Valid.",
            should_have_skipped=False,
            lesson_learned="Patience during London open transition."
        )
        session.add(journal1)
        session.commit()
        print("Success: database seeded with XAU/USD dummy data.")

if __name__ == "__main__":
    seed()
