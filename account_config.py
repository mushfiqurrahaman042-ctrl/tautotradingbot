"""
Account Configuration Manager for Arts One Two Three Automated Trading Bot
Handles multi-account configuration and routing rules
"""
import os
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import json

load_dotenv()


class AccountConfigManager:
    """
    Manages multi-account configurations and routing rules for the trading bot
    """
    
    def __init__(self):
        self.accounts = {}
        self.routing_rules = {}
        self.strategy_configs = {}
        self._load_account_configs()
        self._load_routing_rules()
        self._load_strategy_configs()
    
    def _load_account_configs(self):
        """Load account configurations from environment variables"""
        # Look for all accounts defined in environment
        for key in os.environ:
            if key.endswith('_EXCHANGE'):
                account_id = key.replace('_EXCHANGE', '')
                
                # Verify that the account has all required credentials
                api_key = os.getenv(f"{account_id}_API_KEY")
                api_secret = os.getenv(f"{account_id}_API_SECRET")
                exchange = os.getenv(f"{account_id}_EXCHANGE")
                
                if api_key and api_secret and exchange:
                    # Get additional account settings
                    symbols_allowlist = os.getenv(f"{account_id}_SYMBOLS_ALLOWLIST", "")
                    symbols_denylist = os.getenv(f"{account_id}_SYMBOLS_DENYLIST", "")
                    position_size = float(os.getenv(f"{account_id}_POSITION_SIZE", "0.001"))
                    leverage = int(os.getenv(f"{account_id}_LEVERAGE", "1"))
                    margin_mode = os.getenv(f"{account_id}_MARGIN_MODE", "cross")
                    
                    enabled_flag = os.getenv(f"{account_id}_ENABLED", "true").lower() == "true"
                    
                    # Skip disabled accounts
                    if not enabled_flag:
                        print(f"⚠️ Account {account_id} is disabled, skipping configuration")
                        continue
                        
                    self.accounts[account_id] = {
                        'exchange': exchange.lower(),
                        'api_key': api_key,
                        'api_secret': api_secret,
                        'symbols_allowlist': symbols_allowlist.split(',') if symbols_allowlist else [],
                        'symbols_denylist': symbols_denylist.split(',') if symbols_denylist else [],
                        'position_size': position_size,
                        'leverage': leverage,
                        'margin_mode': margin_mode,
                        'enabled': enabled_flag
                    }
                    
                    print(f"✅ Loaded configuration for account {account_id} ({exchange.upper()}, Enabled: {enabled_flag})")
    
    def _load_routing_rules(self):
        """Load routing rules from environment or default configuration"""
        # Default routing rules - can be customized per strategy
        self.routing_rules = {
            'default': {
                'strategies': ['arts_one_two_three'],
                'accounts': list(self.accounts.keys()),  # Route to all enabled accounts by default
                'filters': {
                    'min_volume': 1000000,  # Minimum 24h volume in USD
                    'max_leverage': 20,     # Maximum leverage allowed
                    'allowed_symbols': [],  # Empty means all symbols allowed
                    'denied_symbols': []    # Empty means no symbols denied
                }
            }
        }
        
        # Load custom routing rules from environment
        custom_rules = os.getenv("CUSTOM_ROUTING_RULES")
        if custom_rules:
            try:
                custom_rules_dict = json.loads(custom_rules)
                self.routing_rules.update(custom_rules_dict)
            except json.JSONDecodeError:
                print("⚠️ Invalid CUSTOM_ROUTING_RULES JSON in environment")
    
    def _load_strategy_configs(self):
        """Load strategy-specific configurations"""
        # Default strategy configurations
        self.strategy_configs = {
            'arts_one_two_three': {
                'mode': 'B',  # Default to Mode B (separate TP/SL events)
                'tp_levels': {
                    'TP1': {'percent': 0.2, 'trail_activation': None},
                    'TP2': {'percent': 0.2, 'trail_activation': None},
                    'TP3': {'percent': 0.2, 'trail_activation': None},
                    'TP4': {'percent': 0.2, 'trail_activation': None},
                    'TP5': {'percent': 0.2, 'trail_activation': None}
                },
                'sl_types': ['base', 'swing', 'sfp', 'body'],  # Supported SL types
                'trail_settings': {
                    'atr_period': 14,
                    'atr_multiplier': 2.0,
                    'chandelier_period': 22,
                    'chandelier_multiplier': 3.0
                },
                'volume_filters': {
                    'min_volume': 1000000,  # Minimum 24h volume
                    'volume_spike_threshold': 2.0  # 2x average volume
                }
            }
        }
        
        # Load strategy configs from environment
        strategy_configs_env = os.getenv("STRATEGY_CONFIGS")
        if strategy_configs_env:
            try:
                strategy_configs_dict = json.loads(strategy_configs_env)
                self.strategy_configs.update(strategy_configs_dict)
            except json.JSONDecodeError:
                print("⚠️ Invalid STRATEGY_CONFIGS JSON in environment")
    
    def get_enabled_accounts(self) -> List[str]:
        """Get list of enabled accounts"""
        return [acc_id for acc_id, config in self.accounts.items() if config['enabled']]
    
    def get_account_config(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific account"""
        return self.accounts.get(account_id)
    
    def is_symbol_allowed(self, account_id: str, symbol: str) -> bool:
        """Check if a symbol is allowed for an account"""
        config = self.get_account_config(account_id)
        if not config:
            return False
        
        # Check denylist first
        if config['symbols_denylist'] and symbol in config['symbols_denylist']:
            return False
        
        # Check allowlist if specified
        if config['symbols_allowlist'] and symbol not in config['symbols_allowlist']:
            return False
        
        return True
    
    def get_accounts_for_strategy(self, strategy_id: str, symbol: str = None) -> List[str]:
        """Get accounts that should receive signals for a specific strategy and symbol"""
        eligible_accounts = []
        
        # Get routing rules for the strategy
        routing_rule = self.routing_rules.get(strategy_id) or self.routing_rules.get('default')
        
        if not routing_rule:
            return []
        
        # Check accounts specified in routing rule
        target_accounts = routing_rule.get('accounts', [])
        
        for account_id in target_accounts:
            if account_id not in self.accounts:
                continue
                
            account_config = self.accounts[account_id]
            if not account_config['enabled']:
                continue
            
            # Check symbol filters
            filters = routing_rule.get('filters', {})
            
            # Check if symbol is allowed for this account
            if not self.is_symbol_allowed(account_id, symbol or ""):
                continue
            
            # Apply additional filters if needed
            if filters.get('allowed_symbols') and symbol not in filters['allowed_symbols']:
                continue
            if filters.get('denied_symbols') and symbol in filters['denied_symbols']:
                continue
            
            eligible_accounts.append(account_id)
        
        return eligible_accounts
    
    def get_strategy_config(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific strategy"""
        return self.strategy_configs.get(strategy_id)
    
    def update_account_status(self, account_id: str, enabled: bool) -> bool:
        """Enable or disable an account"""
        if account_id in self.accounts:
            self.accounts[account_id]['enabled'] = enabled
            return True
        return False
    
    def add_routing_rule(self, rule_name: str, rule_config: Dict[str, Any]):
        """Add a new routing rule"""
        self.routing_rules[rule_name] = rule_config
    
    def get_all_accounts(self) -> Dict[str, Dict[str, Any]]:
        """Get all account configurations"""
        return self.accounts.copy()
    
    def get_account_summary(self) -> List[Dict[str, Any]]:
        """Get a summary of all accounts"""
        summary = []
        for acc_id, config in self.accounts.items():
            summary.append({
                'account_id': acc_id,
                'exchange': config['exchange'],
                'enabled': config['enabled'],
                'position_size': config['position_size'],
                'leverage': config['leverage'],
                'margin_mode': config['margin_mode'],
                'symbol_count': len(config.get('symbols_allowlist', []))
            })
        return summary


# Global instance
account_config_manager = AccountConfigManager()