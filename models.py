from sqlalchemy import Column, String, Float, Integer, DateTime, func
from sqlalchemy import Text
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class ProcessedEvent(Base):
    __tablename__ = 'processed_events'
    
    event_id = Column(String(255), primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class Position(Base):
    __tablename__ = 'positions'
    
    # ID: account_id + symbol + strategy_id
    id = Column(String(255), primary_key=True)
    account_id = Column(String(100))
    symbol = Column(String(20))
    strategy_id = Column(String(100))
    side = Column(String(10)) # 'long' or 'short'
    initial_qty = Column(Float)
    remaining_qty = Column(Float)
    status = Column(String(20), default='OPEN') # 'OPEN' or 'CLOSED'
    tp_level = Column(Integer, default=0) # Tracks TP1-TP5
    closed_qty_tp1 = Column(Float, default=0.0)  # Quantity closed at TP1
    closed_qty_tp2 = Column(Float, default=0.0)  # Quantity closed at TP2
    closed_qty_tp3 = Column(Float, default=0.0)  # Quantity closed at TP3
    closed_qty_tp4 = Column(Float, default=0.0)  # Quantity closed at TP4
    closed_qty_tp5 = Column(Float, default=0.0)  # Quantity closed at TP5
    sl_closed_qty = Column(Float, default=0.0)   # Quantity closed by stop loss
    timeguard_closed_qty = Column(Float, default=0.0)  # Quantity closed by TimeGuard
    maxbars_closed_qty = Column(Float, default=0.0)    # Quantity closed by MaxBars
    swingtp_closed_qty = Column(Float, default=0.0)    # Quantity closed by SwingTP
    dyn_tp_closed_qty = Column(Float, default=0.0)     # Quantity closed by DynTP
    other_closed_qty = Column(Float, default=0.0)      # Quantity closed by other means
    entry_price = Column(Float)
    order_ids = Column(Text) # Store as JSON string list
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Additional fields for Arts One Two Three strategy
    leverage = Column(Integer, default=1)              # Leverage used for position
    margin_mode = Column(String(20), default='cross')      # 'cross' or 'isolated'
    sl_type = Column(String(50), default='base')           # Type of stop loss: base, swing, sfp, body, atr_trail, structure_trail, chandelier_trail
    sl_price = Column(Float)                           # Stop loss price (for Mode A)
    tp_levels = Column(Text)                         # JSON string of TP levels with prices and percentages (for Mode A)
    entry_strategy = Column(String(50), default='sfp')     # Entry strategy: sfp, volume_spike, etc.