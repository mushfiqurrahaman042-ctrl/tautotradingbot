"""
Position Synchronization Script
This script synchronizes the bot's database positions with the actual positions on the exchange.
It checks for positions that exist in the database but are closed on the exchange, and updates
the database status accordingly.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Position
from config import DATABASE_URL
from exchange_manager import exchange_manager
import json
import time
from datetime import datetime

def sync_positions_with_exchange():
    """
    Synchronize positions between database and exchange
    Updates database positions that are closed on the exchange but still marked as OPEN in the database
    """
    print("🔄 Starting position synchronization...")
    
    # Create database session
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Get all OPEN positions from the database
        db_positions = db.query(Position).filter(Position.status == 'OPEN').all()
        
        if not db_positions:
            print("✅ No open positions in database to synchronize")
            return
        
        print(f"🔍 Found {len(db_positions)} open positions in database to check...")
        
        synced_count = 0
        
        for pos in db_positions:
            print(f"Checking position: {pos.id}")
            
            # Extract account_id, symbol, and strategy_id from the position ID
            # Format: {account_id}_{symbol}_{strategy_id}
            # Account ID can have underscores (e.g., ACC_A), so we need to find the right split point
            pos_id_parts = pos.id.split('_')
            
            # The pattern is: account_id (could be ACC_A, ACC_B, etc.), symbol, strategy_id
            # So we need to find where account ends and symbol starts
            # Try different split points
            account_id = None
            symbol = None
            strategy_id = None
            
            for i in range(1, len(pos_id_parts)):
                potential_account = '_'.join(pos_id_parts[:i])
                potential_symbol = pos_id_parts[i]
                potential_strategy = '_'.join(pos_id_parts[i+1:])
                
                # Check if this account exists in exchange manager
                try:
                    exchange_manager.get_exchange_config(potential_account)
                    # If no exception, this is a valid account
                    account_id = potential_account
                    symbol = potential_symbol
                    strategy_id = potential_strategy
                    break
                except:
                    continue  # Try next split point
            
            if account_id and symbol and strategy_id:
                
                try:
                    # Get current position info from exchange
                    exchange_pos_info = exchange_manager.get_position_info(account_id, symbol)
                    
                    if exchange_pos_info is None:
                        print(f"   📉 Position {pos.id} not found on exchange, marking as closed...")
                        
                        # Update the database position to CLOSED
                        pos.status = 'CLOSED'
                        pos.remaining_qty = 0.0
                        pos.updated_at = datetime.utcnow()
                        
                        # Update other closed quantities if not already set
                        total_closed = (pos.closed_qty_tp1 + pos.closed_qty_tp2 + pos.closed_qty_tp3 + 
                                      pos.closed_qty_tp4 + pos.closed_qty_tp5 + pos.sl_closed_qty + 
                                      pos.timeguard_closed_qty + pos.maxbars_closed_qty + 
                                      pos.swingtp_closed_qty + pos.dyn_tp_closed_qty + pos.other_closed_qty)
                        
                        # If no specific close reason is recorded, mark as other closed
                        if total_closed < pos.initial_qty:
                            pos.other_closed_qty += (pos.initial_qty - total_closed)
                        
                        synced_count += 1
                        print(f"   ✅ Updated position {pos.id} to CLOSED in database")
                        continue
                    
                    # Check if there's an actual position on the exchange
                    # For both Binance and Bybit, a position amount/size of 0 means no position
                    position_amount_raw = exchange_pos_info.get('positionAmt') or exchange_pos_info.get('size', 0)
                    
                    # Handle potential empty strings or None values
                    try:
                        position_amount = float(position_amount_raw) if position_amount_raw != '' and position_amount_raw is not None else 0.0
                    except (ValueError, TypeError):
                        position_amount = 0.0
                    
                    if abs(position_amount) < 0.000001:  # Essentially zero position
                        print(f"   📉 Position {pos.id} is closed on exchange but still OPEN in database. Updating...")
                        
                        # Update the database position to CLOSED
                        pos.status = 'CLOSED'
                        pos.remaining_qty = 0.0
                        pos.updated_at = datetime.utcnow()
                        
                        # Update other closed quantities if not already set
                        total_closed = (pos.closed_qty_tp1 + pos.closed_qty_tp2 + pos.closed_qty_tp3 + 
                                      pos.closed_qty_tp4 + pos.closed_qty_tp5 + pos.sl_closed_qty + 
                                      pos.timeguard_closed_qty + pos.maxbars_closed_qty + 
                                      pos.swingtp_closed_qty + pos.dyn_tp_closed_qty + pos.other_closed_qty)
                        
                        # If no specific close reason is recorded, mark as other closed
                        if total_closed < pos.initial_qty:
                            pos.other_closed_qty += (pos.initial_qty - total_closed)
                        
                        synced_count += 1
                        print(f"   ✅ Updated position {pos.id} to CLOSED in database")
                    else:
                        print(f"   ✅ Position {pos.id} is correctly OPEN on both exchange and database")
                
                except Exception as e:
                    print(f"   ❌ Error checking position {pos.id} on exchange: {str(e)}")
                    continue
            else:
                print(f"   ❌ Invalid position ID format: {pos.id}")
                continue
        
        # Commit all changes to the database
        db.commit()
        print(f"\n✅ Position synchronization completed!")
        print(f"📊 Updated {synced_count} positions from OPEN to CLOSED")
        
    except Exception as e:
        print(f"❌ Error during position synchronization: {str(e)}")
        db.rollback()
    finally:
        db.close()

def sync_and_display_status():
    """Sync positions and display current status"""
    print("=" * 60)
    print("POSITION SYNCHRONIZATION AND STATUS CHECK")
    print("=" * 60)
    
    # First, sync the positions
    sync_positions_with_exchange()
    
    # Then show the current status
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        all_positions = db.query(Position).all()
        open_positions = [pos for pos in all_positions if pos.status == 'OPEN']
        closed_positions = [pos for pos in all_positions if pos.status == 'CLOSED']
        
        print(f"\n📈 Total positions in database: {len(all_positions)}")
        print(f"🟢 Open positions: {len(open_positions)}")
        print(f"🔴 Closed positions: {len(closed_positions)}")
        
        if open_positions:
            print("\nOpen positions:")
            for pos in open_positions:
                print(f"  • {pos.id} - {pos.symbol} ({pos.side}) - Qty: {pos.remaining_qty}")
        
        if closed_positions:
            print("\nClosed positions:")
            for pos in closed_positions:
                print(f"  • {pos.id} - {pos.symbol} ({pos.side}) - Status: {pos.status}")
                
    except Exception as e:
        print(f"❌ Error displaying status: {str(e)}")
    finally:
        db.close()
    
    print("=" * 60)

if __name__ == "__main__":
    sync_and_display_status()