"""
Yapılandırma yönetimi modülü
"""

import os
import yaml
import logging
from datetime import datetime
from dotenv import load_dotenv

# Çevre değişkenlerini yükle
load_dotenv()

# Sabit değerler
DATA_DIR = os.getenv("DATA_DIR", "./data")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
USE_TESTNET = os.getenv("BINANCE_USE_TESTNET", "false").lower() == "true"
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "5"))

# Dizinleri oluştur
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(f"{DATA_DIR}/cache", exist_ok=True)
os.makedirs(f"{DATA_DIR}/logs", exist_ok=True)
os.makedirs(f"{DATA_DIR}/backups", exist_ok=True)
os.makedirs(f"{DATA_DIR}/reports", exist_ok=True)

# Loglama yapılandırması
def setup_logging():
    log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Ana logger
    log_file = f"{DATA_DIR}/logs/trading_bot_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    
    logger = logging.getLogger("trading_bot")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # API çağrıları logger
    api_logger = logging.getLogger("api_calls")
    api_logger.setLevel(logging.INFO)
    api_file = f"{DATA_DIR}/logs/api_calls_{datetime.now().strftime('%Y%m%d')}.log"
    api_handler = logging.FileHandler(api_file, encoding='utf-8')
    api_handler.setFormatter(log_formatter)
    api_logger.addHandler(api_handler)
    
    # Trade logger
    trade_logger = logging.getLogger("trade_log")
    trade_logger.setLevel(logging.INFO)
    trade_file = f"{DATA_DIR}/logs/trades_{datetime.now().strftime('%Y%m%d')}.log"
    trade_handler = logging.FileHandler(trade_file, encoding='utf-8')
    trade_handler.setFormatter(log_formatter)
    trade_logger.addHandler(trade_handler)
    
    # Performans logger
    perf_logger = logging.getLogger("performance")
    perf_logger.setLevel(logging.INFO)
    perf_file = f"{DATA_DIR}/logs/performance_{datetime.now().strftime('%Y%m%d')}.log"
    perf_handler = logging.FileHandler(perf_file, encoding='utf-8')
    perf_handler.setFormatter(log_formatter)
    perf_logger.addHandler(perf_handler)
    
    return logger, api_logger, trade_logger, perf_logger

