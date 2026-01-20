"""
Price Monitor for Arts One Two Three Automated Trading Bot
Monitors prices and triggers take-profit orders for Mode A
"""
import asyncio
import threading
from typing import Dict, List, Optional
from exchange_manager import exchange_manager
from models import Position
from position_manager import PositionManager
from sqlalchemy.orm import sessionmaker
import time
import json


class PriceMonitor:
    """
    Monitors prices and triggers take-profit orders for Mode A
    where TP levels are provided at entry and the bot monitors prices
    """
    
    def __init__(self, engine, position_manager: PositionManager):
        self.engine = engine
        self.SessionLocal = sessionmaker(bind=engine)
        self.position_manager = position_manager
        self.active_monitors = {}  # Maps (account_id, symbol) to monitor info
        self.running = False
        self.monitor_thread = None
        
    def start_monitoring(self):
        """Start the price monitoring thread"""
        if not self.running:
            self.running = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            print("✅ Price Monitor started")
    
    def stop_monitoring(self):
        """Stop the price monitoring thread"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        print("✅ Price Monitor stopped")
    
    def add_position_to_monitor(self, account_id: str, symbol: str, position: Position):
        """Add a position to be monitored for take-profit levels"""
        if position.tp_levels:
            try:
                tp_levels = json.loads(position.tp_levels) if isinstance(position.tp_levels, str) else position.tp_levels
                if tp_levels:
                    key = (account_id, symbol)
                    self.active_monitors[key] = {
                        'position': position,
                        'tp_levels': tp_levels,
                        'side': position.side,
                        'last_checked': time.time()
                    }
                    print(f"✅ Added {symbol} position to price monitor for account {account_id}")
            except json.JSONDecodeError:
                print(f"⚠️ Invalid TP levels JSON for {symbol} position")
    
    def remove_position_from_monitor(self, account_id: str, symbol: str):
        """Remove a position from monitoring"""
        key = (account_id, symbol)
        if key in self.active_monitors:
            del self.active_monitors[key]
            print(f"✅ Removed {symbol} from price monitor for account {account_id}")
    
    def _monitor_loop(self):
        """Main monitoring loop that runs in a separate thread"""
        while self.running:
            try:
                self._check_prices()
                time.sleep(1)  # Check every second
            except Exception as e:
                print(f"❌ Error in price monitor: {str(e)}")
                time.sleep(5)  # Wait longer if there's an error
    
    def _check_prices(self):
        """Check current prices against TP levels for all monitored positions"""
        for (account_id, symbol), monitor_info in list(self.active_monitors.items()):
            try:
                # Get current price
                current_price = exchange_manager.get_last_price(account_id, symbol)
                if current_price is None:
                    continue
                
                position = monitor_info['position']
                tp_levels = monitor_info['tp_levels']
                position_side = monitor_info['side']  # 'buy' or 'sell'
                
                # Check if any TP levels have been hit
                for tp_level_name, tp_details in list(tp_levels.items()):
                    if isinstance(tp_details, dict) and 'price' in tp_details and 'percent' in tp_details:
                        tp_price = float(tp_details['price'])
                        tp_percent = float(tp_details['percent'])
                        
                        # For long positions (buy), trigger TP when price >= TP price
                        # For short positions (sell), trigger TP when price <= TP price
                        tp_triggered = False
                        if position_side == 'buy' and current_price >= tp_price:
                            tp_triggered = True
                        elif position_side == 'sell' and current_price <= tp_price:
                            tp_triggered = True
                        
                        if tp_triggered:
                            # Calculate quantity to close based on percentage
                            close_qty = position.initial_qty * tp_percent
                            
                            # Execute take profit order
                            try:
                                exit_side = 'sell' if position_side == 'buy' else 'buy'
                                
                                order = exchange_manager.execute_order(
                                    account_id=account_id,
                                    symbol=symbol,
                                    side=exit_side,
                                    qty=close_qty,
                                    reduce_only=True,
                                    order_type="MARKET"
                                )
                                
                                # Parse TP level number (e.g., TP1 -> 1, TP2 -> 2, etc.)
                                tp_num = int(tp_level_name.replace('TP', '')) if tp_level_name.startswith('TP') else None
                                
                                # Update position in database
                                self.position_manager.update_position_after_partial_exit(
                                    position, 
                                    close_qty, 
                                    order.get('orderId', order.get('result', {}).get('orderId')), 
                                    tp_level=tp_num
                                )
                                
                                # Remove the triggered TP level from monitoring
                                del tp_levels[tp_level_name]
                                
                                print(f"✅ {tp_level_name} hit for {symbol} at ${tp_price}. Closed {close_qty} units.")
                                
                                # Update the position's TP levels in DB
                                position.tp_levels = json.dumps(tp_levels) if tp_levels else None
                                
                                # If no more TP levels, remove from monitoring
                                if not tp_levels:
                                    self.remove_position_from_monitor(account_id, symbol)
                                
                            except Exception as order_error:
                                print(f"❌ Failed to execute {tp_level_name} order for {symbol}: {str(order_error)}")
                                
            except Exception as e:
                print(f"❌ Error checking price for {symbol} on {account_id}: {str(e)}")
    
    def get_monitoring_status(self) -> Dict:
        """Get current status of price monitoring"""
        return {
            'running': self.running,
            'monitored_positions_count': len(self.active_monitors),
            'monitored_positions': list(self.active_monitors.keys())
        }


# Global price monitor instance
price_monitor = None

def init_price_monitor(engine, position_manager):
    """Initialize the price monitor"""
    global price_monitor
    if price_monitor is None:
        price_monitor = PriceMonitor(engine, position_manager)
        price_monitor.start_monitoring()
    return price_monitor