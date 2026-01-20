from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine
from models import Position, ProcessedEvent
from config import PARTIAL_TP_PERCENTAGE
import json
import time
import logging

def execute_db_operation_with_retry(func, max_retries=7, delay=0.1):
    """Execute a database operation with retry logic for database locking errors."""
    for attempt in range(max_retries):
        try:
            return func()
        except OperationalError as e:
            error_msg = str(e).lower()
            # Check for various database locking/concurrency issues
            if ("database is locked" in error_msg or 
                "database locked" in error_msg or 
                "lock wait timeout" in error_msg or 
                "deadlock" in error_msg or
                "too many connections" in error_msg) and attempt < max_retries - 1:
                logging.warning(f"Database issue detected in position manager, retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                delay *= 2.5  # Exponential backoff
            else:
                raise

class PositionManager:
    def __init__(self, engine):
        self.engine = engine
        self.SessionLocal = sessionmaker(bind=engine)
    
    def get_position(self, account_id, symbol, strategy_id):
        """Retrieve an open position for a given account, symbol, and strategy."""
        def execute_get_position():
            db = self.SessionLocal()
            try:
                pos_id = f"{account_id}_{symbol}_{strategy_id}"
                pos = db.query(Position).filter(
                    Position.id == pos_id,
                    Position.status == 'OPEN'
                ).first()
                return pos
            finally:
                db.close()
        
        return execute_db_operation_with_retry(execute_get_position)
    
    def calculate_tp_exit_quantity(self, position, tp_level=None):
        """Calculate quantity for partial take profit exit based on level."""
        # Default to PARTIAL_TP_PERCENTAGE from config
        if tp_level is None:
            return position.initial_qty * PARTIAL_TP_PERCENTAGE
        
        # Different TP levels might have different percentages
        # This can be configured based on strategy requirements
        if tp_level == 1:
            return position.initial_qty * 0.2  # 20% for TP1
        elif tp_level == 2:
            return position.initial_qty * 0.2  # 20% for TP2
        elif tp_level == 3:
            return position.initial_qty * 0.2  # 20% for TP3
        elif tp_level == 4:
            return position.initial_qty * 0.2  # 20% for TP4
        elif tp_level == 5:
            return position.initial_qty * 0.2  # 20% for TP5
        else:
            return position.initial_qty * PARTIAL_TP_PERCENTAGE
    
    def calculate_sl_exit_quantity(self, position):
        """Calculate quantity for stop loss exit (full close)."""
        return position.remaining_qty
    
    def update_position_after_partial_exit(self, position, closed_qty, order_id, tp_level=None):
        """Update position after partial exit (e.g., TP1, TP2, etc.)."""
        def execute_update_partial_exit():
            db = self.SessionLocal()
            try:
                # Get fresh position instance to avoid session issues
                pos_id = position.id
                position = db.query(Position).filter(Position.id == pos_id).first()
                if position is None:
                    raise ValueError(f"Position {pos_id} not found")
                    
                position.remaining_qty -= closed_qty
                
                # Track which TP level was hit
                if tp_level == 1:
                    position.closed_qty_tp1 += closed_qty
                elif tp_level == 2:
                    position.closed_qty_tp2 += closed_qty
                elif tp_level == 3:
                    position.closed_qty_tp3 += closed_qty
                elif tp_level == 4:
                    position.closed_qty_tp4 += closed_qty
                elif tp_level == 5:
                    position.closed_qty_tp5 += closed_qty
                
                # Update TP level if applicable
                if tp_level is not None:
                    position.tp_level = max(position.tp_level, tp_level)
                else:
                    position.tp_level += 1
                
                # Update order IDs list
                order_ids = json.loads(position.order_ids or '[]')
                order_ids.append(order_id)
                position.order_ids = json.dumps(order_ids)
                
                # If remaining quantity is 0 or less, close the position
                if position.remaining_qty <= 0:
                    position.status = 'CLOSED'
                
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        
        execute_db_operation_with_retry(execute_update_partial_exit)
    
    def update_position_after_stop_loss(self, position, closed_qty, order_id, sl_type="base"):
        """Update position after stop loss exit with specific SL type."""
        def execute_update_stop_loss():
            db = self.SessionLocal()
            try:
                # Get fresh position instance to avoid session issues
                pos_id = position.id
                position = db.query(Position).filter(Position.id == pos_id).first()
                if position is None:
                    raise ValueError(f"Position {pos_id} not found")
                    
                position.remaining_qty -= closed_qty
                position.sl_closed_qty += closed_qty
                
                # Set stop loss type for tracking purposes
                if sl_type == "base":
                    position.sl_type = "base"
                elif sl_type == "swing":
                    position.sl_type = "swing"
                elif sl_type == "sfp":
                    position.sl_type = "sfp"
                elif sl_type == "body":
                    position.sl_type = "body"
                elif sl_type == "atr_trail":
                    position.sl_type = "atr_trail"
                elif sl_type == "structure_trail":
                    position.sl_type = "structure_trail"
                elif sl_type == "chandelier_trail":
                    position.sl_type = "chandelier_trail"
                
                # Update order IDs list
                order_ids = json.loads(position.order_ids or '[]')
                order_ids.append(order_id)
                position.order_ids = json.dumps(order_ids)
                
                # If remaining quantity is 0 or less, close the position
                if position.remaining_qty <= 0:
                    position.status = 'CLOSED'
                
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        
        execute_db_operation_with_retry(execute_update_stop_loss)
    
    def update_position_after_other_exit(self, position, closed_qty, order_id, exit_type="other"):
        """Update position after other exit types (TimeGuard, MaxBars, SwingTP, DynTP, etc.)."""
        def execute_update_other_exit():
            db = self.SessionLocal()
            try:
                # Get fresh position instance to avoid session issues
                pos_id = position.id
                position = db.query(Position).filter(Position.id == pos_id).first()
                if position is None:
                    raise ValueError(f"Position {pos_id} not found")
                    
                position.remaining_qty -= closed_qty
                
                if exit_type == "TimeGuard":
                    position.timeguard_closed_qty += closed_qty
                elif exit_type == "MaxBars":
                    position.maxbars_closed_qty += closed_qty
                elif exit_type == "SwingTP":
                    position.swingtp_closed_qty += closed_qty
                elif exit_type == "DynTP":
                    position.dyn_tp_closed_qty += closed_qty
                else:
                    position.other_closed_qty += closed_qty
                
                # Update order IDs list
                order_ids = json.loads(position.order_ids or '[]')
                order_ids.append(order_id)
                position.order_ids = json.dumps(order_ids)
                
                # If remaining quantity is 0 or less, close the position
                if position.remaining_qty <= 0:
                    position.status = 'CLOSED'
                
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        
        execute_db_operation_with_retry(execute_update_other_exit)
    
    def close_position(self, position, order_id):
        """Close position completely (set remaining_qty to 0 and status to CLOSED)."""
        def execute_close_position():
            db = self.SessionLocal()
            try:
                # Get fresh position instance to avoid session issues
                pos_id = position.id
                position = db.query(Position).filter(Position.id == pos_id).first()
                if position is None:
                    raise ValueError(f"Position {pos_id} not found")
                    
                position.remaining_qty = 0
                position.status = 'CLOSED'
                
                # Update order IDs list
                order_ids = json.loads(position.order_ids or '[]')
                order_ids.append(order_id)
                position.order_ids = json.dumps(order_ids)
                
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        
        execute_db_operation_with_retry(execute_close_position)
    
    def create_new_position(self, account_id, symbol, strategy_id, side, qty, price, order_id, leverage=None, margin_mode=None, tp_levels=None, sl_price=None):
        """Create a new position record with additional parameters for Arts One Two Three strategy."""
        def execute_create_position():
            db = self.SessionLocal()
            try:
                pos_id = f"{account_id}_{symbol}_{strategy_id}"
                new_pos = Position(
                    id=pos_id,
                    account_id=account_id,
                    symbol=symbol,
                    strategy_id=strategy_id,
                    side=side,
                    initial_qty=qty,
                    remaining_qty=qty,
                    entry_price=price,
                    order_ids=json.dumps([order_id]),
                    leverage=leverage,
                    margin_mode=margin_mode,
                    tp_levels=json.dumps(tp_levels) if tp_levels else None,
                    sl_price=sl_price
                )
                db.add(new_pos)
                db.commit()
                return new_pos
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        
        return execute_db_operation_with_retry(execute_create_position)
    
    def get_active_positions_count(self, account_id=None):
        """Get count of active (OPEN) positions."""
        def execute_get_active_positions_count():
            db = self.SessionLocal()
            try:
                query = db.query(Position).filter(Position.status == 'OPEN')
                if account_id:
                    query = query.filter(Position.account_id == account_id)
                return query.count()
            finally:
                db.close()
        
        return execute_db_operation_with_retry(execute_get_active_positions_count)
    
    def update_tp_level(self, position, level):
        """Update the current TP level for the position."""
        position.tp_level = max(position.tp_level, level)
    
    def get_position_summary(self, account_id=None, symbol=None, strategy_id=None):
        """Get a comprehensive summary of positions with detailed metrics."""
        def execute_get_position_summary():
            db = self.SessionLocal()
            try:
                query = db.query(Position)
                
                # Apply filters if provided
                if account_id:
                    query = query.filter(Position.account_id == account_id)
                if symbol:
                    query = query.filter(Position.symbol == symbol)
                if strategy_id:
                    query = query.filter(Position.strategy_id == strategy_id)
                
                positions = query.all()
                
                summary = []
                for pos in positions:
                    # Calculate PnL percentage
                    if pos.entry_price:
                        current_price = self._get_current_price(pos.symbol)  # You'd need to implement this
                        pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100 if current_price else 0
                        if pos.side == 'sell':  # Short position
                            pnl_pct = -pnl_pct
                    else:
                        pnl_pct = 0
                    
                    pos_summary = {
                        'id': pos.id,
                        'account_id': pos.account_id,
                        'symbol': pos.symbol,
                        'strategy_id': pos.strategy_id,
                        'side': pos.side,
                        'initial_qty': pos.initial_qty,
                        'remaining_qty': pos.remaining_qty,
                        'entry_price': pos.entry_price,
                        'pnl_percentage': pnl_pct,
                        'tp_level': pos.tp_level,
                        'closed_qty_tp1': pos.closed_qty_tp1,
                        'closed_qty_tp2': pos.closed_qty_tp2,
                        'closed_qty_tp3': pos.closed_qty_tp3,
                        'closed_qty_tp4': pos.closed_qty_tp4,
                        'closed_qty_tp5': pos.closed_qty_tp5,
                        'sl_closed_qty': pos.sl_closed_qty,
                        'timeguard_closed_qty': pos.timeguard_closed_qty,
                        'maxbars_closed_qty': pos.maxbars_closed_qty,
                        'swingtp_closed_qty': pos.swingtp_closed_qty,
                        'dyn_tp_closed_qty': pos.dyn_tp_closed_qty,
                        'other_closed_qty': pos.other_closed_qty,
                        'status': pos.status,
                        'updated_at': pos.updated_at,
                        'leverage': pos.leverage,
                        'margin_mode': pos.margin_mode,
                        'sl_type': pos.sl_type
                    }
                    summary.append(pos_summary)
                
                return summary
            finally:
                db.close()
        
        return execute_db_operation_with_retry(execute_get_position_summary)
    
    def _get_current_price(self, symbol):
        """Helper method to get current price (would integrate with exchange manager)."""
        # This would need to be implemented to fetch real-time prices
        # from the exchange manager for PnL calculations
        return None
    
    def calculate_remaining_tp_percent(self, position):
        """Calculate the percentage of position that still needs to be closed via TP."""
        total_closed = (position.closed_qty_tp1 + position.closed_qty_tp2 + 
                       position.closed_qty_tp3 + position.closed_qty_tp4 + 
                       position.closed_qty_tp5)
        remaining_for_tp = position.initial_qty - total_closed - position.sl_closed_qty - position.other_closed_qty
        return (remaining_for_tp / position.initial_qty) * 100 if position.initial_qty > 0 else 0