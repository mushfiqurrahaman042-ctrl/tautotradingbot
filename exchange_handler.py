import os
from dotenv import load_dotenv
from binance.um_futures import UMFutures
from pybit.unified_trading import HTTP
import time

load_dotenv()

class ExchangeHandler:
    @staticmethod
    def get_client(account_id):
        exch_name = os.getenv(f"{account_id}_EXCHANGE", "binance").lower()
        api_key = os.getenv(f"{account_id}_API_KEY")
        api_secret = os.getenv(f"{account_id}_API_SECRET")
        
        # Determine if using testnet based on environment
        use_testnet = os.getenv("USE_TESTNET", "true").lower() == "true"
        
        if exch_name == "binance":
            # Use Binance Futures with optional testnet
            client = UMFutures(
                key=api_key,
                secret=api_secret,
                base_url="https://testnet.binancefuture.com" if use_testnet else "https://fapi.binance.com"
            )
            print(f"✅ {exch_name.capitalize()} Client Initialized ({'Testnet' if use_testnet else 'Live'})")
            
        elif exch_name == "bybit":
            # Use Bybit Unified Trading API with optional testnet
            client = HTTP(
                testnet=use_testnet,  # Use testnet if enabled
                api_key=api_key,
                api_secret=api_secret,
            )
            print(f"✅ {exch_name.capitalize()} Client Initialized ({'Testnet' if use_testnet else 'Live'})")
        else:
            raise ValueError(f"Unsupported exchange: {exch_name}")
            
        return client

    @staticmethod
    def execute_order(account_id, symbol, side, qty, reduce_only=False, order_type="MARKET", price=None, time_in_force="GTC", **kwargs):
        client = ExchangeHandler.get_client(account_id)
        exch_name = os.getenv(f"{account_id}_EXCHANGE", "binance").lower()
        
        # Format quantity according to exchange requirements
        formatted_qty = ExchangeHandler.format_quantity(client, exch_name, symbol, qty)
        
        # Ensure quantity is positive and greater than zero
        qty_as_float = float(formatted_qty)
        if qty_as_float <= 0:
            raise ValueError(f"Invalid quantity: {formatted_qty}. Quantity must be greater than zero.")
        
        # Define minimum quantities for different symbols
        symbol_upper = symbol.upper()
        min_qty = 0.001  # Default minimum
        
        if "BTC" in symbol_upper:
            min_qty = 0.001
        elif "ETH" in symbol_upper:
            min_qty = 0.001
        elif any(coin in symbol_upper for coin in ["SOL", "ADA", "XRP", "DOGE", "AVAX"]):
            min_qty = 0.001  # Even for altcoins, ensure minimum
        
        # Adjust quantity if it's below minimum
        if qty_as_float < min_qty:
            logger = __import__('logging').getLogger(__name__)
            logger.warning(f"⚠️ Quantity {qty_as_float} for {symbol} is below minimum {min_qty}, adjusting to minimum")
            formatted_qty = min_qty
        
        try:
            if exch_name == "binance":
                # Prepare parameters for Binance
                params = {
                    "symbol": symbol,
                    "side": side.upper(),
                    "type": order_type,
                    "quantity": str(formatted_qty)  # Convert to string as expected by Binance API
                }
                
                # Add additional parameters based on order type
                if order_type == "LIMIT" and price:
                    params["price"] = str(price)
                    params["timeInForce"] = time_in_force
                
                # Add reduceOnly for exit orders
                if reduce_only:
                    params["reduceOnly"] = True  # Use boolean True instead of string "true"
                    
                # Add any additional parameters passed in kwargs
                params.update(kwargs)
                
                print(f"📤 Executing {order_type} order on Binance: {side.upper()} {formatted_qty} {symbol}")
                print(f"   Parameters: {params}")
                
                # Execute order
                order = client.new_order(**params)
                
            elif exch_name == "bybit":
                # Prepare parameters for Bybit V5 API
                params = {
                    "category": "linear",
                    "symbol": symbol,
                    "side": side.capitalize(),  # 'Buy' or 'Sell'
                    "orderType": order_type,
                    "qty": str(formatted_qty),
                }
                
                # Add additional parameters based on order type
                if order_type == "LIMIT":
                    if price:
                        params["price"] = str(price)
                    else:
                        # For limit orders without explicit price, Bybit requires price or BBO
                        # This would need to be handled by fetching current price if not provided
                        pass
                
                # Add reduceOnly for exit orders
                if reduce_only:
                    params["reduceOnly"] = True
                    
                # Add any additional parameters passed in kwargs
                params.update(kwargs)
                
                print(f"📤 Executing {order_type} order on Bybit: {side.capitalize()} {formatted_qty} {symbol}")
                print(f"   Parameters: {params}")
                
                # Execute order
                order = client.place_order(**params)
                
            print(f"✅ Order executed successfully on {exch_name.upper()}: {order.get('orderId', order.get('result', {}).get('orderId'))}")
            return order
            
        except Exception as e:
            print(f"❌ Error executing order on {exch_name.upper()}: {str(e)}")
            raise

    @staticmethod
    def get_last_price(account_id, symbol):
        """Fetches the last traded price for a symbol."""
        client = ExchangeHandler.get_client(account_id)
        exch_name = os.getenv(f"{account_id}_EXCHANGE", "binance").lower()
        
        try:
            if exch_name == "binance":
                ticker = client.ticker_price(symbol=symbol)
                return float(ticker['price']) if ticker and 'price' in ticker else None
            elif exch_name == "bybit":
                ticker_response = client.get_tickers(category="linear", symbol=symbol)
                tickers = ticker_response.get('result', {}).get('list', [])
                if tickers:
                    return float(tickers[0]['lastPrice']) if 'lastPrice' in tickers[0] else None
                return None
        except Exception as e:
            print(f"❌ Error fetching price on {exch_name.upper()}: {str(e)}")
            return None

    @staticmethod
    def format_quantity(client, exch_name, symbol, qty):
        """Format quantity according to exchange's precision requirements."""
        qty = float(qty)
        
        if exch_name == "binance":
            # Binance has specific precision requirements per symbol
            # Use proper decimal places based on Binance's actual requirements
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
                decimal_places = 3  # Use 3 decimal places to avoid precision errors
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
            
            # Ensure result is not zero or negative after adjustments
            if result <= 0:
                # If rounding resulted in zero, use a minimum value
                # Use smallest allowed value for this symbol type
                if decimal_places == 0:
                    result = 1.0  # For symbols that don't allow decimals
                else:
                    result = 1.0 / factor  # Smallest allowed quantity for this decimal place
            
            return result
        elif exch_name == "bybit":
            # Bybit typically uses 2-3 decimal places
            result = round(qty, 3)
            # Ensure result is not zero or negative after rounding
            if result <= 0:
                if qty > 0:
                    result = min(qty, 0.001)
                else:
                    result = 0.001
            return result
        
        return qty
    
    @staticmethod
    def get_position_info(account_id, symbol):
        """Get current position information for a symbol."""
        client = ExchangeHandler.get_client(account_id)
        exch_name = os.getenv(f"{account_id}_EXCHANGE", "binance").lower()
        
        try:
            if exch_name == "binance":
                positions = client.account()
                for position in positions['positions']:
                    if position['symbol'] == symbol:
                        return {
                            'symbol': position['symbol'],
                            'positionAmt': float(position['positionAmt']),
                            'entryPrice': float(position['entryPrice']),
                            'unRealizedProfit': float(position['unRealizedProfit']),
                            'liquidationPrice': float(position['liquidationPrice'])
                        }
            elif exch_name == "bybit":
                # Get positions for Bybit
                response = client.get_positions(category="linear", symbol=symbol)
                positions = response.get('result', {}).get('list', [])
                if positions:
                    pos = positions[0]
                    return {
                        'symbol': pos['symbol'],
                        'size': float(pos['size']) if pos['side'] == 'Buy' else -float(pos['size']),
                        'entryPrice': float(pos['avgPrice']),
                        'unrealisedPnl': float(pos['unrealisedPnl'])
                    }
            return None
        except Exception as e:
            print(f"❌ Error fetching position info on {exch_name.upper()}: {str(e)}")
            return None

    @staticmethod
    def cancel_order(account_id, symbol, order_id):
        """Cancel an existing order."""
        client = ExchangeHandler.get_client(account_id)
        exch_name = os.getenv(f"{account_id}_EXCHANGE", "binance").lower()
        
        try:
            if exch_name == "binance":
                result = client.cancel_order(symbol=symbol, orderId=order_id)
            elif exch_name == "bybit":
                result = client.cancel_order(category="linear", symbol=symbol, orderId=order_id)
            
            print(f"✅ Order {order_id} cancelled successfully on {exch_name.upper()}")
            return result
        except Exception as e:
            print(f"❌ Error cancelling order {order_id} on {exch_name.upper()}: {str(e)}")
            raise