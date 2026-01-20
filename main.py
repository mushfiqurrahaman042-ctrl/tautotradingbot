from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError
from sqlalchemy import event
from models import Base, Position, ProcessedEvent
from exchange_handler import ExchangeHandler
from position_manager import PositionManager
from config import DATABASE_URL, WEBHOOK_PASSPHRASE
import os
from dotenv import load_dotenv
import json
from dashboard import router as dashboard_router
import time
import logging
import datetime

# Import the new ExchangeManager, Price Monitor, Account Config and Symbol Manager
from exchange_manager import exchange_manager
from price_monitor import init_price_monitor
from account_config import account_config_manager
from symbol_manager import symbol_manager

load_dotenv()

# Enhanced logging setup
logging.basicConfig(
    level=logging.DEBUG if os.getenv("LOG_LEVEL", "info").lower() == "debug" else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('trading_bot.log')
    ]
)
logger = logging.getLogger(__name__)

def execute_with_retry(func, max_retries=7, delay=0.1):
    """Execute a function with retry logic for database locking errors."""
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
                logging.warning(f"Database issue detected, retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                delay *= 2.5  # Exponential backoff
            else:
                raise

def get_sqlite_engine():
    """Create database engine with appropriate settings based on database type."""
    # Determine if using PostgreSQL, MySQL, or SQLite
    if DATABASE_URL.startswith("postgresql://"):
        # PostgreSQL configuration
        engine = create_engine(
            DATABASE_URL,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=30,
            echo=False
        )
    elif DATABASE_URL.startswith("mysql://") or DATABASE_URL.startswith("mysql+pymysql://"):
        # MySQL configuration
        engine = create_engine(
            DATABASE_URL,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=30,
            echo=False,
            connect_args={
                "connect_timeout": 30,
                "charset": "utf8mb4"
            }
        )
    else:
        # SQLite configuration with WAL mode
        engine = create_engine(
            DATABASE_URL,
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=30,
            echo=False,
            connect_args={
                "timeout": 30,
                "check_same_thread": False,
                "uri": True
            }
        )
        
        # Enable WAL mode for better SQLite concurrency
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=10000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.close()
    
    return engine

app = FastAPI()
engine = get_sqlite_engine()
# Create all tables, including the new ProcessedEvent
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(bind=engine)
position_manager = PositionManager(engine)

# Initialize price monitor for Mode A
price_monitor = init_price_monitor(engine, position_manager)

# Include dashboard API routes
app.include_router(dashboard_router, prefix="", tags=["dashboard-api"])

@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    return RedirectResponse(url="/dashboard/")

@app.get("/dashboard/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# Mount static files separately
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/status")
async def get_status():
    """Status endpoint that lists open positions and recent events, grouped by account_profile"""
    def execute_status_logic():
        db = SessionLocal()
        try:
            # Get all open positions
            open_positions = db.query(Position).filter(Position.status == 'OPEN').all()
            
            # Group positions by account
            positions_by_account = {}
            for pos in open_positions:
                account_id = pos.account_id
                if account_id not in positions_by_account:
                    positions_by_account[account_id] = []
                positions_by_account[account_id].append({
                    "id": pos.id,
                    "symbol": pos.symbol,
                    "strategy_id": pos.strategy_id,
                    "side": pos.side,
                    "initial_qty": pos.initial_qty,
                    "remaining_qty": pos.remaining_qty,
                    "status": pos.status,
                    "tp_level": pos.tp_level,
                    "entry_price": pos.entry_price
                })
            
            # Get recent processed events
            recent_events = db.query(ProcessedEvent).order_by(ProcessedEvent.timestamp.desc()).limit(10).all()
            recent_event_list = [{
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat()
            } for event in recent_events]
            
            return {
                "open_positions_by_account": positions_by_account,
                "recent_events": recent_event_list,
                "active_accounts": list(positions_by_account.keys())
            }
        finally:
            db.close()

    return execute_with_retry(execute_status_logic)


@app.post("/webhook")
async def handle_signal(request: Request):
    logger.info("=" * 60)
    logger.info("📥 RECEIVED WEBHOOK REQUEST")
    logger.info("=" * 60)
    
    # Log raw request info
    client_host = request.client.host if request.client else "Unknown"
    logger.info(f"📡 Source IP: {client_host}")
    logger.info(f"🕒 Timestamp: {datetime.datetime.utcnow().isoformat()}")
    
    try:
        data = await request.json()
        logger.debug(f"📄 Raw payload: {json.dumps(data, indent=2)}")
    except Exception as e:
        logger.error(f"❌ Failed to parse JSON payload: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    
    def execute_webhook_logic():
        db = SessionLocal()

        try:
            # --- Validation ---
            logger.info("🔍 STARTING VALIDATION")
            
            # Check passphrase
            received_passphrase = data.get("passphrase")
            logger.info(f"🔑 Expected passphrase: {WEBHOOK_PASSPHRASE}")
            logger.info(f"🔑 Received passphrase: {received_passphrase}")
            
            if received_passphrase != WEBHOOK_PASSPHRASE:
                logger.error(f"❌ PASSPHRASE MISMATCH - Expected: {WEBHOOK_PASSPHRASE}, Received: {received_passphrase}")
                raise HTTPException(status_code=401, detail="Unauthorized - Invalid passphrase")
            logger.info("✅ Passphrase validation passed")

            # Check event_id
            event_id = data.get("event_id")
            logger.info(f"🆔 Event ID: {event_id}")
            if not event_id:
                logger.error("❌ Missing event_id in payload")
                raise HTTPException(status_code=400, detail="Missing event_id")
            logger.info("✅ Event ID validation passed")

            # --- Idempotency Check ---
            if db.query(ProcessedEvent).filter(ProcessedEvent.event_id == event_id).first():
                raise HTTPException(status_code=409, detail="Event already processed")

            # --- Extract Payload ---
            logger.info("📦 EXTRACTING PAYLOAD DATA")
            
            event_type = data.get("event_type")
            symbol = data.get("symbol")
            strategy_id = data.get("strategy_id")
            
            logger.info(f"📈 Event Type: {event_type}")
            logger.info(f"💱 Symbol: {symbol}")
            logger.info(f"🎯 Strategy ID: {strategy_id}")
            
            # Validate required fields
            if not event_type:
                logger.error("❌ Missing event_type in payload")
                raise HTTPException(status_code=400, detail="Missing event_type")
            if not symbol:
                logger.error("❌ Missing symbol in payload")
                raise HTTPException(status_code=400, detail="Missing symbol")
            if not strategy_id:
                logger.error("❌ Missing strategy_id in payload")
                raise HTTPException(status_code=400, detail="Missing strategy_id")
            
            logger.info("✅ Required payload fields validation passed")
            
            # Use account configuration manager to determine which accounts should receive this signal
            accounts = data.get("account_profile", []) # If specified in payload, use those accounts
            if not accounts:
                # Otherwise, get accounts based on routing rules
                accounts = account_config_manager.get_accounts_for_strategy(strategy_id, symbol)
            
            # Extract additional fields for Arts One Two Three strategy
            side = data.get("side")  # 'long' or 'short'
            quantity = data.get("quantity")  # Will be obtained from account config if not provided
            leverage = data.get("leverage")  # Will be obtained from account config if not provided
            order_type = data.get("order_type", "MARKET")  # Order type (market/limit)
            margin_mode = data.get("margin_mode")  # Will be obtained from account config if not provided
            
            # Mode A specific fields (TP levels provided at entry)
            tp_levels = data.get("tp_levels", {})  # {"TP1": {"price": 50000, "percent": 0.2}, "TP2": {"price": 52000, "percent": 0.2}, ...}
            sl_price = data.get("sl_price")  # Stop loss price for Mode A
            sl_type = data.get("sl_type", "base")  # Type of stop loss (base, swing, sfp, body, atr_trail, etc.)
            
            # Mode B specific fields (separate TP/SL events)
            # These will be handled when separate events arrive
            
            # Entry strategy (for Arts One Two Three)
            entry_strategy = data.get("entry_strategy", "sfp")  # Default to SFP-based entry

            # Mark event as processed inside a transaction
            db.add(ProcessedEvent(event_id=event_id))

            # Process each account with better error isolation
            logger.info(f"👥 Processing accounts: {accounts}")
            processing_results = {}
            all_successful = True
            
            for acc_id in accounts:
                logger.info(f"⚙️ Processing account: {acc_id}")
                # Using PositionManager to handle position operations
                try:
                    # Get account-specific configuration
                    acc_config = account_config_manager.get_account_config(acc_id)
                    if not acc_config or not acc_config.get('enabled', False):
                        print(f"⚠️ Account {acc_id} is disabled, skipping")
                        continue
                    
                    # Check if symbol is allowed for this account
                    if not account_config_manager.is_symbol_allowed(acc_id, symbol):
                        print(f"⚠️ Symbol {symbol} not allowed for account {acc_id}, skipping")
                        continue
                    
                    # Check if symbol is allowed for this strategy
                    if not symbol_manager.is_symbol_allowed_for_strategy(symbol, strategy_id, acc_id):
                        print(f"⚠️ Symbol {symbol} not allowed for strategy {strategy_id} on account {acc_id}, skipping")
                        continue
                    
                    # Use account-specific defaults if not provided in webhook
                    if quantity is None:
                        quantity = acc_config.get('position_size', 0.001)
                    if leverage is None:
                        leverage = acc_config.get('leverage', 1)
                    if margin_mode is None:
                        margin_mode = acc_config.get('margin_mode', 'cross')
                                        
                    # Ensure quantity is positive and not None
                    logger.info(f"📊 Quantity before conversion: {quantity} (type: {type(quantity)})")
                                        
                    # Convert to float safely
                    try:
                        quantity = float(quantity)
                    except (TypeError, ValueError):
                        logger.error(f"❌ Invalid quantity type/value: {quantity}. Setting to default 0.001")
                        quantity = 0.001
                                        
                    # Ensure quantity is positive
                    quantity = abs(quantity)
                    if quantity <= 0:
                        logger.error(f"❌ Invalid quantity after conversion: {quantity}. Setting to default 0.001")
                        quantity = 0.001
                                        
                    logger.info(f"📊 Final quantity: {quantity}")
                    
                    # Get position within the same DB session
                    pos = db.query(Position).filter(
                        Position.id == f"{acc_id}_{symbol}_{strategy_id}",
                        Position.status == 'OPEN'
                    ).first()

                    # 1. ENTRY LOGIC - Arts One Two Three Strategy
                    if event_type in ["LONG_ENTRY", "SHORT_ENTRY"]:
                        # No-pyramiding: ignore new entry if position already open for this symbol/account
                        if pos:
                            print(f"⚠️ Position already open for {acc_id}_{symbol}_{strategy_id}, ignoring new entry request")
                            processing_results[acc_id] = {"status": "warning", "action": "entry", "message": "Position already open, pyramiding blocked"}
                            continue
                        elif not pos:
                            # Check if a position exists in the database with a different status
                            existing_pos = db.query(Position).filter(
                                Position.id == f"{acc_id}_{symbol}_{strategy_id}"
                            ).first()
                            if existing_pos and existing_pos.status != 'OPEN':
                                try:
                                    # Update the existing closed position to OPEN instead of creating a new one
                                    # Determine entry side based on event_type or side field
                                    order_side = "buy" if "LONG" in event_type or side == "long" else "sell"
                                    
                                    print(f"DEBUG: Attempting {order_side} on {acc_id} for {symbol}")
                                    
                                    # Execute order using ExchangeManager
                                    order_params = {
                                        "account_id": acc_id,
                                        "symbol": symbol,
                                        "side": order_side,
                                        "qty": quantity,
                                        "order_type": order_type,
                                    }
                                    
                                    # Add optional parameters if they exist
                                    if leverage:
                                        order_params["leverage"] = leverage
                                    if "price" in data and data["price"]:
                                        order_params["price"] = data["price"]
                                    
                                    order = exchange_manager.execute_order(**order_params)
                                    
                                    # --- Price Fallback Logic ---
                                    price = order.get('price') or (order.get('result', {}).get('orderPrice') if 'result' in order else None)
                                    if not price:
                                        try:
                                            # Fallback to last price if order price not available
                                            print(f"ℹ️ Order price not available, falling back to last ticker price for {symbol} on {acc_id}.")
                                            price = exchange_manager.get_last_price(acc_id, symbol)
                                        except Exception as e:
                                            print(f"⚠️ Could not fetch price for {symbol} on {acc_id}: {e}")

                                    if not price:
                                        raise Exception("Could not determine entry price.")
                                    # --- End Price Fallback ---
                                    
                                    # Update the existing position with new values
                                    existing_pos.status = 'OPEN'
                                    existing_pos.side = order_side
                                    existing_pos.initial_qty = quantity
                                    existing_pos.remaining_qty = quantity
                                    existing_pos.entry_price = price
                                    existing_pos.updated_at = datetime.datetime.utcnow()
                                    
                                    # Update other fields as needed
                                    existing_pos.leverage = leverage
                                    existing_pos.margin_mode = margin_mode
                                    existing_pos.tp_levels = json.dumps(tp_levels) if tp_levels else None
                                    existing_pos.sl_price = sl_price
                                    existing_pos.entry_strategy = entry_strategy
                                    
                                    print(f"DEBUG: Reopened existing position for {acc_id}_{symbol}_{strategy_id}")
                                    processing_results[acc_id] = {"status": "success", "action": "entry", "order_id": order.get('orderId', order.get('result', {}).get('orderId'))}
                                    
                                    # Add to price monitor if using Mode A (TP levels provided at entry)
                                    if tp_levels:
                                        price_monitor.add_position_to_monitor(acc_id, symbol, existing_pos)
                                        print(f"DEBUG: Added {symbol} position to price monitor for Mode A")
                                except Exception as e:
                                    print(f"❌ Exchange Error on {acc_id}: {str(e)}")
                                    processing_results[acc_id] = {"status": "error", "action": "entry", "error": str(e)}
                                    all_successful = False
                                    # Continue processing other accounts
                            else:
                                try:
                                    # Determine entry side based on event_type or side field
                                    order_side = "buy" if "LONG" in event_type or side == "long" else "sell"
                                    
                                    print(f"DEBUG: Attempting {order_side} on {acc_id} for {symbol}")
                                    
                                    # Execute order using ExchangeManager
                                    order_params = {
                                        "account_id": acc_id,
                                        "symbol": symbol,
                                        "side": order_side,
                                        "qty": quantity,
                                        "order_type": order_type,
                                    }
                                    
                                    # Add optional parameters if they exist
                                    if leverage:
                                        order_params["leverage"] = leverage
                                    if "price" in data and data["price"]:
                                        order_params["price"] = data["price"]
                                    
                                    order = exchange_manager.execute_order(**order_params)
                                    
                                    # --- Price Fallback Logic ---
                                    price = order.get('price') or (order.get('result', {}).get('orderPrice') if 'result' in order else None)
                                    if not price:
                                        try:
                                            # Fallback to last price if order price not available
                                            print(f"ℹ️ Order price not available, falling back to last ticker price for {symbol} on {acc_id}.")
                                            price = exchange_manager.get_last_price(acc_id, symbol)
                                        except Exception as e:
                                            print(f"⚠️ Could not fetch price for {symbol} on {acc_id}: {e}")

                                    if not price:
                                        raise Exception("Could not determine entry price.")
                                    # --- End Price Fallback ---

                                    # Create new position using PositionManager
                                    new_position = position_manager.create_new_position(
                                        account_id=acc_id,
                                        symbol=symbol,
                                        strategy_id=strategy_id,
                                        side=order_side,
                                        qty=quantity,
                                        price=price, # Use the determined price
                                        order_id=order.get('orderId', order.get('result', {}).get('orderId')),
                                        leverage=leverage,
                                        margin_mode=margin_mode,
                                        tp_levels=tp_levels,
                                        sl_price=sl_price
                                    )
                                    print(f"DEBUG: Successfully opened {order_side} position. Order ID: {order.get('orderId', order.get('result', {}).get('orderId'))}")
                                    processing_results[acc_id] = {"status": "success", "action": "entry", "order_id": order.get('orderId', order.get('result', {}).get('orderId'))}
                                    
                                    # Add to price monitor if using Mode A (TP levels provided at entry)
                                    if tp_levels:
                                        price_monitor.add_position_to_monitor(acc_id, symbol, new_position)
                                        print(f"DEBUG: Added {symbol} position to price monitor for Mode A")
                                except Exception as e:
                                    print(f"❌ Exchange Error on {acc_id}: {str(e)}")
                                    processing_results[acc_id] = {"status": "error", "action": "entry", "error": str(e)}
                                    all_successful = False
                                    # Continue processing other accounts

                    # 2. EXIT LOGIC - Arts One Two Three Strategy
                    elif pos:
                        # Determine exit side based on position side
                        exit_side = "sell" if pos.side == "buy" else "buy"
                        
                        # Partial TP - Arts One Two Three TP1-TP4
                        if event_type in ["TP1_HIT", "TP2_HIT", "TP3_HIT", "TP4_HIT"]:
                            try:
                                # Calculate close quantity based on custom percentages from webhook payload or use defaults
                                # Check if custom TP percentages are provided in the webhook data
                                custom_tp_percentages = data.get("tp_percentages", {})
                                
                                if event_type == "TP1_HIT":
                                    tp_percentage = custom_tp_percentages.get("TP1", 0.2)  # Default 20% for TP1 (to cover fees)
                                elif event_type == "TP2_HIT":
                                    tp_percentage = custom_tp_percentages.get("TP2", 0.2)  # Default 20% for TP2
                                elif event_type == "TP3_HIT":
                                    tp_percentage = custom_tp_percentages.get("TP3", 0.2)  # Default 20% for TP3
                                elif event_type == "TP4_HIT":
                                    tp_percentage = custom_tp_percentages.get("TP4", 0.2)  # Default 20% for TP4
                                
                                close_qty = pos.initial_qty * tp_percentage
                                
                                # Ensure close quantity is positive and not greater than remaining quantity
                                close_qty = max(0.000001, min(close_qty, pos.remaining_qty))  # Minimum quantity to avoid zero
                                
                                logger.info(f"📊 Calculating close quantity: initial={pos.initial_qty}, percent={tp_percentage}, close={close_qty}, remaining={pos.remaining_qty}")
                                
                                if close_qty <= 0 or pos.remaining_qty <= 0:
                                    logger.warning(f"⚠️ Cannot close position: close_qty={close_qty}, remaining_qty={pos.remaining_qty}")
                                    processing_results[acc_id] = {"status": "warning", "action": "partial_exit", "message": "Nothing to close"}
                                    continue
                                
                                # Execute partial close order
                                order = exchange_manager.execute_order(
                                    account_id=acc_id,
                                    symbol=symbol,
                                    side=exit_side,
                                    qty=close_qty,
                                    reduce_only=True,
                                    order_type=order_type
                                )
                                
                                # Determine TP level from event type
                                tp_level = int(event_type[2]) if event_type.startswith("TP") and len(event_type) > 2 else None
                                
                                # Update position directly in the same session
                                pos.remaining_qty -= close_qty
                                
                                # Track which TP level was hit
                                if tp_level == 1:
                                    pos.closed_qty_tp1 += close_qty
                                elif tp_level == 2:
                                    pos.closed_qty_tp2 += close_qty
                                elif tp_level == 3:
                                    pos.closed_qty_tp3 += close_qty
                                elif tp_level == 4:
                                    pos.closed_qty_tp4 += close_qty
                                elif tp_level == 5:
                                    pos.closed_qty_tp5 += close_qty
                                
                                # Update TP level if applicable
                                if tp_level is not None:
                                    pos.tp_level = max(pos.tp_level, tp_level)
                                else:
                                    pos.tp_level += 1
                                
                                # Update order IDs list
                                order_ids = json.loads(pos.order_ids or '[]')
                                order_ids.append(order.get('orderId', order.get('result', {}).get('orderId')))
                                pos.order_ids = json.dumps(order_ids)
                                
                                # Ensure entry price is preserved
                                if not pos.entry_price:
                                    # Try to get the entry price from the order if not set
                                    pos.entry_price = order.get('price') or (order.get('result', {}).get('orderPrice') if 'result' in order else None)
                                
                                processing_results[acc_id] = {"status": "success", "action": "partial_exit", "order_id": order.get('orderId', order.get('result', {}).get('orderId')), "tp_level": tp_level}

                            except Exception as e:
                                print(f"❌ Exchange Error on {acc_id}: {str(e)}")
                                processing_results[acc_id] = {"status": "error", "action": "partial_exit", "error": str(e)}
                                all_successful = False
                                # Continue processing other accounts

                        # Full Close - Arts One Two Three various exit types
                        elif event_type in ["STOP", "TP5_HIT", "TIME_GUARD", "MAX_BARS", "SWING_TP", "DYN_TP", "CLOSE"]:
                            # Check if there's anything left to close
                            if pos.remaining_qty <= 0:
                                logger.warning(f"⚠️ No remaining quantity to close for {acc_id}_{symbol}_{strategy_id}, skipping close order")
                                processing_results[acc_id] = {"status": "warning", "action": "exit", "message": "No remaining quantity to close"}
                                continue
                            
                            # Ensure close quantity is positive
                            close_qty = max(0.000001, pos.remaining_qty)  # Minimum quantity to avoid zero
                            logger.info(f"📊 Full close quantity: {close_qty}")
                            
                            try:
                                # Execute full close order
                                order = exchange_manager.execute_order(
                                    account_id=acc_id,
                                    symbol=symbol,
                                    side=exit_side,
                                    qty=close_qty,
                                    reduce_only=True,
                                    order_type=order_type
                                )
                                
                                # Handle different exit types with appropriate tracking
                                if event_type == "STOP":
                                    # Stop loss exit (base SL, swing SL, SFP SL, body SL, ATR trail, structure trail, chandelier trail)
                                    pos.remaining_qty -= pos.remaining_qty  # Close entire remaining quantity
                                    pos.sl_closed_qty += pos.remaining_qty
                                    
                                    # Update order IDs list
                                    order_ids = json.loads(pos.order_ids or '[]')
                                    order_ids.append(order.get('orderId', order.get('result', {}).get('orderId')))
                                    pos.order_ids = json.dumps(order_ids)
                                    
                                    # Ensure entry price is preserved
                                    if not pos.entry_price:
                                        # Try to get the entry price from the order if not set
                                        pos.entry_price = order.get('price') or (order.get('result', {}).get('orderPrice') if 'result' in order else None)
                                    
                                    # Set stop loss type for tracking purposes
                                    pos.sl_type = 'base'  # Default to base, could be extended based on event_type
                                    processing_results[acc_id] = {"status": "success", "action": "stop_loss", "order_id": order.get('orderId', order.get('result', {}).get('orderId'))}
                                elif event_type == "SWING_TP":
                                    # Swing TP close
                                    pos.remaining_qty -= pos.remaining_qty  # Close entire remaining quantity
                                    pos.swingtp_closed_qty += pos.remaining_qty
                                    
                                    # Update order IDs list
                                    order_ids = json.loads(pos.order_ids or '[]')
                                    order_ids.append(order.get('orderId', order.get('result', {}).get('orderId')))
                                    pos.order_ids = json.dumps(order_ids)
                                    
                                    processing_results[acc_id] = {"status": "success", "action": "swing_tp_exit", "order_id": order.get('orderId', order.get('result', {}).get('orderId'))}
                                elif event_type == "DYN_TP":
                                    # Dynamic TP close
                                    pos.remaining_qty -= pos.remaining_qty  # Close entire remaining quantity
                                    pos.dyn_tp_closed_qty += pos.remaining_qty
                                    
                                    # Update order IDs list
                                    order_ids = json.loads(pos.order_ids or '[]')
                                    order_ids.append(order.get('orderId', order.get('result', {}).get('orderId')))
                                    pos.order_ids = json.dumps(order_ids)
                                    
                                    processing_results[acc_id] = {"status": "success", "action": "dyn_tp_exit", "order_id": order.get('orderId', order.get('result', {}).get('orderId'))}
                                elif event_type == "TIME_GUARD":
                                    # TimeGuard exit
                                    pos.remaining_qty -= pos.remaining_qty  # Close entire remaining quantity
                                    pos.timeguard_closed_qty += pos.remaining_qty
                                    
                                    # Update order IDs list
                                    order_ids = json.loads(pos.order_ids or '[]')
                                    order_ids.append(order.get('orderId', order.get('result', {}).get('orderId')))
                                    pos.order_ids = json.dumps(order_ids)
                                    
                                    processing_results[acc_id] = {"status": "success", "action": "time_guard_exit", "order_id": order.get('orderId', order.get('result', {}).get('orderId'))}
                                elif event_type == "MAX_BARS":
                                    # MaxBars exit
                                    pos.remaining_qty -= pos.remaining_qty  # Close entire remaining quantity
                                    pos.maxbars_closed_qty += pos.remaining_qty
                                    
                                    # Update order IDs list
                                    order_ids = json.loads(pos.order_ids or '[]')
                                    order_ids.append(order.get('orderId', order.get('result', {}).get('orderId')))
                                    pos.order_ids = json.dumps(order_ids)
                                    
                                    processing_results[acc_id] = {"status": "success", "action": "max_bars_exit", "order_id": order.get('orderId', order.get('result', {}).get('orderId'))}
                                elif event_type == "TP5_HIT":
                                    # TP5 - Final take profit
                                    pos.remaining_qty -= pos.remaining_qty  # Close entire remaining quantity
                                    pos.closed_qty_tp5 += pos.remaining_qty
                                    
                                    # Update order IDs list
                                    order_ids = json.loads(pos.order_ids or '[]')
                                    order_ids.append(order.get('orderId', order.get('result', {}).get('orderId')))
                                    pos.order_ids = json.dumps(order_ids)
                                    
                                    # Update TP level
                                    pos.tp_level = max(pos.tp_level, 5)
                                    
                                    # Then close the position completely
                                    pos.status = 'CLOSED'
                                    processing_results[acc_id] = {"status": "success", "action": "tp5_exit", "order_id": order.get('orderId', order.get('result', {}).get('orderId')), "tp_level": 5}
                                else:
                                    # Generic close
                                    pos.remaining_qty = 0
                                    pos.status = 'CLOSED'
                                    
                                    # Update order IDs list
                                    order_ids = json.loads(pos.order_ids or '[]')
                                    order_ids.append(order.get('orderId', order.get('result', {}).get('orderId')))
                                    pos.order_ids = json.dumps(order_ids)
                                    
                                    processing_results[acc_id] = {"status": "success", "action": "close", "order_id": order.get('orderId', order.get('result', {}).get('orderId'))}
                            except Exception as e:
                                error_str = str(e)
                                # Check if the error is related to zero quantity
                                if "Quantity less than or equal to zero" in error_str or "reduce-only order qty" in error_str:
                                    print(f"⚠️ Quantity error for {acc_id}_{symbol}_{strategy_id}: {error_str}, treating as warning")
                                    processing_results[acc_id] = {"status": "warning", "action": "exit", "message": "No remaining quantity to close", "error": error_str}
                                else:
                                    print(f"❌ Exchange Error on {acc_id}: {error_str}")
                                    processing_results[acc_id] = {"status": "error", "action": "close", "error": error_str}
                                    all_successful = False
                                # Continue processing other accounts
                    else:
                        # No position found for exit event
                        processing_results[acc_id] = {"status": "warning", "action": "exit", "message": "No open position found"}
                except Exception as e:
                    print(f"❌ Processing Error for {acc_id}: {str(e)}")
                    processing_results[acc_id] = {"status": "error", "action": "unknown", "error": str(e)}
                    all_successful = False
                    # Continue processing other accounts
            
            # Only commit if at least one account was processed successfully
            # This allows partial success for multi-account signals
            if all_successful or processing_results:
                db.commit()
            else:
                # If all accounts failed, rollback
                db.rollback()
                # Raise error only if all accounts failed
                all_failed = all(result.get('status') == 'error' for result in processing_results.values())
                if all_failed and processing_results:
                    raise HTTPException(status_code=500, detail=f"All accounts failed: {processing_results}")
            
            # Return processing results to provide visibility into what happened
            return {"status": "processed", "event_id": event_id, "results": processing_results}
            
            db.commit()

        except HTTPException:
            # Re-raise HTTP exceptions without closing the session here
            raise
        except Exception as e:
            # Rollback on generic errors
            db.rollback()
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
        finally:
            # Always close the session
            db.close()

    # Execute with retry logic for database locking errors
    return execute_with_retry(execute_webhook_logic)