# Varsayılan parametre değerleri
DEFAULT_PARAMS = {
    # Genel Ayarlar
    'max_open_positions': int(os.getenv('MAX_OPEN_POSITIONS', '5')),
    'max_daily_trades': int(os.getenv('MAX_DAILY_TRADES', '20')),
    'trading_type': os.getenv('TRADING_TYPE', 'BOTH'),  # LONG_ONLY, SHORT_ONLY, BOTH
    'quote_asset': os.getenv('QUOTE_ASSET', 'USDT'),
    'blacklist_symbols': os.getenv('BLACKLIST_SYMBOLS', '').split(','),
    'whitelist_symbols': os.getenv('WHITELIST_SYMBOLS', '').split(','),
    'min_volume_usdt': float(os.getenv('MIN_VOLUME_USDT', '5000000')),
    
    # Risk Yönetimi
    'account_risk_per_trade': float(os.getenv('ACCOUNT_RISK_PER_TRADE', '1.0')),  # % cinsinden
    'max_account_risk': float(os.getenv('MAX_ACCOUNT_RISK', '5.0')),  # % cinsinden
    'max_drawdown': float(os.getenv('MAX_DRAWDOWN', '10.0')),  # % cinsinden
    'default_leverage': int(os.getenv('DEFAULT_LEVERAGE', '3')),
    'max_leverage': int(os.getenv('MAX_LEVERAGE', '10')),
    'auto_leverage': os.getenv('AUTO_LEVERAGE', 'true').lower() == 'true',
    'margin_type': os.getenv('MARGIN_TYPE', 'ISOLATED'),  # ISOLATED veya CROSSED
    
    # Stop Loss ve Take Profit
    'static_sl_percent': float(os.getenv('STATIC_SL_PERCENT', '2.0')),  # % cinsinden
    'trailing_sl': os.getenv('TRAILING_SL', 'true').lower() == 'true',
    'trailing_sl_distance': float(os.getenv('TRAILING_SL_DISTANCE', '1.0')),  # % cinsinden
    'trailing_sl_interval': float(os.getenv('TRAILING_SL_INTERVAL', '0.5')),  # % cinsinden
    'take_profit_targets': [
        float(x) for x in os.getenv('TAKE_PROFIT_TARGETS', '1.5,3.0,5.0').split(',')
    ],
    'take_profit_quantities': [
        float(x) for x in os.getenv('TAKE_PROFIT_QUANTITIES', '30,30,40').split(',')
    ],
    
    # Teknik Göstergeler
    'primary_timeframe': os.getenv('PRIMARY_TIMEFRAME', '4h'),
    'secondary_timeframes': os.getenv('SECONDARY_TIMEFRAMES', '1h,1d').split(','),
    
    # RSI
    'rsi_length': int(os.getenv('RSI_LENGTH', '14')),
    'rsi_overbought': float(os.getenv('RSI_OVERBOUGHT', '70.0')),
    'rsi_oversold': float(os.getenv('RSI_OVERSOLD', '30.0')),
    'rsi_weight': float(os.getenv('RSI_WEIGHT', '1.0')),
    
    # MACD
    'macd_fast': int(os.getenv('MACD_FAST', '12')),
    'macd_slow': int(os.getenv('MACD_SLOW', '26')),
    'macd_signal': int(os.getenv('MACD_SIGNAL', '9')),
    'macd_weight': float(os.getenv('MACD_WEIGHT', '1.0')),
    
    # Bollinger Bands
    'bb_length': int(os.getenv('BB_LENGTH', '20')),
    'bb_std_dev': float(os.getenv('BB_STD_DEV', '2.0')),
    'bb_weight': float(os.getenv('BB_WEIGHT', '1.0')),
    
    # ATR
    'atr_length': int(os.getenv('ATR_LENGTH', '14')),
    'atr_multiplier': float(os.getenv('ATR_MULTIPLIER', '3.0')),
    'atr_weight': float(os.getenv('ATR_WEIGHT', '1.0')),
    
    # EMA
    'ema_short': int(os.getenv('EMA_SHORT', '9')),
    'ema_medium': int(os.getenv('EMA_MEDIUM', '21')),
    'ema_long': int(os.getenv('EMA_LONG', '50')),
    'ema_weight': float(os.getenv('EMA_WEIGHT', '1.0')),
    
    # Stochastic
    'stoch_k': int(os.getenv('STOCH_K', '14')),
    'stoch_d': int(os.getenv('STOCH_D', '3')),
    'stoch_overbought': float(os.getenv('STOCH_OVERBOUGHT', '80.0')),
    'stoch_oversold': float(os.getenv('STOCH_OVERSOLD', '20.0')),
    'stoch_weight': float(os.getenv('STOCH_WEIGHT', '1.0')),
    
    # ADX
    'adx_length': int(os.getenv('ADX_LENGTH', '14')),
    'adx_threshold': float(os.getenv('ADX_THRESHOLD', '25.0')),
    'adx_weight': float(os.getenv('ADX_WEIGHT', '1.0')),
    
    # Hacim İndikatörleri
    'obv_weight': float(os.getenv('OBV_WEIGHT', '1.0')),
    'vpt_weight': float(os.getenv('VPT_WEIGHT', '1.0')),
    
    # Ichimoku
    'ichimoku_fast': int(os.getenv('ICHIMOKU_FAST', '9')),
    'ichimoku_med': int(os.getenv('ICHIMOKU_MED', '26')),
    'ichimoku_slow': int(os.getenv('ICHIMOKU_SLOW', '52')),
    'ichimoku_weight': float(os.getenv('ICHIMOKU_WEIGHT', '1.0')),
    
    # Adaptif Ayarlar
    'adaptive_params': os.getenv('ADAPTIVE_PARAMS', 'true').lower() == 'true',
    'volatility_multiplier': float(os.getenv('VOLATILITY_MULTIPLIER', '2.0')),
    'trend_strength_factor': float(os.getenv('TREND_STRENGTH_FACTOR', '1.0')),
    
    # Piyasa Koşulları
    'bearish_btc_affect': float(os.getenv('BEARISH_BTC_AFFECT', '0.5')),  # BTC düşüşünün etki faktörü
    'market_condition_weight': float(os.getenv('MARKET_CONDITION_WEIGHT', '1.0')),
    
    # Zaman Bazlı Ayarlar
    'trading_hours_only': os.getenv('TRADING_HOURS_ONLY', 'false').lower() == 'true',
    'trading_hours_start': int(os.getenv('TRADING_HOURS_START', '9')),  # UTC saat
    'trading_hours_end': int(os.getenv('TRADING_HOURS_END', '17')),  # UTC saat
    'weekend_mode': os.getenv('WEEKEND_MODE', 'REDUCED_RISK'),  # DISABLED, REDUCED_RISK, NORMAL
    
    # Strateji Skorlama
    'min_score_to_trade': float(os.getenv('MIN_SCORE_TO_TRADE', '60.0')),
    'score_threshold_long': float(os.getenv('SCORE_THRESHOLD_LONG', '70.0')),
    'score_threshold_short': float(os.getenv('SCORE_THRESHOLD_SHORT', '70.0')),
    
    # Pozisyon Yönetimi
    'position_size_type': os.getenv('POSITION_SIZE_TYPE', 'RISK_BASED'),  # FIXED, RISK_BASED, DYNAMIC
    'fixed_position_size': float(os.getenv('FIXED_POSITION_SIZE', '100.0')),  # USDT cinsinden
    'partial_close_enabled': os.getenv('PARTIAL_CLOSE_ENABLED', 'true').lower() == 'true',
    'partial_close_threshold': float(os.getenv('PARTIAL_CLOSE_THRESHOLD', '2.0')),  # % cinsinden
    'partial_close_percentage': float(os.getenv('PARTIAL_CLOSE_PERCENTAGE', '50.0')),  # % cinsinden
    
    # Performans İzleme
    'profit_threshold_daily': float(os.getenv('PROFIT_THRESHOLD_DAILY', '3.0')),  # % cinsinden
    'loss_threshold_daily': float(os.getenv('LOSS_THRESHOLD_DAILY', '5.0')),  # % cinsinden
    
    # Funding Rate
    'avoid_high_funding': os.getenv('AVOID_HIGH_FUNDING', 'true').lower() == 'true',
    'funding_rate_threshold': float(os.getenv('FUNDING_RATE_THRESHOLD', '0.0005')),
    
    # Backtesting
    'backtesting_mode': os.getenv('BACKTESTING_MODE', 'false').lower() == 'true',
    'backtest_from': os.getenv('BACKTEST_FROM', ''),  # ISO formatı: 2023-01-01
    'backtest_to': os.getenv('BACKTEST_TO', ''),  # ISO formatı: 2023-02-01
    
    # Diğer Ayarlar
    'debug_mode': os.getenv('DEBUG_MODE', 'false').lower() == 'true',
    'log_level': os.getenv('LOG_LEVEL', 'INFO'),
    'save_trades_to_db': os.getenv('SAVE_TRADES_TO_DB', 'true').lower() == 'true',
    'check_interval': int(os.getenv('CHECK_INTERVAL', '60')),  # saniye
    'health_check_interval': int(os.getenv('HEALTH_CHECK_INTERVAL', '3600')),  # saniye
}

