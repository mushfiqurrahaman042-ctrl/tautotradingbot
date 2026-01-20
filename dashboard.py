from fastapi import APIRouter, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import json
from models import Base, Position, ProcessedEvent
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL
from exchange_manager import exchange_manager
from position_manager import PositionManager

router = APIRouter()

# Setup templates
templates = Jinja2Templates(directory="templates")

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
position_manager = PositionManager(engine)

# This route is now handled in main.py
# @router.get("/", response_class=HTMLResponse)
# async def dashboard(request: Request):
#     return templates.TemplateResponse("dashboard.html", {"request": request})

@router.get("/api/positions")
async def get_positions():
    """Fetch all positions from exchange APIs for real-time dashboard display"""
    import os
    positions_data = []
    
    # Get all account IDs from environment
    account_ids = []
    for key in os.environ:
        if key.endswith('_EXCHANGE'):
            account_id = key.replace('_EXCHANGE', '')
            if os.getenv(f"{account_id}_ENABLED", "true").lower() == "true":
                account_ids.append(account_id)
    
    # Fetch positions from each active exchange
    for account_id in account_ids:
        try:
            # Get exchange positions
            exchange_positions = exchange_manager.get_all_positions(account_id)
            
            for position in exchange_positions:
                position_amt = float(position.get('positionAmt', 0))
                if abs(position_amt) > 0.000001:  # Only show non-zero positions (using small epsilon for floating point comparison)
                    symbol = position.get('symbol', '')
                    entry_price = float(position.get('entryPrice', 0))
                    unrealized_pnl = float(position.get('unRealizedProfit', 0))
                    liquidation_price = float(position.get('liquidationPrice', 0))
                    
                    # Determine side
                    side = 'buy' if position_amt > 0 else 'sell'
                    abs_qty = abs(position_amt)
                    
                    # Get current price
                    try:
                        current_price = exchange_manager.get_last_price(account_id, symbol)
                    except:
                        current_price = None
                    
                    # Calculate PnL percentage
                    pnl_pct = 0
                    if entry_price and current_price and entry_price != 0:
                        pnl_raw = (current_price - entry_price) * (1 if side == 'buy' else -1)
                        pnl_pct = (pnl_raw / entry_price) * 100
                    
                    positions_data.append({
                        "id": f"{account_id}_{symbol}_exchange",
                        "account_id": account_id,
                        "symbol": symbol,
                        "strategy_id": "exchange_direct",
                        "side": side,
                        "initial_qty": abs_qty,
                        "remaining_qty": abs_qty,
                        "entry_price": entry_price,
                        "current_price": current_price,
                        "pnl_percentage": round(pnl_pct, 2),
                        "unrealized_pnl": unrealized_pnl,
                        "liquidation_price": liquidation_price,
                        "tp_level": 0,
                        "status": "OPEN",
                        "source": "exchange_api",
                        "updated_at": None
                    })
        except Exception as e:
            print(f"Error fetching positions for {account_id}: {e}")
            continue
    
    # Also include positions from database for historical tracking
    db = SessionLocal()
    try:
        db_positions = db.query(Position).all()
        for pos in db_positions:
            # Check if this position is already included from exchange
            existing_pos = next((p for p in positions_data if p['id'] == pos.id), None)
            if not existing_pos:
                # Get current price from exchange
                try:
                    current_price = exchange_manager.get_last_price(pos.account_id, pos.symbol)
                except:
                    current_price = None
                
                # Calculate PnL percentage
                pnl_pct = 0
                if pos.entry_price and current_price:
                    pnl_raw = (current_price - pos.entry_price) * (1 if pos.side == 'buy' else -1)
                    pnl_pct = (pnl_raw / pos.entry_price) * 100
                
                positions_data.append({
                    "id": pos.id,
                    "account_id": pos.account_id,
                    "symbol": pos.symbol,
                    "strategy_id": pos.strategy_id,
                    "side": pos.side,
                    "initial_qty": pos.initial_qty,
                    "remaining_qty": pos.remaining_qty,
                    "entry_price": pos.entry_price,
                    "current_price": current_price,
                    "pnl_percentage": round(pnl_pct, 2),
                    "tp_level": pos.tp_level,
                    "status": pos.status,
                    "closed_qty_tp1": pos.closed_qty_tp1,
                    "closed_qty_tp2": pos.closed_qty_tp2,
                    "closed_qty_tp3": pos.closed_qty_tp3,
                    "closed_qty_tp4": pos.closed_qty_tp4,
                    "closed_qty_tp5": pos.closed_qty_tp5,
                    "sl_closed_qty": pos.sl_closed_qty,
                    "timeguard_closed_qty": pos.timeguard_closed_qty,
                    "maxbars_closed_qty": pos.maxbars_closed_qty,
                    "swingtp_closed_qty": pos.swingtp_closed_qty,
                    "dyn_tp_closed_qty": pos.dyn_tp_closed_qty,
                    "other_closed_qty": pos.other_closed_qty,
                    "source": "database",
                    "updated_at": pos.updated_at.isoformat() if pos.updated_at else None
                })
    finally:
        db.close()
    
    return positions_data

@router.get("/api/events")
async def get_events():
    db = SessionLocal()
    try:
        events = db.query(ProcessedEvent).order_by(ProcessedEvent.timestamp.desc()).limit(50).all()
        events_data = []
        for event in events:
            events_data.append({
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat()
            })
        return events_data
    finally:
        db.close()

@router.get("/api/accounts")
async def get_accounts():
    # Get account balances from exchanges
    accounts_data = []
    
    # Get all account IDs from the environment
    import os
    for key in os.environ:
        if key.endswith('_EXCHANGE'):
            account_id = key.replace('_EXCHANGE', '')
            exchange_name = os.getenv(key)
            
            # Get balance from exchange
            try:
                balance_info = exchange_manager.get_account_balance(account_id)
                accounts_data.append({
                    "account_id": account_id,
                    "exchange": exchange_name,
                    "total_balance": balance_info.get('totalBalance'),
                    "available_balance": balance_info.get('availableBalance'),
                    "asset": balance_info.get('asset'),
                    "connected": True
                })
            except Exception as e:
                accounts_data.append({
                    "account_id": account_id,
                    "exchange": exchange_name,
                    "total_balance": 0,
                    "available_balance": 0,
                    "asset": "USDT",
                    "connected": False,
                    "error": str(e)
                })
    
    return accounts_data

@router.get("/api/symbols")
async def get_symbols():
    # Get available symbols from exchanges
    symbols_data = {}
    
    import os
    for key in os.environ:
        if key.endswith('_EXCHANGE'):
            account_id = key.replace('_EXCHANGE', '')
            
            try:
                symbols = exchange_manager.get_available_symbols(account_id)
                symbols_data[account_id] = symbols[:20]  # Limit to first 20 symbols
            except Exception as e:
                symbols_data[account_id] = []
    
    return symbols_data

@router.post("/api/sync_positions")
async def sync_positions():
    """Manually trigger position synchronization with exchange"""
    from sync_positions import sync_positions_with_exchange
    try:
        sync_positions_with_exchange()
        return {"status": "success", "message": "Position synchronization completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)