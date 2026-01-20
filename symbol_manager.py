"""
Symbol Manager for Arts One Two Three Automated Trading Bot
Handles auto-fetch of tradeable instruments and allowlist/denylist per strategy
"""
from typing import List, Dict, Optional, Set
from exchange_manager import exchange_manager
import re


class SymbolManager:
    """
    Manages symbols for the trading bot including:
    - Auto-fetching of tradeable instruments from exchanges
    - Allowlist/Denylist per strategy
    - Symbol filtering and validation
    """
    
    def __init__(self):
        self.available_symbols = {}  # exchange -> list of symbols
        self.strategy_allowlists = {}  # strategy_id -> set of allowed symbols
        self.strategy_denylists = {}  # strategy_id -> set of denied symbols
        self.symbol_metadata = {}  # symbol -> metadata dict
    
    def fetch_available_symbols(self, account_id: str, force_refresh: bool = False) -> List[str]:
        """
        Fetch available symbols from the exchange for a given account
        """
        exchange_config = exchange_manager.get_exchange_config(account_id)
        exchange_name = exchange_config['exchange']
        
        cache_key = f"{account_id}_{exchange_name}"
        
        # Return cached symbols if available and not forcing refresh
        if not force_refresh and cache_key in self.available_symbols:
            return self.available_symbols[cache_key]
        
        # Fetch symbols from exchange
        symbols = exchange_manager.get_available_symbols(account_id)
        
        # Cache the results
        self.available_symbols[cache_key] = symbols
        
        # Update metadata for fetched symbols
        self._update_symbol_metadata(account_id, symbols)
        
        return symbols
    
    def _update_symbol_metadata(self, account_id: str, symbols: List[str]):
        """
        Update metadata for the given symbols
        """
        # This is a simplified version - in a production system, you'd fetch
        # detailed metadata like tick size, lot size, min notional, etc.
        for symbol in symbols:
            if symbol not in self.symbol_metadata:
                self.symbol_metadata[symbol] = {
                    'symbol': symbol,
                    'account_id': account_id,
                    'tradable': True,
                    'min_notional': 5.0,  # Default min notional
                    'tick_size': 0.1,     # Default tick size
                    'lot_size': 0.001,    # Default lot size
                    'volume_24h': 0,      # Will be updated periodically
                    'price_precision': 1,  # Decimal places for price
                    'quantity_precision': 3  # Decimal places for quantity
                }
    
    def is_symbol_valid(self, symbol: str) -> bool:
        """
        Check if a symbol is valid (format-wise)
        """
        # Basic validation: should be in format like BTCUSDT, ETHUSDT, etc.
        # Should have at least 3 chars for base currency and 3 for quote currency
        pattern = r'^[A-Z]{3,}[A-Z]{3,}$'
        return bool(re.match(pattern, symbol))
    
    def is_symbol_allowed_for_strategy(self, symbol: str, strategy_id: str, account_id: str = None) -> bool:
        """
        Check if a symbol is allowed for a specific strategy
        """
        # First check if symbol is valid
        if not self.is_symbol_valid(symbol):
            return False
        
        # Check strategy-specific allowlist
        if strategy_id in self.strategy_allowlists:
            allowlist = self.strategy_allowlists[strategy_id]
            if allowlist and symbol not in allowlist:
                return False
        
        # Check strategy-specific denylist
        if strategy_id in self.strategy_denylists:
            denylist = self.strategy_denylists[strategy_id]
            if denylist and symbol in denylist:
                return False
        
        # If account_id is provided, also check account-specific filters
        if account_id:
            from account_config import account_config_manager
            if not account_config_manager.is_symbol_allowed(account_id, symbol):
                return False
        
        return True
    
    def set_strategy_allowlist(self, strategy_id: str, symbols: List[str]):
        """
        Set the allowlist for a specific strategy
        """
        self.strategy_allowlists[strategy_id] = set(symbols)
    
    def set_strategy_denylist(self, strategy_id: str, symbols: List[str]):
        """
        Set the denylist for a specific strategy
        """
        self.strategy_denylists[strategy_id] = set(symbols)
    
    def add_to_strategy_allowlist(self, strategy_id: str, symbols: List[str]):
        """
        Add symbols to the allowlist for a specific strategy
        """
        if strategy_id not in self.strategy_allowlists:
            self.strategy_allowlists[strategy_id] = set()
        self.strategy_allowlists[strategy_id].update(symbols)
    
    def remove_from_strategy_allowlist(self, strategy_id: str, symbols: List[str]):
        """
        Remove symbols from the allowlist for a specific strategy
        """
        if strategy_id in self.strategy_allowlists:
            for symbol in symbols:
                self.strategy_allowlists[strategy_id].discard(symbol)
    
    def add_to_strategy_denylist(self, strategy_id: str, symbols: List[str]):
        """
        Add symbols to the denylist for a specific strategy
        """
        if strategy_id not in self.strategy_denylists:
            self.strategy_denylists[strategy_id] = set()
        self.strategy_denylists[strategy_id].update(symbols)
    
    def remove_from_strategy_denylist(self, strategy_id: str, symbols: List[str]):
        """
        Remove symbols from the denylist for a specific strategy
        """
        if strategy_id in self.strategy_denylists:
            for symbol in symbols:
                self.strategy_denylists[strategy_id].discard(symbol)
    
    def get_filtered_symbols_for_strategy(self, strategy_id: str, account_id: str = None) -> List[str]:
        """
        Get all symbols that are allowed for a specific strategy
        """
        # Start with all available symbols
        all_symbols = set()
        if account_id:
            # If account is specified, get symbols for that account
            account_symbols = self.fetch_available_symbols(account_id)
            all_symbols.update(account_symbols)
        else:
            # Otherwise, get symbols from all exchanges
            for cache_key, symbols in self.available_symbols.items():
                all_symbols.update(symbols)
        
        # Filter based on strategy allowlist/denylist
        filtered_symbols = []
        for symbol in all_symbols:
            if self.is_symbol_allowed_for_strategy(symbol, strategy_id, account_id):
                filtered_symbols.append(symbol)
        
        return filtered_symbols
    
    def refresh_all_symbols(self):
        """
        Refresh symbols from all connected exchanges
        """
        from account_config import account_config_manager
        enabled_accounts = account_config_manager.get_enabled_accounts()
        
        for account_id in enabled_accounts:
            try:
                self.fetch_available_symbols(account_id, force_refresh=True)
            except Exception as e:
                print(f"⚠️ Error refreshing symbols for account {account_id}: {str(e)}")
    
    def get_symbol_metadata(self, symbol: str) -> Optional[Dict]:
        """
        Get metadata for a specific symbol
        """
        return self.symbol_metadata.get(symbol)
    
    def get_symbols_with_filters(self, strategy_id: str, account_id: str = None, 
                                min_volume: Optional[float] = None,
                                max_symbols: Optional[int] = None) -> List[str]:
        """
        Get symbols with additional filters like minimum volume
        """
        symbols = self.get_filtered_symbols_for_strategy(strategy_id, account_id)
        
        # Apply volume filter if specified
        if min_volume is not None:
            filtered_by_volume = []
            for symbol in symbols:
                metadata = self.get_symbol_metadata(symbol)
                if metadata and metadata.get('volume_24h', 0) >= min_volume:
                    filtered_by_volume.append(symbol)
            symbols = filtered_by_volume
        
        # Limit number of symbols if specified
        if max_symbols is not None:
            symbols = symbols[:max_symbols]
        
        return symbols


# Global instance
symbol_manager = SymbolManager()