def load_config(config_file=None):
    """Yapılandırma dosyasından parametreleri yükler."""
    config = DEFAULT_PARAMS.copy()
    
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f)
                if file_config and isinstance(file_config, dict):
                    # İç içe parametreleri düzleştir
                    flattened = {}
                    _flatten_dict(file_config, flattened)
                    # Parametreleri güncelle
                    config.update(flattened)
        except Exception as e:
            print(f"Yapılandırma dosyası yüklenirken hata: {e}")
    
    return config

def save_config(config, config_file):
    """Parametreleri YAML dosyasına kaydeder."""
    try:
        # Parametreleri hiyerarşik yapıya dönüştür
        nested_params = _nest_dict(config)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(nested_params, f, default_flow_style=False, sort_keys=False)
        
        return True
    except Exception as e:
        print(f"Yapılandırma dosyası kaydedilirken hata: {e}")
        return False

def _flatten_dict(d, result=None, parent_key='', sep='_'):
    """İç içe sözlüğü düzleştirir."""
    if result is None:
        result = {}
    
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        
        if isinstance(v, dict):
            _flatten_dict(v, result, new_key, sep)
        else:
            result[new_key] = v
    
    return result

def _nest_dict(d, sep='_'):
    """Düz sözlüğü iç içe hiyerarşiye dönüştürür."""
    result = {}
    
    for k, v in d.items():
        parts = k.split(sep)
        current = result
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = v
    
    return result
