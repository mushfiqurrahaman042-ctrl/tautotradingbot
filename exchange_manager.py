"""
Exchange Manager for Arts One Two Three Automated Trading Bot
Handles both Binance and Bybit connections with WhiteList Capital broker compatibility
"""
import os
from dotenv import load_dotenv
from binance.um_futures import UMFutures
from pybit.unified_trading import HTTP
import time
import json
from typing import Dict, Optional, List, Any

load_dotenv()

class ExchangeManager:
    """
    Unified Exchange Manager that handles both Binance and Bybit connections
    with WhiteList Capital broker compatibility and enhanced features
    """
    
    def __init__(self):
        self.clients = {}
        self.exchange_configs = {}
        self._initialize_exchanges()
    
    def _initialize_exchanges(self):
        """Initialize exchange clients based on environment configuration"""
        # Load all account configurations from environment
        for key in os.environ:
            if key.endswith('_EXCHANGE'):
                account_id = key.replace('_EXCHANGE', '')
                exchange_name = os.getenv(key)
                
                # Get API credentials for this account
                api_key = os.getenv(f"{account_id}_API_KEY")
                api_secret = os.getenv(f"{account_id}_API_SECRET")
                enabled = os.getenv(f"{account_id}_ENABLED", "true").lower() == "true"
                
                # Skip disabled accounts
                if not enabled:
                    print(f"⚠️ Skipping disabled account {account_id}")
                    continue
                
                if api_key and api_secret:
                    # Determine if using testnet based on environment
                    use_testnet = os.getenv("USE_TESTNET", "true").lower() == "true"
                    
                    if exchange_name.lower() == "binance":
                        # Use Binance Futures with optional testnet
                        client = UMFutures(
                            key=api_key,
                            secret=api_secret,
                            base_url="https://testnet.binancefuture.com" if use_testnet else "https://fapi.binance.com"
                        )
                        print(f"✅ {account_id} - Binance Client Initialized ({'Testnet' if use_testnet else 'Live'})")
                        
                    elif exchange_name.lower() == "bybit":
                        # Use Bybit Unified Trading API with optional testnet
                        client = HTTP(
                            testnet=use_testnet,  # Use testnet if enabled
                            api_key=api_key,
                            api_secret=api_secret,
                        )
                        print(f"✅ {account_id} - Bybit Client Initialized ({'Testnet' if use_testnet else 'Live'})")
                    else:
                        raise ValueError(f"Unsupported exchange: {exchange_name}")
                    
                    self.clients[account_id] = client
                    self.exchange_configs[account_id] = {
                        'exchange': exchange_name,
                        'testnet': use_testnet
                    }
    
    def get_client(self, account_id: str):
        """Get exchange client for a specific account"""
        if account_id not in self.clients:
            raise ValueError(f"No client initialized for account: {account_id}")
        return self.clients[account_id]
    
    def get_exchange_config(self, account_id: str) -> Dict[str, Any]:
        """Get configuration for a specific account"""
        if account_id not in self.exchange_configs:
            raise ValueError(f"No configuration found for account: {account_id}")
        return self.exchange_configs[account_id]
    
    def execute_order(
        self, 
        account_id: str, 
        symbol: str, 
        side: str, 
        qty: float, 
        reduce_only: bool = False, 
        order_type: str = "MARKET",
        price: Optional[float] = None,
        time_in_force: str = "GTC",
        **kwargs
    ):
        """Execute an order on the specified exchange with advanced options"""
        # Use the ExchangeHandler's execute_order method
        from exchange_handler import ExchangeHandler
        return ExchangeHandler.execute_order(
            account_id=account_id,
            symbol=symbol,
            side=side,
            qty=qty,
            reduce_only=reduce_only,
            order_type=order_type,
            price=price,
            time_in_force=time_in_force,
            **kwargs
        )
    
    def get_last_price(self, account_id: str, symbol: str) -> Optional[float]:
        """Fetch the last traded price for a symbol."""
        client = self.get_client(account_id)
        exchange_config = self.get_exchange_config(account_id)
        exch_name = exchange_config['exchange']
        
        try:
            if exch_name.lower() == "binance":
                ticker = client.ticker_price(symbol=symbol)
                return float(ticker['price']) if ticker and 'price' in ticker else None
            elif exch_name.lower() == "bybit":
                ticker_response = client.get_tickers(category="linear", symbol=symbol)
                tickers = ticker_response.get('result', {}).get('list', [])
                if tickers:
                    return float(tickers[0]['lastPrice']) if 'lastPrice' in tickers[0] else None
                return None
        except Exception as e:
            print(f"❌ Error fetching price on {exch_name.upper()}: {str(e)}")
            return None

    def format_quantity(self, exch_name: str, symbol: str, qty: float) -> str:
        """Format quantity according to exchange's precision requirements."""
        qty = float(qty)
        
        if exch_name.lower() == "binance":
            # Binance has specific precision requirements per symbol
            symbol_upper = symbol.upper()
            
            # Determine decimal places based on symbol (these are typical Binance requirements)
            if symbol_upper in ["BTCUSDT", "BTCUSD"]:
                # BTC typically allows 3-6 decimal places, using 3 is safe
                decimal_places = 3
            elif symbol_upper in ["ETHUSDT", "ETHUSD"]:
                # ETH typically allows 3-5 decimal places, using 3 is safe
                decimal_places = 3
            elif symbol_upper in ["SOLUSDT"]:
                # SOL typically allows 2-3 decimal places
                decimal_places = 3
            elif symbol_upper in ["ADAUSDT"]:
                # ADA typically allows 1-2 decimal places
                decimal_places = 1
            elif symbol_upper in ["XRPUSDT"]:
                # XRP typically allows 0-1 decimal places
                decimal_places = 0
            elif symbol_upper in ["DOGEUSDT"]:
                # DOGE typically allows 0-1 decimal places
                decimal_places = 0
            elif symbol_upper in ["AVAXUSDT"]:
                # AVAX typically allows 2-3 decimal places
                decimal_places = 2
                # Increase default quantity for AVAX to meet minimum notional value
                if qty < 0.2:  # If quantity is too small for AVAX's price (~$40), increase it
                    qty = max(qty, 0.2)  # Ensure enough AVAX to meet $5 minimum
            else:
                # Default to 3 decimal places for other symbols
                decimal_places = 3
            
            # Round to the appropriate number of decimal places
            factor = 10 ** decimal_places
            result = round(qty * factor) / factor
            
            # Apply minimum notional value check for USDT pairs
            # Determine if using testnet based on environment
            use_testnet = os.getenv("USE_TESTNET", "true").lower() == "true"
            min_notional = 100 if use_testnet else 5  # $100 for testnet, $5 for live
            
            if symbol_upper.endswith("USDT"):
                # We need to estimate current price to calculate notional value
                # Since we don't have real-time prices here, use approximate prices
                approx_prices = {
                    "BTCUSDT": 40000,
                    "ETHUSDT": 2500,
                    "SOLUSDT": 100,
                    "ADAUSDT": 0.5,
                    "XRPUSDT": 0.6,
                    "DOGEUSDT": 0.1,
                    "AVAXUSDT": 40
                }
                
                approx_price = approx_prices.get(symbol_upper, 10)  # Default to $10 if unknown
                notional_value = result * approx_price
                
                # If notional value is less than minimum, adjust quantity
                if notional_value < min_notional:
                    result = max(result, min_notional / approx_price)  # Adjust to meet minimum requirement
                    result = round(result * factor) / factor  # Re-round to proper decimal places
                
                # Additional specific adjustments for known problematic symbols
                if symbol_upper == "ADAUSDT" and result < (min_notional / 0.5):  # At $0.5 per coin, need more coins for min_notional
                    result = max(result, min_notional / 0.5)
                    result = round(result * factor) / factor
                elif symbol_upper == "AVAXUSDT" and result < (min_notional / 40):  # At $40 per coin, need more coins for min_notional
                    result = max(result, min_notional / 40)
                    result = round(result * factor) / factor
            
            # Ensure result is not zero or negative after rounding
            if result <= 0:
                # If rounding resulted in zero, use a minimum value
                # Use smallest allowed value for this symbol type
                if decimal_places == 0:
                    result = 1.0  # For symbols that don't allow decimals
                else:
                    result = 1.0 / factor  # Smallest allowed quantity for this decimal place
            return str(result)
        elif exch_name.lower() == "bybit":
            # Bybit typically uses 2-3 decimal places
            result = round(qty, 3)
            # Ensure result is not zero or negative after rounding
            if result <= 0:
                if qty > 0:
                    result = min(qty, 0.001)
                else:
                    result = 0.001
            return str(result)
        
        return str(qty)

    def get_all_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """Get all positions for an account from the exchange."""
        client = self.get_client(account_id)
        exchange_config = self.get_exchange_config(account_id)
        exch_name = exchange_config['exchange']
        
        try:
            if exch_name.lower() == "binance":
                # Get all positions from Binance
                account_info = client.account()
                positions = account_info['positions']
                
                # Filter out zero positions and format data
                filtered_positions = []
                for position in positions:
                    position_amt = float(position.get('positionAmt', 0))
                    if position_amt != 0:  # Only include non-zero positions
                        # Safely convert string values to floats, handling empty strings
                        def safe_float(value):
                            if value == '' or value is None:
                                return 0.0
                            try:
                                return float(value)
                            except (ValueError, TypeError):
                                return 0.0
                        
                        filtered_positions.append({
                            'symbol': position['symbol'],
                            'positionAmt': safe_float(position.get('positionAmt')),
                            'entryPrice': safe_float(position.get('entryPrice')),
                            'unRealizedProfit': safe_float(position.get('unRealizedProfit')),
                            'liquidationPrice': safe_float(position.get('liquidationPrice')),
                            'leverage': safe_float(position.get('leverage')),
                            'marginType': position.get('marginType', 'cross'),
                            'isolatedMargin': safe_float(position.get('isolatedMargin')),
                            'positionSide': position.get('positionSide', 'BOTH')
                        })
                return filtered_positions
                
            elif exch_name.lower() == "bybit":
                # Get all positions from Bybit
                response = client.get_positions(category="linear")
                positions = response.get('result', {}).get('list', [])
                
                # Filter out zero positions and format data
                filtered_positions = []
                for position in positions:
                    size = float(position.get('size', 0))
                    if size != 0:  # Only include non-zero positions
                        # Safely convert string values to floats, handling empty strings
                        def safe_float(value):
                            if value == '' or value is None:
                                return 0.0
                            try:
                                return float(value)
                            except (ValueError, TypeError):
                                return 0.0
                        
                        # Convert side to amount (positive for Buy, negative for Sell)
                        position_amt = size if position.get('side') == 'Buy' else -size
                        
                        filtered_positions.append({
                            'symbol': position['symbol'],
                            'positionAmt': position_amt,
                            'entryPrice': safe_float(position.get('avgPrice')),
                            'unRealizedProfit': safe_float(position.get('unrealisedPnl')),
                            'liquidationPrice': safe_float(position.get('liqPrice')),
                            'leverage': safe_float(position.get('leverage')),
                            'positionSide': position.get('side', 'Buy')
                        })
                return filtered_positions
                
            return []
        except Exception as e:
            print(f"❌ Error fetching all positions from {exch_name.upper()}: {str(e)}")
            return []

    def get_position_info(self, account_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current position information for a symbol."""
        client = self.get_client(account_id)
        exchange_config = self.get_exchange_config(account_id)
        exch_name = exchange_config['exchange']
        
        try:
            if exch_name.lower() == "binance":
                positions = client.account()
                for position in positions['positions']:
                    if position['symbol'] == symbol:
                        
                        # Safely convert string values to floats, handling empty strings
                        def safe_float(value):
                            if value == '' or value is None:
                                return 0.0
                            try:
                                return float(value)
                            except (ValueError, TypeError):
                                return 0.0
                        
                        return {
                            'symbol': position['symbol'],
                            'positionAmt': safe_float(position['positionAmt']),
                            'entryPrice': safe_float(position['entryPrice']),
                            'unRealizedProfit': safe_float(position['unRealizedProfit']),
                            'liquidationPrice': safe_float(position['liquidationPrice'])
                        }
            elif exch_name.lower() == "bybit":
                # Get positions for Bybit
                response = client.get_positions(category="linear", symbol=symbol)
                positions = response.get('result', {}).get('list', [])
                if positions:
                    pos = positions[0]
                    
                    # Safely convert string values to floats, handling empty strings
                    def safe_float(value):
                        if value == '' or value is None:
                            return 0.0
                        try:
                            return float(value)
                        except (ValueError, TypeError):
                            return 0.0
                    
                    size = safe_float(pos['size'])
                    if pos['side'] == 'Sell':
                        size = -size
                    
                    return {
                        'symbol': pos['symbol'],
                        'size': size,
                        'entryPrice': safe_float(pos.get('avgPrice')),
                        'unrealisedPnl': safe_float(pos.get('unrealisedPnl'))
                    }
            return None
        except Exception as e:
            print(f"❌ Error fetching position info on {exch_name.upper()}: {str(e)}")
            return None

    def cancel_order(self, account_id: str, symbol: str, order_id: str) -> Any:
        """Cancel an existing order."""
        client = self.get_client(account_id)
        exchange_config = self.get_exchange_config(account_id)
        exch_name = exchange_config['exchange']
        
        try:
            if exch_name.lower() == "binance":
                result = client.cancel_order(symbol=symbol, orderId=order_id)
            elif exch_name.lower() == "bybit":
                result = client.cancel_order(category="linear", symbol=symbol, orderId=order_id)
            
            print(f"✅ Order {order_id} cancelled successfully on {exch_name.upper()}")
            return result
        except Exception as e:
            print(f"❌ Error cancelling order {order_id} on {exch_name.upper()}: {str(e)}")
            raise

    def get_available_symbols(self, account_id: str, whitelist: Optional[List[str]] = None, blacklist: Optional[List[str]] = None) -> List[str]:
        """Get list of available symbols from exchange, filtered by whitelist/blacklist."""
        client = self.get_client(account_id)
        exchange_config = self.get_exchange_config(account_id)
        exch_name = exchange_config['exchange']
        
        try:
            if exch_name.lower() == "binance":
                # Get all futures symbols from Binance
                exchange_info = client.exchange_info()
                symbols = [s['symbol'] for s in exchange_info['symbols'] 
                          if s['contractType'] == 'PERPETUAL' and s['status'] == 'TRADING']
            elif exch_name.lower() == "bybit":
                # Get all linear perpetual symbols from Bybit
                response = client.get_instruments_info(category="linear")
                instruments = response.get('result', {}).get('list', [])
                symbols = [inst['symbol'] for inst in instruments if inst['status'] == 'Trading']
            
            # Apply filters
            if whitelist:
                symbols = [s for s in symbols if s in whitelist]
            if blacklist:
                symbols = [s for s in symbols if s not in blacklist]
                
            return symbols
        except Exception as e:
            print(f"❌ Error fetching available symbols from {exch_name.upper()}: {str(e)}")
            return []

    def get_account_balance(self, account_id: str) -> Dict[str, Any]:
        """Get account balance information."""
        client = self.get_client(account_id)
        exchange_config = self.get_exchange_config(account_id)
        exch_name = exchange_config['exchange']
        
        try:
            if exch_name.lower() == "binance":
                account_info = client.account()
                balances = account_info['assets']
                usdt_balance = next((item for item in balances if item['asset'] == 'USDT'), {})
                # Handle potential empty string values by converting to float safely
                margin_balance_val = usdt_balance.get('marginBalance', 0)
                available_balance_val = usdt_balance.get('availableBalance', 0)
                
                # Convert to float, handling empty strings
                total_bal = float(margin_balance_val) if margin_balance_val != '' and margin_balance_val is not None else 0.0
                avail_bal = float(available_balance_val) if available_balance_val != '' and available_balance_val is not None else 0.0
                
                return {
                    'totalBalance': total_bal,
                    'availableBalance': avail_bal,
                    'asset': 'USDT'
                }
            elif exch_name.lower() == "bybit":
                response = client.get_wallet_balance(accountType="UNIFIED")
                balances = response.get('result', {}).get('list', [])
                if balances:
                    coin_balance = next((coin for coin in balances[0]['coin'] if coin['coin'] == 'USDT'), {})
                    
                    # Handle potential empty string values by converting to float safely
                    wallet_balance_val = coin_balance.get('walletBalance', 0)
                    # Use availableToTrade instead of availableToWithdraw for trading purposes
                    trade_balance_val = coin_balance.get('availableToTrade', 0)
                    
                    # Convert to float, handling empty strings
                    total_bal = float(wallet_balance_val) if wallet_balance_val != '' and wallet_balance_val is not None else 0.0
                    avail_bal = float(trade_balance_val) if trade_balance_val != '' and trade_balance_val is not None else 0.0
                    
                    return {
                        'totalBalance': total_bal,
                        'availableBalance': avail_bal,
                        'asset': 'USDT'
                    }
            return {'totalBalance': 0, 'availableBalance': 0, 'asset': 'USDT'}
        except Exception as e:
            print(f"❌ Error fetching account balance from {exch_name.upper()}: {str(e)}")
            return {'totalBalance': 0, 'availableBalance': 0, 'asset': 'USDT'}

    def place_multiple_orders(self, account_id: str, orders: List[Dict]) -> List[Any]:
        """Place multiple orders at once (batch order placement)."""
        results = []
        for order_data in orders:
            try:
                result = self.execute_order(account_id, **order_data)
                results.append(result)
            except Exception as e:
                print(f"❌ Failed to place order: {str(e)}")
                results.append({'error': str(e)})
        return results

    def get_open_orders(self, account_id: str, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of open orders."""
        client = self.get_client(account_id)
        exchange_config = self.get_exchange_config(account_id)
        exch_name = exchange_config['exchange']
        
        try:
            if exch_name.lower() == "binance":
                params = {}
                if symbol:
                    params['symbol'] = symbol
                orders = client.get_open_orders(**params)
                return orders
            elif exch_name.lower() == "bybit":
                params = {"category": "linear"}
                if symbol:
                    params['symbol'] = symbol
                response = client.get_open_orders(**params)
                return response.get('result', {}).get('list', [])
        except Exception as e:
            print(f"❌ Error fetching open orders from {exch_name.upper()}: {str(e)}")
            return []

    def get_exchange_status(self, account_id: str) -> Dict[str, Any]:
        """Get the status of the exchange connection."""
        try:
            # Try to fetch a simple piece of data to verify connection
            balance = self.get_account_balance(account_id)
            return {
                'connected': True,
                'balance': balance,
                'timestamp': time.time()
            }
        except Exception as e:
            return {
                'connected': False,
                'error': str(e),
                'timestamp': time.time()
            }


# Global instance for easy access
exchange_manager = ExchangeManager()